"""Main window: sidebar, profile header and the Lighting / Game mode / Settings pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QInputDialog, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, autostart
from .. import keys as K
from ..controller import Controller
from ..profile import (DEFAULT_GAME_KEYS, EFFECTS, PERIOD_RANGE, Profile, export_g810,
                       import_g810)
from . import theme
from .keyboard_view import KeyboardView
from .widgets import LabeledSlider, Segmented, Switch, card, chip, label


def _pct(value: int) -> str:
    return f"{value}%"


class LightingPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        self.view = KeyboardView(KeyboardView.VIEW)
        ctl.frame.connect(self.view.set_levels)
        self.view.selectionChanged.connect(self._selection_changed)
        root.addWidget(self.view)

        self.mode = Segmented([("effect", "Effects"), ("freestyle", "Freestyle")])
        self.mode.changed.connect(self._set_mode)
        root.addWidget(self.mode)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_effects())
        self.stack.addWidget(self._build_freestyle())
        root.addWidget(self.stack)
        root.addStretch(1)

        QShortcut(QKeySequence.SelectAll, self, activated=self._select_all)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.view.set_selection(set()))

    # -- effects panel -----------------------------------------------------

    def _build_effects(self) -> QWidget:
        frame, layout = card()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.effect_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        for kind, spec in EFFECTS.items():
            button = QPushButton(spec["title"])
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("role", "effect")
            button.setToolTip(spec["help"])
            button.clicked.connect(lambda _=False, k=kind: self._set_effect(k))
            group.addButton(button)
            self.effect_buttons[kind] = button
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        self.effect_help = label("", "muted", wrap=True)
        layout.addWidget(self.effect_help)

        self.fx_brightness = LabeledSlider("Brightness", 0, 100, _pct)
        self.fx_background = LabeledSlider("Background", 0, 100, _pct)
        self.fx_speed = LabeledSlider("Speed", 0, 100, lambda v: "", ends=("slow", "fast"))
        self.fx_density = LabeledSlider("Density", 1, 100, _pct)
        self.fx_brightness.changed.connect(lambda v: self._set_param("brightness", round(v * 2.55)))
        self.fx_background.changed.connect(lambda v: self._set_param("background", round(v * 2.55)))
        self.fx_density.changed.connect(lambda v: self._set_param("density", v))
        self.fx_speed.changed.connect(self._set_speed)
        for slider in (self.fx_brightness, self.fx_background, self.fx_speed, self.fx_density):
            layout.addWidget(slider)

        self.fx_direction_row = QWidget()
        drow = QHBoxLayout(self.fx_direction_row)
        drow.setContentsMargins(0, 0, 0, 0)
        drow.setSpacing(12)
        caption = label("Direction")
        caption.setMinimumWidth(110)
        drow.addWidget(caption)
        self.fx_direction = Segmented([("horizontal", "Left to right"), ("vertical", "Top to bottom"),
                                       ("center", "From the centre")])
        self.fx_direction.changed.connect(lambda v: self._set_param("direction", v))
        drow.addWidget(self.fx_direction, 1)
        layout.addWidget(self.fx_direction_row)
        return frame

    def _set_effect(self, kind: str) -> None:
        effect = self.ctl.profile.effect
        if effect["type"] != kind:
            effect["type"] = kind
            if kind in PERIOD_RANGE:
                effect["period"] = PERIOD_RANGE[kind][2]
            self.ctl.renderer.reset()
            self.ctl.profile_edited()
        self.refresh()

    def _set_param(self, key: str, value) -> None:
        self.ctl.profile.effect[key] = value
        self.ctl.profile_edited()

    def _set_speed(self, value: int) -> None:
        lo, hi, _ = PERIOD_RANGE.get(self.ctl.profile.effect["type"], (1000, 10000, 3000))
        period = round(hi - (hi - lo) * value / 100)
        self.fx_speed.value_label.setText(f"{period / 1000:.1f} s")
        self._set_param("period", period)

    # -- freestyle panel ---------------------------------------------------

    def _build_freestyle(self) -> QWidget:
        frame, layout = card()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.key_brightness = LabeledSlider("Brightness", 0, 100, _pct)
        self.key_brightness.changed.connect(self._paint)
        row.addWidget(self.key_brightness, 1)
        for pct in (0, 25, 50, 75, 100):
            button = chip("Off" if pct == 0 else f"{pct}%")
            button.clicked.connect(lambda _=False, v=pct: (self.key_brightness.set_value(v), self._paint(v)))
            row.addWidget(button)
        layout.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        select_caption = label("Select")
        select_caption.setMinimumWidth(110)
        grid.addWidget(select_caption, 0, 0)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text, handler in (("All", self._select_all),
                              ("None", lambda: self.view.set_selection(set())),
                              ("Invert", self._invert)):
            button = chip(text)
            button.clicked.connect(handler)
            chips.addWidget(button)
        chips.addSpacing(10)
        for title, names in K.PRESET_SELECTIONS:
            button = chip(title)
            button.clicked.connect(lambda _=False, n=names: self.view.set_selection(n))
            chips.addWidget(button)
        chips.addStretch(1)
        grid.addLayout(chips, 0, 1)
        grid.addWidget(label("Zones"), 1, 0)
        zones = QHBoxLayout()
        zones.setSpacing(6)
        for zone, title in K.ZONES:
            button = chip(title)
            button.clicked.connect(lambda _=False, z=zone: self._select_zone(z))
            zones.addWidget(button)
        zones.addStretch(1)
        grid.addLayout(zones, 1, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self.selection_label = label("", "caption", wrap=True)
        layout.addWidget(self.selection_label)
        return frame

    def _select_all(self) -> None:
        if self.ctl.profile.mode == "freestyle":
            self.view.set_selection({k.name for k in self.view.keys})

    def _invert(self) -> None:
        self.view.set_selection({k.name for k in self.view.keys} - self.view.selected)

    def _select_zone(self, zone: str) -> None:
        self.view.set_selection({k.name for k in self.view.keys if k.zone == zone})

    def _selection_changed(self) -> None:
        selected = self.view.selected
        profile = self.ctl.profile
        self.key_brightness.setEnabled(bool(selected))
        if selected:
            values = {profile.level(n) for n in selected}
            self.key_brightness.set_value(round(max(values) / 2.55))
            mixed = "  (mixed brightness)" if len(values) > 1 else ""
            self.selection_label.setText(
                f"{len(selected)} key{'s' if len(selected) != 1 else ''} selected{mixed}. "
                "Move the slider to set their brightness.")
        else:
            self.selection_label.setText(
                "Click a key or drag across several, then set their brightness. "
                "Ctrl+click adds keys, double-click selects a whole zone, Ctrl+A selects everything.")

    def _paint(self, pct: int) -> None:
        profile = self.ctl.profile
        if profile.mode != "freestyle" or not self.view.selected:
            return
        level = round(pct * 2.55)
        for name in self.view.selected:
            profile.keys[name] = level
        self._selection_changed()
        self.ctl.profile_edited()

    # -- shared ------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        profile = self.ctl.profile
        if profile.mode != mode:
            if mode == "freestyle" and not profile.keys:
                start = int(profile.effect.get("brightness", 255))
                profile.keys = {name: start for name in K.ALL_KEYS}
            profile.mode = mode
            self.ctl.renderer.reset()
            self.ctl.profile_edited()
        self.refresh()

    def refresh(self) -> None:
        """Bring every control in line with the active profile."""
        profile = self.ctl.profile
        effect = profile.effect
        freestyle = profile.mode == "freestyle"
        self.view.set_keys(self.ctl.layout)
        self.view.mode = KeyboardView.SELECT if freestyle else KeyboardView.VIEW
        if not freestyle:
            self.view.set_selection(set())
        self.mode.set_value(profile.mode)
        self.stack.setCurrentIndex(1 if freestyle else 0)

        kind = effect["type"]
        self.effect_buttons[kind].setChecked(True)
        spec = EFFECTS[kind]
        self.effect_help.setText(spec["help"])
        params = spec["params"]
        self.fx_brightness.set_value(round(effect["brightness"] / 2.55))
        self.fx_background.set_value(round(effect["background"] / 2.55))
        self.fx_density.set_value(effect["density"])
        self.fx_direction.set_value(effect["direction"])
        lo, hi, _ = PERIOD_RANGE.get(kind, (1000, 10000, 3000))
        period = max(lo, min(hi, effect["period"]))
        self.fx_speed.set_value(round((hi - period) * 100 / (hi - lo)))
        self.fx_speed.value_label.setText(f"{period / 1000:.1f} s")
        self.fx_background.setVisible("background" in params)
        self.fx_speed.setVisible("period" in params)
        self.fx_density.setVisible("density" in params)
        self.fx_direction_row.setVisible("direction" in params)
        self._selection_changed()
        self.view.set_levels(self.ctl.preview_levels() if not self.ctl.blanked else {})


class GameModePage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        self.view = KeyboardView(KeyboardView.TOGGLE)
        self.view.markedChanged.connect(self._changed)
        root.addWidget(self.view)

        frame, layout = card()
        layout.addWidget(label("Game mode", "heading"))
        layout.addWidget(label(
            "Press the game mode button on the keyboard (next to the brightness button) to switch "
            "game mode on or off. While it is on, the keys marked here do nothing, so a stray "
            "press cannot throw you out of a game. Click keys above to mark or unmark them.",
            "muted", wrap=True))
        row = QHBoxLayout()
        self.count = label("", "muted")
        row.addWidget(self.count)
        row.addStretch(1)
        for text, names in (("Windows key only", DEFAULT_GAME_KEYS),
                            ("Windows + Menu + Caps Lock", DEFAULT_GAME_KEYS + ["menu", "caps_lock"]),
                            ("Disable nothing", [])):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, n=names: self._preset(n))
            row.addWidget(button)
        layout.addLayout(row)
        self.note = label("", "caption", wrap=True)
        layout.addWidget(self.note)
        root.addWidget(frame)
        root.addStretch(1)

    def _preset(self, names: list[str]) -> None:
        self.view.set_marked(names)
        self._changed()

    def _changed(self) -> None:
        self.ctl.set_game_keys(sorted(self.view.marked))
        self._update_count()

    def _update_count(self) -> None:
        n = len(self.view.marked)
        self.count.setText("No keys are disabled in game mode" if n == 0 else
                           f"{n} key{'s' if n != 1 else ''} disabled in game mode")

    def refresh(self) -> None:
        self.view.set_keys(self.ctl.layout)
        self.view.set_levels({k.name: 120 for k in self.ctl.layout})
        self.view.set_marked(self.ctl.settings["game_keys"])
        self._update_count()
        info = self.ctl.info
        if info is None:
            self.note.setText("The keyboard is not connected; changes are sent when it is back.")
        elif not info.game_mode_supported:
            self.note.setText("This keyboard does not report support for choosing game mode keys.")
        else:
            self.note.setText("G610 Control sends this list to the keyboard again every time "
                              "it connects.")


class SettingsPage(QScrollArea):
    def __init__(self, ctl: Controller, window: "MainWindow"):
        super().__init__()
        self.ctl = ctl
        self.window_ = window
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Device
        frame, layout = card()
        layout.addWidget(label("Keyboard", "heading"))
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(8)
        self.dev_fields = {}
        for key, title in (("name", "Model"), ("serial", "Serial number"),
                           ("firmware", "Firmware"), ("bootloader", "Bootloader")):
            value = label("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.dev_fields[key] = value
            form.addRow(label(title, "muted"), value)
        layout.addLayout(form)
        root.addWidget(frame)

        # Hardware settings
        frame, layout = card()
        layout.addWidget(label("Hardware settings", "heading"))
        self.startup = QComboBox()
        self.startup.addItem("Steady light", False)
        self.startup.addItem("Light wave animation", True)
        self.startup.activated.connect(lambda _: ctl.set_startup_wave(self.startup.currentData()))
        layout.addLayout(self._row(
            "When the keyboard powers on",
            "What the keyboard shows by itself before this app takes over. Stored in the keyboard.",
            self.startup))
        self.rate = QComboBox()
        self.rate.activated.connect(lambda _: ctl.set_report_rate(self.rate.currentData()))
        layout.addLayout(self._row(
            "Polling rate",
            "How often the keyboard reports key presses to the computer. 1000 Hz is the default.",
            self.rate))
        self.layout_box = QComboBox()
        for value, text in (("auto", "Detect automatically"), ("ansi", "ANSI (US)"), ("iso", "ISO (European)")):
            self.layout_box.addItem(text, value)
        self.layout_box.activated.connect(lambda _: ctl.set_setting("layout", self.layout_box.currentData()))
        layout.addLayout(self._row("Key layout", "The physical shape of the keyboard drawn in this app.",
                                   self.layout_box))
        root.addWidget(frame)

        # Power
        frame, layout = card()
        layout.addWidget(label("Lighting sleep", "heading"))
        self.sleep = QComboBox()
        for minutes in (0, 1, 2, 5, 10, 15, 30, 60):
            self.sleep.addItem("Never" if minutes == 0 else f"After {minutes} min", minutes)
        self.sleep.activated.connect(lambda _: ctl.set_setting("sleep_minutes", self.sleep.currentData()))
        layout.addLayout(self._row(
            "Turn the lights off when idle",
            "Counts time since the last key press on this keyboard; any key wakes it. "
            "Mouse movement is not seen.", self.sleep))
        self.lock = Switch()
        self.lock.toggled.connect(lambda on: ctl.set_setting("off_when_locked", on))
        layout.addLayout(self._row("Lights off while the screen is locked", "", self.lock))
        root.addWidget(frame)

        # Application
        frame, layout = card()
        layout.addWidget(label("Application", "heading"))
        self.autostart = Switch()
        self.autostart.toggled.connect(self._set_autostart)
        layout.addLayout(self._row(
            "Start at login",
            "Starts hidden in the system tray and restores your lighting. Software effects, "
            "the sleep timer and game mode keys need the app running.", self.autostart))
        self.tray = Switch()
        self.tray.toggled.connect(lambda on: ctl.set_setting("close_to_tray", on))
        layout.addLayout(self._row("Keep running in the tray when the window is closed", "", self.tray))
        root.addWidget(frame)

        # Profiles
        frame, layout = card()
        layout.addWidget(label("g810-led profiles", "heading"))
        layout.addWidget(label(
            "Import a g810-led profile file, or export the current look so g810-led can apply it "
            "at boot before you log in (copy the file to /etc/g810-led/profile).", "muted", wrap=True))
        row = QHBoxLayout()
        import_button = QPushButton("Import profile…")
        import_button.clicked.connect(window.import_profile)
        export_button = QPushButton("Export current profile…")
        export_button.clicked.connect(window.export_profile)
        row.addWidget(import_button)
        row.addWidget(export_button)
        row.addStretch(1)
        layout.addLayout(row)
        root.addWidget(frame)

        root.addWidget(label(f"{APP_NAME} {__version__}  •  not affiliated with Logitech", "caption"))
        root.addStretch(1)

    @staticmethod
    def _row(title: str, help_text: str, control: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title))
        if help_text:
            text.addWidget(label(help_text, "caption", wrap=True))
        row.addLayout(text, 1)
        row.addWidget(control, 0, Qt.AlignVCenter)
        return row

    def _set_autostart(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not change the autostart entry:\n{exc}")
        self.refresh()

    def refresh(self) -> None:
        ctl, info = self.ctl, self.ctl.info
        for key, widget in self.dev_fields.items():
            widget.setText((getattr(info, key) or "—") if info else "Not connected")

        self.startup.setEnabled(bool(info and info.startup_wave is not None))
        if info and info.startup_wave is not None:
            self.startup.setCurrentIndex(1 if info.startup_wave else 0)
        self.rate.clear()
        if info and info.report_rates:
            for interval in info.report_rates:
                self.rate.addItem(f"{1000 // interval} Hz", interval)
            self.rate.setCurrentIndex(max(0, self.rate.findData(info.report_rate)))
        self.rate.setEnabled(bool(info and info.report_rates))
        self.layout_box.setCurrentIndex(self.layout_box.findData(ctl.settings["layout"]))
        self.sleep.setCurrentIndex(max(0, self.sleep.findData(ctl.settings["sleep_minutes"])))
        for switch, value in ((self.lock, ctl.settings["off_when_locked"]),
                              (self.tray, ctl.settings["close_to_tray"]),
                              (self.autostart, autostart.is_enabled())):
            switch.blockSignals(True)
            switch.setChecked(bool(value))
            switch.blockSignals(False)


class MainWindow(QMainWindow):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.force_quit = False
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 860)
        self.setMinimumSize(1080, 720)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sidebar
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 20, 14, 16)
        side.setSpacing(6)
        side.addWidget(label("G610", "title"))
        side.addWidget(label("Control", "muted"))
        side.addSpacing(18)
        self.nav = QButtonGroup(self)
        self.pages = QStackedWidget()
        self.lighting = LightingPage(ctl)
        self.game = GameModePage(ctl)
        self.settings_page = SettingsPage(ctl, self)
        for index, (title, page) in enumerate((("Lighting", self.lighting), ("Game mode", self.game),
                                               ("Settings", self.settings_page))):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("role", "nav")
            button.clicked.connect(lambda _=False, i=index: self._show_page(i))
            self.nav.addButton(button, index)
            side.addWidget(button)
            self.pages.addWidget(page)
        self.nav.button(0).setChecked(True)
        side.addStretch(1)
        self.status = label("", wrap=True)
        self.status_detail = label("", "caption", wrap=True)
        side.addWidget(self.status)
        side.addWidget(self.status_detail)
        outer.addWidget(sidebar)

        # Header + pages
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        header = QFrame(objectName="header")
        head = QHBoxLayout(header)
        head.setContentsMargins(24, 12, 24, 12)
        head.setSpacing(10)
        head.addWidget(label("Profile", "muted"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(190)
        self.profile_box.activated.connect(lambda _: ctl.select_profile(self.profile_box.currentText()))
        head.addWidget(self.profile_box)
        menu_button = QPushButton("Manage")
        menu = QMenu(menu_button)
        menu.addAction("New profile…", self.new_profile)
        menu.addAction("Duplicate…", self.duplicate_profile)
        menu.addAction("Rename…", self.rename_profile)
        self.delete_action = menu.addAction("Delete", self.delete_profile)
        menu.addSeparator()
        menu.addAction("Import g810-led profile…", self.import_profile)
        menu.addAction("Export as g810-led profile…", self.export_profile)
        menu_button.setMenu(menu)
        head.addWidget(menu_button)
        head.addStretch(1)
        self.master = LabeledSlider("Brightness", 5, 100, _pct)
        self.master.caption.setMinimumWidth(0)
        self.master.caption.setProperty("role", "muted")
        self.master.setFixedWidth(300)
        self.master.changed.connect(lambda v: ctl.set_setting("brightness", v))
        head.addWidget(self.master)
        head.addSpacing(8)
        head.addWidget(label("Lights", "muted"))
        self.power = Switch()
        self.power.toggled.connect(lambda on: ctl.set_setting("lights_on", on))
        head.addWidget(self.power)
        right.addWidget(header)
        right.addWidget(self.pages, 1)
        outer.addLayout(right, 1)

        self._message_timer = QTimer(self, interval=6000, singleShot=True)
        self._message_timer.timeout.connect(self._refresh_status)
        ctl.deviceChanged.connect(self.refresh)
        ctl.profilesChanged.connect(self.refresh)
        ctl.stateChanged.connect(self._refresh_state)
        ctl.message.connect(self._show_message)
        self.refresh()

    # -- refresh -----------------------------------------------------------

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.pages.currentWidget().refresh()

    def refresh(self) -> None:
        ctl = self.ctl
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        self.profile_box.addItems(list(ctl.store.profiles))
        self.profile_box.setCurrentText(ctl.profile.name)
        self.profile_box.blockSignals(False)
        self.delete_action.setEnabled(len(ctl.store.profiles) > 1)
        self.lighting.refresh()
        self.game.refresh()
        self.settings_page.refresh()
        self._refresh_state()

    def _refresh_state(self) -> None:
        ctl = self.ctl
        self.master.set_value(ctl.settings["brightness"])
        self.power.blockSignals(True)
        self.power.setChecked(ctl.settings["lights_on"])
        self.power.blockSignals(False)
        if ctl.blanked:
            self.lighting.view.set_levels({})
        self._refresh_status()

    def _refresh_status(self) -> None:
        ctl = self.ctl
        if ctl.connected:
            self.status.setText(f"<span style='color:{theme.OK}'>●</span>  Connected")
            if not ctl.settings["lights_on"]:
                detail = "Lights are switched off"
            elif ctl.sleeping:
                detail = "Lights asleep – press a key"
            elif ctl.locked and ctl.settings["off_when_locked"]:
                detail = "Lights off while locked"
            else:
                detail = ctl.info.name.replace("Logitech ", "")
        else:
            self.status.setText(f"<span style='color:{theme.DANGER}'>●</span>  Not connected")
            detail = "Plug in the G610; it is picked up automatically."
        self.status_detail.setText(detail)

    def _show_message(self, text: str) -> None:
        self.status_detail.setText(text)
        self._message_timer.start()

    # -- profile actions ---------------------------------------------------

    def _ask_name(self, title: str, initial: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, "Profile name:", text=initial)
        name = name.strip()
        return name if ok and name else None

    def new_profile(self) -> None:
        name = self._ask_name("New profile", "New profile")
        if name:
            self.ctl.add_profile(Profile(name))

    def duplicate_profile(self) -> None:
        name = self._ask_name("Duplicate profile", f"{self.ctl.profile.name} copy")
        if name:
            self.ctl.add_profile(self.ctl.profile.copy(name))

    def rename_profile(self) -> None:
        name = self._ask_name("Rename profile", self.ctl.profile.name)
        if name:
            self.ctl.rename_profile(name)

    def delete_profile(self) -> None:
        name = self.ctl.profile.name
        if QMessageBox.question(self, "Delete profile", f"Delete the profile “{name}”?") \
                == QMessageBox.Yes:
            self.ctl.delete_profile()

    def import_profile(self) -> None:
        start = "/etc/g810-led" if Path("/etc/g810-led").is_dir() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Import g810-led profile", start)
        if not path:
            return
        try:
            text = Path(path).read_text(errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not read the file:\n{exc}")
            return
        self.ctl.add_profile(import_g810(text, Path(path).stem.replace("_", " ").title() or "Imported"))

    def export_profile(self) -> None:
        profile = self.ctl.profile
        suggested = str(Path.home() / f"{profile.name.lower().replace(' ', '_')}.g810")
        path, _ = QFileDialog.getSaveFileName(self, "Export as g810-led profile", suggested)
        if not path:
            return
        try:
            Path(path).write_text(export_g810(profile, self.ctl.settings["brightness"]))
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not write the file:\n{exc}")
            return
        self._show_message("Profile exported")

    # -- window ------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.ctl.set_preview_visible(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.ctl.set_preview_visible(False)

    def closeEvent(self, event) -> None:
        if not self.force_quit and self.ctl.settings["close_to_tray"] and self.property("has_tray"):
            event.ignore()
            self.hide()
        else:
            event.accept()
