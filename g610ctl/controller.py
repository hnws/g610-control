"""Application logic: device thread, active profile, effect playback, sleep and lock handling."""

from __future__ import annotations

import errno
import os
import select
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot, SLOT
from PySide6.QtDBus import QDBusConnection

from . import keys as K
from .device import G610, DeviceInfo, find_devices
from .effects import ANIMATED, EffectRenderer
from .hidpp import HidppError, HidppTimeout
from .lighting import lighting_job
from .profile import EFFECTS, Profile, Store

FRAME_MS = 40


class DeviceWorker(QObject):
    """Owns the keyboard on a background thread and reconnects when it reappears."""

    connected = Signal(object)      # DeviceInfo
    disconnected = Signal()
    activity = Signal()             # some key was pressed or released
    keysPressed = Signal(list)      # names of keys that just went down
    failed = Signal(str)
    infoRead = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._jobs: list[tuple[str | None, Callable[[G610], None]]] = []
        self._wake_r, self._wake_w = os.pipe()
        os.set_blocking(self._wake_r, False)
        self._stop = False
        self._dev: G610 | None = None
        self._kbd_fd = -1
        self._down: dict[str, set[int]] = {"boot": set(), "nkro": set()}
        self._last_activity = 0.0
        self._thread = threading.Thread(target=self._run, name="g610-device", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake()
        self._thread.join(timeout=2.0)

    def submit(self, job: Callable[[G610], None], key: str | None = None) -> None:
        """Queue work for the keyboard. A job replaces a pending one with the same key."""
        with self._lock:
            if key is not None:
                self._jobs = [j for j in self._jobs if j[0] != key]
            self._jobs.append((key, job))
        self._wake()

    def _wake(self) -> None:
        try:
            os.write(self._wake_w, b"x")
        except OSError:
            pass

    # -- thread ------------------------------------------------------------

    def _open(self) -> bool:
        devices = find_devices()
        if not devices:
            return False
        dev = None
        try:
            dev = G610(devices[0], self._on_hidpp_report)
            info = dev.read_info()
        except (OSError, HidppTimeout, HidppError):
            if dev is not None:
                dev.close()
            return False
        self._dev = dev
        self._kbd_fd = -1
        path = devices[0].get("keyboard")
        if path:
            try:
                self._kbd_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                pass
        self._down = {"boot": set(), "nkro": set()}
        self.connected.emit(info)
        return True

    def _drop(self) -> None:
        if self._dev is not None:
            self._dev.close()
            self._dev = None
        if self._kbd_fd >= 0:
            try:
                os.close(self._kbd_fd)
            except OSError:
                pass
            self._kbd_fd = -1
        with self._lock:
            self._jobs.clear()
        self.disconnected.emit()

    def _keys_changed(self, source: str, down: set[int]) -> None:
        before = self._down["boot"] | self._down["nkro"]
        self._down[source] = down
        fresh = (self._down["boot"] | self._down["nkro"]) - before
        names = [K.BY_USAGE[u] for u in fresh if u in K.BY_USAGE]
        if names:
            self.keysPressed.emit(names)
        self._note_activity()

    def _note_activity(self) -> None:
        now = time.monotonic()
        if now - self._last_activity > 0.25:
            self._last_activity = now
            self.activity.emit()

    def _on_hidpp_report(self, data: bytes) -> None:
        # The vendor interface also carries the n-key rollover and media key reports.
        if data[0] == 0x01:
            self._keys_changed("nkro", {b for b in data[1:] if b > 3})
        elif data[0] == 0x02:
            self._note_activity()

    def _read_boot_keyboard(self) -> None:
        while True:
            try:
                data = os.read(self._kbd_fd, 64)
            except BlockingIOError:
                return
            if len(data) < 8:
                return
            down = {0xE0 + bit for bit in range(8) if data[0] & (1 << bit)}
            down |= {b for b in data[2:8] if b > 3}
            self._keys_changed("boot", down)

    def _run(self) -> None:
        while not self._stop:
            if self._dev is None and not self._open():
                select.select([self._wake_r], [], [], 1.5)
                self._drain_wake()
                with self._lock:
                    self._jobs.clear()
                continue
            dev = self._dev
            fds = [self._wake_r, dev.hidpp.fd] + ([self._kbd_fd] if self._kbd_fd >= 0 else [])
            try:
                ready = select.select(fds, [], [], 2.0)[0]
                self._drain_wake()
                if dev.hidpp.fd in ready:
                    dev.hidpp.pump()
                if self._kbd_fd in ready:
                    self._read_boot_keyboard()
                if not ready and not os.path.exists(dev.paths["hidpp"]):
                    raise OSError(errno.ENODEV, "keyboard unplugged")
                while True:
                    with self._lock:
                        if not self._jobs:
                            break
                        _, job = self._jobs.pop(0)
                    try:
                        job(dev)
                    except HidppError as exc:
                        self.failed.emit(str(exc))
            except (OSError, HidppTimeout, ValueError):
                self._drop()
        if self._dev is not None:
            self._dev.close()

    def _drain_wake(self) -> None:
        try:
            while os.read(self._wake_r, 256):
                pass
        except (BlockingIOError, OSError):
            pass


class Controller(QObject):
    frame = Signal(dict)        # brightness per key, for the on-screen preview
    deviceChanged = Signal()    # connected / disconnected / info refreshed
    profilesChanged = Signal()  # active profile switched, or the list changed
    stateChanged = Signal()     # lights on/off, master brightness, sleeping
    message = Signal(str)

    def __init__(self, store: Store | None = None, parent=None):
        super().__init__(parent)
        self.store = store or Store()
        self.settings = self.store.settings
        self.info: DeviceInfo | None = None
        self.sleeping = False
        self.locked = False
        self._preview_visible = False
        self._last_activity = time.monotonic()
        self._clock0 = time.monotonic()
        self.renderer = EffectRenderer(K.LAYOUTS[self.layout_name])

        self.worker = DeviceWorker(self)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.activity.connect(self._on_activity)
        self.worker.keysPressed.connect(self._on_keys_pressed)
        self.worker.failed.connect(self.message)
        self.worker.infoRead.connect(self._on_info)

        self._anim = QTimer(self, interval=FRAME_MS)
        self._anim.timeout.connect(self._tick)
        self._idle = QTimer(self, interval=1000)
        self._idle.timeout.connect(self._check_idle)
        self._idle.start()
        self._save_timer = QTimer(self, interval=600, singleShot=True)
        self._save_timer.timeout.connect(self._save)

        QDBusConnection.sessionBus().connect(
            "", "/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged",
            self, SLOT("_on_lock_changed(bool)"))
        QDBusConnection.systemBus().connect(
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "PrepareForSleep",
            self, SLOT("_on_prepare_for_sleep(bool)"))

    def start(self) -> None:
        self.worker.start()

    def shutdown(self) -> None:
        self._save()
        self.worker.stop()

    # -- state -------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.info is not None

    @property
    def profile(self) -> Profile:
        return self.store.profiles[self.settings["active_profile"]]

    @property
    def layout_name(self) -> str:
        choice = self.settings.get("layout", "auto")
        if choice in K.LAYOUTS:
            return choice
        return self.info.layout if self.info else "ansi"

    @property
    def layout(self) -> list[K.Key]:
        return K.LAYOUTS[self.layout_name]

    @property
    def blanked(self) -> bool:
        return (not self.settings["lights_on"] or self.sleeping
                or (self.locked and self.settings["off_when_locked"]))

    def _scale(self, level: int) -> int:
        return round(level * self.settings["brightness"] / 100)

    def _now(self) -> float:
        return time.monotonic() - self._clock0

    # -- profiles ----------------------------------------------------------

    def select_profile(self, name: str) -> None:
        if name in self.store.profiles and name != self.settings["active_profile"]:
            self._save()
            self.settings["active_profile"] = name
            self.store.save_settings()
            self.renderer.reset()
            self.profilesChanged.emit()
            self.apply()

    def add_profile(self, profile: Profile) -> None:
        profile.name = self.store.unique_name(profile.name)
        self.store.profiles[profile.name] = profile
        self.store.save_profile(profile)
        self.select_profile(profile.name)

    def rename_profile(self, new_name: str) -> None:
        old = self.profile
        new_name = new_name.strip()
        if not new_name or new_name == old.name:
            return
        self._save_timer.stop()
        self.store.delete_profile(old.name)
        old.name = self.store.unique_name(new_name)
        self.store.profiles[old.name] = old
        self.store.save_profile(old)
        self.settings["active_profile"] = old.name
        self.store.save_settings()
        self.profilesChanged.emit()

    def delete_profile(self) -> None:
        if len(self.store.profiles) <= 1:
            return
        self._save_timer.stop()
        self.store.delete_profile(self.profile.name)
        self.settings["active_profile"] = next(iter(self.store.profiles))
        self.store.save_settings()
        self.profilesChanged.emit()
        self.apply()

    def profile_edited(self) -> None:
        """Call after changing the active profile: pushes it to the keyboard and saves."""
        self._save_timer.start()
        self.apply()

    def _save(self) -> None:
        self._save_timer.stop()
        self.store.save_profile(self.profile)
        self.store.save_settings()

    # -- global switches ---------------------------------------------------

    def set_setting(self, key: str, value) -> None:
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self.store.save_settings()
        if key == "layout":
            self.renderer.set_layout(self.layout)
            self.deviceChanged.emit()
        if key in ("lights_on", "brightness", "off_when_locked", "layout"):
            self.apply()
        self.stateChanged.emit()

    def set_game_keys(self, names: list[str]) -> None:
        self.settings["game_keys"] = sorted(names)
        self.store.save_settings()
        self._push_game_keys()

    def _push_game_keys(self) -> None:
        names = list(self.settings["game_keys"])
        self.worker.submit(lambda d: d.set_game_mode_keys(names), "game")

    def set_report_rate(self, interval_ms: int) -> None:
        self.settings["report_rate"] = interval_ms
        self.store.save_settings()
        self.worker.submit(lambda d: d.set_report_rate(interval_ms), "rate")
        self.refresh_info()

    def set_startup_wave(self, enabled: bool) -> None:
        self.worker.submit(lambda d: d.set_startup_wave(enabled), "startup")
        self.refresh_info()

    def refresh_info(self) -> None:
        self.worker.submit(lambda d: self.worker.infoRead.emit(d.read_info()), "info")

    # -- output ------------------------------------------------------------

    def set_preview_visible(self, visible: bool) -> None:
        self._preview_visible = visible
        self.apply(device=False)

    def preview_levels(self) -> dict[str, int]:
        """What the keyboard is showing right now, unscaled, for the preview."""
        profile = self.profile
        if profile.mode == "freestyle":
            return {k.name: profile.level(k.name) for k in self.layout}
        return self.renderer.render(profile.effect, self._now())

    def apply(self, device: bool = True, full: bool = False) -> None:
        """Bring the keyboard (and the preview) in line with the current state."""
        profile = self.profile
        kind = profile.effect.get("type", "fixed") if profile.mode == "effect" else "freestyle"
        software = kind in EFFECTS and not EFFECTS[kind]["onboard"]
        animated = kind in ANIMATED

        if self.blanked:
            self._anim.stop()
            if device:
                off = {name: 0 for name in K.ALL_KEYS}
                self.worker.submit(lambda d: d.set_keys(off, force=True), "light")
            self.frame.emit({k.name: 0 for k in self.layout})
            return

        if device and not software:
            self.worker.submit(lighting_job(profile, self.settings["brightness"], full), "light")
        if device and software and full:
            self.worker.submit(lambda d: d.forget_sent(), None)
        # Software effects always need the timer; on-board ones only to animate the preview.
        if animated and (software or self._preview_visible):
            if not self._anim.isActive():
                self._anim.start()
        else:
            self._anim.stop()
        self._tick()

    def _tick(self) -> None:
        if self.blanked:
            return
        profile = self.profile
        levels = self.preview_levels()
        self.frame.emit(levels)
        if profile.mode == "effect" and not EFFECTS[profile.effect["type"]]["onboard"]:
            scaled = {name: self._scale(level) for name, level in levels.items()}
            self.worker.submit(lambda d: d.set_keys(scaled), "light")

    # -- device events -----------------------------------------------------

    def _on_connected(self, info: DeviceInfo) -> None:
        self.info = info
        self.renderer.set_layout(self.layout)
        self.deviceChanged.emit()
        self._last_activity = time.monotonic()
        self.sleeping = False
        # Give udev's own g810-led run a moment to finish before taking over.
        QTimer.singleShot(400, self._restore_device)

    def _restore_device(self) -> None:
        if not self.connected:
            return
        self.apply(full=True)
        self._push_game_keys()
        rate = self.settings.get("report_rate")
        if rate and self.info and rate in self.info.report_rates and rate != self.info.report_rate:
            self.worker.submit(lambda d: d.set_report_rate(rate), "rate")
            self.refresh_info()

    def _on_disconnected(self) -> None:
        if self.info is not None:
            self.info = None
            self.deviceChanged.emit()

    def _on_info(self, info: DeviceInfo) -> None:
        self.info = info
        self.deviceChanged.emit()

    def _on_keys_pressed(self, names: list) -> None:
        now = self._now()
        for name in names:
            self.renderer.key_pressed(name, now)

    def _on_activity(self) -> None:
        self._last_activity = time.monotonic()
        if self.sleeping:
            self.sleeping = False
            self.stateChanged.emit()
            self.apply(full=True)

    def _check_idle(self) -> None:
        minutes = self.settings.get("sleep_minutes") or 0
        if (minutes > 0 and not self.sleeping and self.connected
                and time.monotonic() - self._last_activity > minutes * 60):
            self.sleeping = True
            self.stateChanged.emit()
            self.apply()

    @Slot(bool)
    def _on_lock_changed(self, active: bool) -> None:
        self.locked = bool(active)
        self.stateChanged.emit()
        self.apply(full=True)

    @Slot(bool)
    def _on_prepare_for_sleep(self, going_down: bool) -> None:
        if not going_down:
            # The keyboard usually loses power while suspended and forgets its lighting.
            QTimer.singleShot(1500, lambda: self.apply(full=True))
