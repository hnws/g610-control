"""Logitech G610 driver: lighting, effects, game mode, polling rate, device info.

The feature and effect indexes are discovered from the keyboard instead of
being hard-coded, because they differ between models (g810-led's fixed table
is wrong for the G610: it has no colour cycle, and has starlight and ripple).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from . import keys as K
from .hidpp import Hidpp, HidppError, HidppTimeout

VENDOR_ID = 0x046D
PRODUCT_IDS = (0xC338, 0xC333)

FEAT_FIRMWARE = 0x0003
FEAT_NAME = 0x0005
FEAT_DISABLE_KEYS = 0x4522   # keys switched off while game mode is on
FEAT_LAYOUT = 0x4540
FEAT_REPORT_RATE = 0x8060
FEAT_EFFECTS = 0x8070        # on-board lighting effects, per zone
FEAT_PER_KEY = 0x8080        # per-key brightness

ZONE_KEYS = 0x0001
ZONE_LOGO = 0x0002

FX_OFF = 0x0000
FX_FIXED = 0x0001
FX_WAVE = 0x0004
FX_STARLIGHT = 0x0005
FX_BREATHING = 0x000A
FX_RIPPLE = 0x000B

WAVE_DIRECTIONS = {"horizontal": 1, "vertical": 2, "center": 3}

NV_BOOT_EFFECT = 0x0001


@dataclass
class DeviceInfo:
    name: str = "Logitech G610"
    serial: str = ""
    product_id: int = 0
    firmware: str = ""
    bootloader: str = ""
    layout_code: int | None = None
    report_rates: list[int] = field(default_factory=list)  # in ms
    report_rate: int | None = None
    startup_wave: bool | None = None
    effects: dict[int, list[int]] = field(default_factory=dict)  # zone -> effect ids
    game_mode_supported: bool = False

    @property
    def layout(self) -> str:
        # 0x4540 reports 1 for the US layout; everything else is an ISO-shaped board.
        return "ansi" if self.layout_code in (None, 0, 1) else "iso"


def find_devices() -> list[dict]:
    """Connected G610 keyboards as {serial, product_id, hidpp, keyboard} hidraw paths."""
    found: dict[str, dict] = {}
    for sys_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(sys_path, "device", "uevent")) as fh:
                props = dict(line.strip().split("=", 1) for line in fh if "=" in line)
            bus, vid, pid = (int(x, 16) for x in props["HID_ID"].split(":"))
            if vid != VENDOR_ID or pid not in PRODUCT_IDS:
                continue
            with open(os.path.join(sys_path, "device", "report_descriptor"), "rb") as fh:
                descriptor = fh.read()
        except (OSError, KeyError, ValueError):
            continue
        ident = props.get("HID_UNIQ") or props.get("HID_PHYS", "").split("/")[0]
        entry = found.setdefault(ident, {"serial": props.get("HID_UNIQ", ""), "product_id": pid})
        node = "/dev/" + os.path.basename(sys_path)
        # The vendor interface carries usage page 0xFF43; the other one is the plain keyboard.
        entry["hidpp" if b"\x06\x43\xff" in descriptor else "keyboard"] = node
    return [d for d in found.values() if "hidpp" in d]


def _bcd(value: int) -> str:
    return f"{value:02x}"


class G610:
    def __init__(self, paths: dict, on_report=None):
        self.paths = paths
        self.hidpp = Hidpp(paths["hidpp"], on_report)
        self._sent: dict[str, int] = {}
        self._effect_index: dict[int, dict[int, int]] = {}  # zone -> effect id -> index
        self._zone_index: dict[int, int] = {}
        self._features_loaded = False

    @classmethod
    def open_first(cls, on_report=None) -> "G610":
        devices = find_devices()
        if not devices:
            raise FileNotFoundError("No Logitech G610 keyboard found")
        return cls(devices[0], on_report)

    def close(self) -> None:
        self.hidpp.close()

    def _feat(self, feature_id: int) -> int:
        index = self.hidpp.feature_index(feature_id)
        if index is None:
            raise HidppError(0, 0, 9)
        return index

    # -- information -------------------------------------------------------

    def _load_effects(self) -> None:
        if self._features_loaded:
            return
        fx = self._feat(FEAT_EFFECTS)
        zone_count = self.hidpp.request(fx, 0)[0]
        for z in range(zone_count):
            info = self.hidpp.request(fx, 1, bytes([z]))
            location = (info[1] << 8) | info[2]
            self._zone_index[location] = z
            table: dict[int, int] = {}
            for e in range(info[3]):
                r = self.hidpp.request(fx, 2, bytes([z, e]))
                table[(r[2] << 8) | r[3]] = e
            self._effect_index[location] = table
        self._features_loaded = True

    def read_info(self) -> DeviceInfo:
        info = DeviceInfo(serial=self.paths.get("serial", ""),
                          product_id=self.paths.get("product_id", 0))
        h = self.hidpp
        try:
            idx = self._feat(FEAT_NAME)
            length = h.request(idx, 0)[0]
            name = b""
            while len(name) < length:
                chunk = h.request(idx, 1, bytes([len(name)]))
                name += chunk[:length - len(name)]
            info.name = name.decode("ascii", "replace").strip("\0 ")
        except (HidppError, HidppTimeout):
            pass
        try:
            idx = self._feat(FEAT_FIRMWARE)
            for entity in range(h.request(idx, 0)[0]):
                r = h.request(idx, 1, bytes([entity]))
                version = f"{_bcd(r[4])}.{_bcd(r[5])} build {_bcd(r[6])}{_bcd(r[7])}"
                if r[0] == 0:
                    info.firmware = version
                elif r[0] == 1:
                    info.bootloader = version
        except (HidppError, HidppTimeout):
            pass
        try:
            info.layout_code = h.request(self._feat(FEAT_LAYOUT), 0)[0]
        except (HidppError, HidppTimeout):
            pass
        try:
            idx = self._feat(FEAT_REPORT_RATE)
            mask = h.request(idx, 0)[0]
            info.report_rates = [bit + 1 for bit in range(8) if mask & (1 << bit)]
            info.report_rate = h.request(idx, 1)[0]
        except (HidppError, HidppTimeout):
            pass
        try:
            info.startup_wave = self.get_startup_wave()
            self._load_effects()
            info.effects = {zone: sorted(t) for zone, t in self._effect_index.items()}
        except (HidppError, HidppTimeout):
            pass
        info.game_mode_supported = h.feature_index(FEAT_DISABLE_KEYS) is not None
        return info

    # -- per-key lighting --------------------------------------------------

    def forget_sent(self) -> None:
        """Drop the cache of what the keyboard is showing, forcing a full resend."""
        self._sent.clear()

    def set_keys(self, levels: dict[str, int], force: bool = False) -> int:
        """Set per-key brightness (0-255). Only changed keys are sent. Returns packets sent."""
        groups: dict[int, list[tuple[int, int]]] = {}
        for name, level in levels.items():
            key = K.ALL_KEYS.get(name)
            if key is None:
                continue
            level = max(0, min(255, int(level)))
            if not force and self._sent.get(name) == level:
                continue
            groups.setdefault(key.addr, []).append((key.code, level))
            self._sent[name] = level
        if not groups:
            return 0
        feat = self._feat(FEAT_PER_KEY)
        packets = 0
        for addr, items in groups.items():
            # g810-led sends the logo in a 20 byte report and everything else in 64.
            very_long = addr != K.ADDR_LOGO
            per_packet = 14 if very_long else 3
            for i in range(0, len(items), per_packet):
                chunk = items[i:i + per_packet]
                params = bytes([0x00, addr, 0x00, len(chunk)])
                for code, level in chunk:
                    params += bytes([code, level, level, level])
                self.hidpp.request(feat, 3, params, very_long=very_long)
                packets += 1
        self.hidpp.request(feat, 5)  # commit
        return packets + 1

    # -- on-board effects --------------------------------------------------

    def supports_effect(self, effect_id: int, zone: int = ZONE_KEYS) -> bool:
        self._load_effects()
        return effect_id in self._effect_index.get(zone, {})

    def set_zone_effect(self, zone: int, effect_id: int, params: bytes = b"") -> bool:
        """Start an on-board effect on a zone. False when the zone can't do it."""
        self._load_effects()
        index = self._effect_index.get(zone, {}).get(effect_id)
        if index is None:
            return False
        payload = bytes([self._zone_index[zone], index]) + bytes(params).ljust(10, b"\0") + b"\0"
        self.hidpp.request(self._feat(FEAT_EFFECTS), 3, payload)
        if zone == ZONE_KEYS:
            # The effect now owns the keys; whatever we cached is no longer shown.
            for name, key in K.ALL_KEYS.items():
                if key.addr in (K.ADDR_KEYS, K.ADDR_MEDIA):
                    self._sent.pop(name, None)
        else:
            self._sent.pop("logo", None)
        return True

    def raw_zone_effect(self, zone_index: int, effect_index: int, params: bytes) -> None:
        payload = bytes([zone_index, effect_index]) + bytes(params).ljust(11, b"\0")
        self.hidpp.request(self._feat(FEAT_EFFECTS), 3, payload[:16])
        self.forget_sent()

    def effect_off(self, zone: int) -> bool:
        return self.set_zone_effect(zone, FX_OFF)

    def effect_fixed(self, zone: int, level: int) -> bool:
        return self.set_zone_effect(zone, FX_FIXED, bytes([level, level, level, 0]))

    def effect_breathing(self, zone: int, level: int, period_ms: int) -> bool:
        p = max(100, min(0xFFFF, int(period_ms)))
        return self.set_zone_effect(
            zone, FX_BREATHING, bytes([level, level, level, p >> 8, p & 0xFF, 0, 0]))

    def effect_wave(self, level: int, period_ms: int, direction: str) -> bool:
        # Layout taken from g810-led, where it is verified on the G810: period low
        # byte at 6, direction at 7, intensity (percent) at 8, period high byte at 9.
        p = max(100, min(0xFFFF, int(period_ms)))
        intensity = max(1, min(100, round(level * 100 / 255)))
        params = bytes([level, level, level, 0, 0, p >> 8, p & 0xFF,
                        WAVE_DIRECTIONS.get(direction, 1), intensity, p >> 8])
        return self.set_zone_effect(ZONE_KEYS, FX_WAVE, params)

    def effect_ripple(self, level: int, period_ms: int) -> bool:
        p = max(1, min(0xFFFF, int(period_ms)))
        return self.set_zone_effect(
            ZONE_KEYS, FX_RIPPLE, bytes([level, level, level, 0, p >> 8, p & 0xFF]))

    def effect_starlight(self, sky: int, star: int) -> bool:
        return self.set_zone_effect(
            ZONE_KEYS, FX_STARLIGHT, bytes([sky, sky, sky, star, star, star]))

    # -- power-on behaviour ------------------------------------------------

    def get_startup_wave(self) -> bool:
        r = self.hidpp.request(self._feat(FEAT_EFFECTS), 4,
                               bytes([NV_BOOT_EFFECT >> 8, NV_BOOT_EFFECT & 0xFF]))
        return r[2] == 1

    def set_startup_wave(self, enabled: bool) -> None:
        self.hidpp.request(self._feat(FEAT_EFFECTS), 5,
                           bytes([NV_BOOT_EFFECT >> 8, NV_BOOT_EFFECT & 0xFF, 1 if enabled else 2]))

    # -- polling rate ------------------------------------------------------

    def get_report_rate(self) -> int:
        return self.hidpp.request(self._feat(FEAT_REPORT_RATE), 1)[0]

    def set_report_rate(self, interval_ms: int) -> None:
        self.hidpp.request(self._feat(FEAT_REPORT_RATE), 2, bytes([interval_ms]))

    # -- game mode ---------------------------------------------------------

    def set_game_mode_keys(self, names: list[str]) -> None:
        """Choose which keys the keyboard ignores while its game mode is on."""
        feat = self._feat(FEAT_DISABLE_KEYS)
        usages = sorted({K.ALL_KEYS[n].code for n in names
                         if n in K.ALL_KEYS and K.ALL_KEYS[n].usage is not None})
        self.hidpp.request(feat, 3)  # enable all keys
        for i in range(0, len(usages), 16):
            self.hidpp.request(feat, 1, bytes(usages[i:i + 16]))
