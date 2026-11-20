"""Key table for the Logitech G610: names, LED addresses and on-screen geometry.

Key names follow g810-led so its profile files can be imported and exported.
Geometry is in key units (1.0 = one standard key), origin at the Esc key.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# LED address groups used by HID++ feature 0x8080 (per-key lighting).
ADDR_KEYS = 0x01
ADDR_MEDIA = 0x02
ADDR_LOGO = 0x10
ADDR_INDICATORS = 0x40

# The G610 has Fn where right Win usually is. Its LED answers to the right Win
# address, but the key is handled inside the keyboard and sends nothing.
NO_USAGE = {"win_right"}


@dataclass(frozen=True)
class Key:
    name: str
    label: str
    zone: str
    addr: int
    code: int
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0
    shape: str = "rect"  # rect | round | led

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def usage(self) -> int | None:
        """USB HID keyboard usage, for keys that send one."""
        if self.addr != ADDR_KEYS or self.name in NO_USAGE:
            return None
        return self.code


def _usages() -> dict[str, int]:
    table: dict[str, int] = {}
    for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
        table[ch] = 0x04 + i
    for i, ch in enumerate("123456789"):
        table[ch] = 0x1E + i
    table["0"] = 0x27
    ordered = [
        "enter", "escape", "backspace", "tab", "space", "minus", "equal",
        "open_bracket", "close_bracket", "backslash", "dollar", "semicolon",
        "quote", "tilde", "comma", "period", "slash", "caps_lock",
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
        "print_screen", "scroll_lock", "pause_break", "insert", "home", "page_up",
        "delete", "end", "page_down", "arrow_right", "arrow_left", "arrow_bottom",
        "arrow_top", "num_lock", "num_slash", "num_asterisk", "num_minus",
        "num_plus", "numenter", "num1", "num2", "num3", "num4", "num5", "num6",
        "num7", "num8", "num9", "num0", "num_dot", "intl_backslash", "menu",
    ]
    for i, name in enumerate(ordered):
        table[name] = 0x28 + i
    for i, name in enumerate([
        "ctrl_left", "shift_left", "alt_left", "win_left",
        "ctrl_right", "shift_right", "alt_right", "win_right",
    ]):
        table[name] = 0xE0 + i
    return table


USAGES = _usages()

_ZONES = {
    "fkeys": [f"f{i}" for i in range(1, 13)],
    "modifiers": ["shift_left", "ctrl_left", "win_left", "alt_left", "alt_right",
                  "win_right", "menu", "ctrl_right", "shift_right"],
    "arrows": ["arrow_top", "arrow_left", "arrow_bottom", "arrow_right"],
    "numeric": ["num_lock", "num_slash", "num_asterisk", "num_minus", "num_plus",
                "numenter", "num_dot"] + [f"num{i}" for i in range(10)],
    "functions": ["escape", "print_screen", "scroll_lock", "pause_break", "insert",
                  "home", "page_up", "delete", "end", "page_down"],
}
_ZONE_OF = {name: zone for zone, names in _ZONES.items() for name in names}

# (name, label, width). A bare number is a horizontal gap.
_R0 = [("escape", "Esc", 1), 1, ("f1", "F1", 1), ("f2", "F2", 1), ("f3", "F3", 1),
       ("f4", "F4", 1), 0.5, ("f5", "F5", 1), ("f6", "F6", 1), ("f7", "F7", 1),
       ("f8", "F8", 1), 0.5, ("f9", "F9", 1), ("f10", "F10", 1), ("f11", "F11", 1),
       ("f12", "F12", 1), 0.25, ("print_screen", "PrtSc", 1),
       ("scroll_lock", "ScrLk", 1), ("pause_break", "Pause", 1)]
_R1 = [("tilde", "`", 1)] + [(c, c, 1) for c in "1234567890"] + [
       ("minus", "-", 1), ("equal", "=", 1), ("backspace", "Backspace", 2), 0.25,
       ("insert", "Ins", 1), ("home", "Home", 1), ("page_up", "PgUp", 1), 0.25,
       ("num_lock", "Num", 1), ("num_slash", "/", 1), ("num_asterisk", "*", 1),
       ("num_minus", "-", 1)]
_R2 = [("tab", "Tab", 1.5)] + [(c, c.upper(), 1) for c in "qwertyuiop"] + [
       ("open_bracket", "[", 1), ("close_bracket", "]", 1), ("backslash", "\\", 1.5),
       0.25, ("delete", "Del", 1), ("end", "End", 1), ("page_down", "PgDn", 1), 0.25,
       ("num7", "7", 1), ("num8", "8", 1), ("num9", "9", 1)]
_R3 = [("caps_lock", "Caps", 1.75)] + [(c, c.upper(), 1) for c in "asdfghjkl"] + [
       ("semicolon", ";", 1), ("quote", "'", 1), ("enter", "Enter", 2.25), 3.5,
       ("num4", "4", 1), ("num5", "5", 1), ("num6", "6", 1)]
_R4 = [("shift_left", "Shift", 2.25)] + [(c, c.upper(), 1) for c in "zxcvbnm"] + [
       ("comma", ",", 1), ("period", ".", 1), ("slash", "/", 1),
       ("shift_right", "Shift", 2.75), 1.25, ("arrow_top", "↑", 1), 1.25,
       ("num1", "1", 1), ("num2", "2", 1), ("num3", "3", 1)]
_R5 = [("ctrl_left", "Ctrl", 1.25), ("win_left", "Win", 1.25), ("alt_left", "Alt", 1.25),
       ("space", "", 6.25), ("alt_right", "Alt", 1.25), ("win_right", "Fn", 1.25),
       ("menu", "Menu", 1.25), ("ctrl_right", "Ctrl", 1.25), 0.25,
       ("arrow_left", "←", 1), ("arrow_bottom", "↓", 1),
       ("arrow_right", "→", 1), 0.25, ("num0", "0", 2), ("num_dot", ".", 1)]
_ROWS = [(0.0, _R0), (1.25, _R1), (2.25, _R2), (3.25, _R3), (4.25, _R4), (5.25, _R5)]

TOP_Y = -1.3


def _build_ansi() -> list[Key]:
    keys: list[Key] = []
    for y, row in _ROWS:
        x = 0.0
        for item in row:
            if isinstance(item, (int, float)):
                x += item
                continue
            name, label, w = item
            keys.append(Key(name, label, _ZONE_OF.get(name, "keys"), ADDR_KEYS,
                            USAGES[name], x, y, w))
            x += w
    keys.append(Key("num_plus", "+", "numeric", ADDR_KEYS, USAGES["num_plus"], 21.5, 2.25, 1, 2))
    keys.append(Key("numenter", "Ent", "numeric", ADDR_KEYS, USAGES["numenter"], 21.5, 4.25, 1, 2))

    # Strip above the main block: logo, the two round buttons, status LEDs, media keys.
    keys.append(Key("logo", "G", "logo", ADDR_LOGO, 0x01, 0.0, TOP_Y, 1, 1, "round"))
    keys.append(Key("game_mode", "Game", "indicators", ADDR_INDICATORS, 0x02, 11.0, TOP_Y, 1, 1, "round"))
    keys.append(Key("back_light", "☀", "indicators", ADDR_INDICATORS, 0x01, 12.0, TOP_Y, 1, 1, "round"))
    keys.append(Key("num_indicator", "Num", "indicators", ADDR_INDICATORS, 0x05, 13.4, TOP_Y, 0.9, 1, "led"))
    keys.append(Key("caps_indicator", "Caps", "indicators", ADDR_INDICATORS, 0x03, 14.3, TOP_Y, 0.9, 1, "led"))
    keys.append(Key("scroll_indicator", "Scroll", "indicators", ADDR_INDICATORS, 0x04, 15.2, TOP_Y, 0.9, 1, "led"))
    keys.append(Key("mute", "Mute", "multimedia", ADDR_MEDIA, 0xE2, 17.25, TOP_Y, 1, 1, "round"))
    keys.append(Key("play_pause", "▷‖", "multimedia", ADDR_MEDIA, 0xCD, 18.5, TOP_Y, 1, 0.8))
    keys.append(Key("stop", "□", "multimedia", ADDR_MEDIA, 0xB7, 19.5, TOP_Y, 1, 0.8))
    keys.append(Key("previous", "◁◁", "multimedia", ADDR_MEDIA, 0xB6, 20.5, TOP_Y, 1, 0.8))
    keys.append(Key("next", "▷▷", "multimedia", ADDR_MEDIA, 0xB5, 21.5, TOP_Y, 1, 0.8))
    return keys


def _build_iso(ansi: list[Key]) -> list[Key]:
    keys: list[Key] = []
    for k in ansi:
        if k.name == "backslash":
            continue
        if k.name == "enter":
            k = replace(k, x=13.75, y=2.25, w=1.25, h=2.0)
        elif k.name == "shift_left":
            k = replace(k, w=1.25)
        keys.append(k)
    keys.append(Key("dollar", "#", "keys", ADDR_KEYS, USAGES["dollar"], 12.75, 3.25))
    keys.append(Key("intl_backslash", "\\", "keys", ADDR_KEYS, USAGES["intl_backslash"], 1.25, 4.25))
    return keys


_ANSI = _build_ansi()
LAYOUTS: dict[str, list[Key]] = {"ansi": _ANSI, "iso": _build_iso(_ANSI)}

# Every addressable LED, whatever the physical layout (ISO adds two keys).
ALL_KEYS: dict[str, Key] = {k.name: k for k in LAYOUTS["iso"]}
ALL_KEYS.update({k.name: k for k in LAYOUTS["ansi"]})
BY_USAGE: dict[int, str] = {k.code: k.name for k in ALL_KEYS.values() if k.usage is not None}

# Bounding box of the drawing, in key units.
WIDTH = 22.5
HEIGHT = 6.25 - TOP_Y

# Zones offered as one-click selections in the UI: (id, title).
ZONES = [
    ("keys", "Typing keys"),
    ("fkeys", "F1 – F12"),
    ("modifiers", "Modifiers"),
    ("arrows", "Arrows"),
    ("functions", "Navigation"),
    ("numeric", "Numpad"),
    ("multimedia", "Media"),
    ("indicators", "Indicators"),
    ("logo", "Logo"),
]
PRESET_SELECTIONS = [
    ("WASD", ["w", "a", "s", "d"]),
    ("Letters", list("abcdefghijklmnopqrstuvwxyz")),
    ("Numbers", list("1234567890")),
]

# g810-led accepts several spellings per key; map them onto ours for profile import.
ALIASES = {
    "numindicator": "num_indicator", "num": "num_indicator",
    "capsindicator": "caps_indicator", "caps": "caps_indicator",
    "scrollindicator": "scroll_indicator", "scroll": "scroll_indicator",
    "gamemode": "game_mode", "game": "game_mode",
    "backlight": "back_light", "light": "back_light",
    "shiftleft": "shift_left", "shiftl": "shift_left",
    "ctrlleft": "ctrl_left", "ctrll": "ctrl_left",
    "winleft": "win_left", "winl": "win_left",
    "altleft": "alt_left", "altl": "alt_left",
    "altright": "alt_right", "altr": "alt_right", "altgr": "alt_right",
    "winright": "win_right", "winr": "win_right",
    "ctrlright": "ctrl_right", "ctrlr": "ctrl_right",
    "shiftright": "shift_right", "shiftr": "shift_right",
    "playpause": "play_pause", "play": "play_pause", "prev": "previous",
    "arrowtop": "arrow_top", "top": "arrow_top",
    "arrowleft": "arrow_left", "left": "arrow_left",
    "arrowbottom": "arrow_bottom", "bottom": "arrow_bottom",
    "arrowright": "arrow_right", "right": "arrow_right",
    "numlock": "num_lock", "numslash": "num_slash", "num/": "num_slash",
    "numasterisk": "num_asterisk", "num*": "num_asterisk",
    "numminus": "num_minus", "num-": "num_minus",
    "numplus": "num_plus", "num+": "num_plus",
    "num_enter": "numenter", "numdot": "num_dot", "num.": "num_dot",
    "esc": "escape", "printscreen": "print_screen", "printscr": "print_screen",
    "scrolllock": "scroll_lock", "pausebreak": "pause_break", "ins": "insert",
    "pageup": "page_up", "del": "delete", "pagedown": "page_down",
    "capslock": "caps_lock", "back": "backspace",
}
for _i in range(10):
    ALIASES[f"num_{_i}"] = f"num{_i}"


def canonical(name: str) -> str | None:
    name = name.strip().lower()
    name = ALIASES.get(name, name)
    return name if name in ALL_KEYS else None


def zone_keys(zone: str) -> list[str]:
    return [k.name for k in ALL_KEYS.values() if k.zone == zone]
