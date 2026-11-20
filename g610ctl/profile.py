"""Profiles and settings, stored as JSON under ~/.config/g610-control."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import APP_ID
from . import keys as K

# type -> (title, description, parameters shown, runs on the keyboard itself)
EFFECTS: dict[str, dict] = {
    "fixed": {
        "title": "Fixed", "onboard": True, "params": ["brightness"],
        "help": "Every key at one steady brightness.",
    },
    "breathing": {
        "title": "Breathing", "onboard": True, "params": ["brightness", "period"],
        "help": "The whole keyboard slowly fades in and out.",
    },
    "wave": {
        "title": "Light wave", "onboard": True, "params": ["brightness", "period", "direction"],
        "help": "A band of light travels across the keyboard.",
    },
    "ripple": {
        "title": "Key press", "onboard": True, "params": ["brightness", "period"],
        "help": "Each key press sends a ripple of light outwards.",
    },
    "stars": {
        "title": "Star effect", "onboard": False,
        "params": ["brightness", "background", "density", "period"],
        "help": "Random keys twinkle like stars. Drawn by this app, so it has to keep running.",
    },
    "reactive": {
        "title": "Typing glow", "onboard": False,
        "params": ["brightness", "background", "period"],
        "help": "Keys light up as you press them and fade back. Drawn by this app, "
                "so it has to keep running.",
    },
}

EFFECT_DEFAULTS = {
    "type": "fixed", "brightness": 255, "background": 0, "period": 3000,
    "direction": "horizontal", "density": 40,
}
# Sensible speed when an effect is first picked, and the slider range (ms).
PERIOD_RANGE = {
    "breathing": (1000, 10000, 3000), "wave": (1000, 15000, 5000),
    "ripple": (200, 3000, 800), "stars": (300, 5000, 1500), "reactive": (150, 3000, 600),
}

DEFAULT_GAME_KEYS = ["win_left"]

SETTINGS_DEFAULTS = {
    "active_profile": "Default",
    "lights_on": True,
    "brightness": 100,
    "layout": "auto",
    "sleep_minutes": 0,
    "off_when_locked": True,
    "close_to_tray": True,
    "game_keys": list(DEFAULT_GAME_KEYS),
    "report_rate": None,
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_ID


@dataclass
class Profile:
    name: str
    mode: str = "effect"  # "effect" or "freestyle"
    keys: dict[str, int] = field(default_factory=dict)
    effect: dict = field(default_factory=lambda: dict(EFFECT_DEFAULTS))

    def level(self, name: str) -> int:
        return self.keys.get(name, 255)

    def to_json(self) -> dict:
        return {"name": self.name, "mode": self.mode, "keys": self.keys, "effect": self.effect}

    @classmethod
    def from_json(cls, data: dict) -> "Profile":
        effect = dict(EFFECT_DEFAULTS)
        effect.update({k: v for k, v in (data.get("effect") or {}).items() if k in EFFECT_DEFAULTS})
        if effect["type"] not in EFFECTS:
            effect["type"] = "fixed"
        keys = {}
        for name, level in (data.get("keys") or {}).items():
            if name in K.ALL_KEYS:
                keys[name] = max(0, min(255, int(level)))
        mode = data.get("mode") if data.get("mode") in ("effect", "freestyle") else "effect"
        return cls(str(data.get("name") or "Profile"), mode, keys, effect)

    def copy(self, name: str) -> "Profile":
        return Profile(name, self.mode, dict(self.keys), dict(self.effect))


def builtin_profiles() -> list[Profile]:
    gaming = {name: 40 for name in K.ALL_KEYS}
    for name in ["w", "a", "s", "d", "escape", "space", "shift_left", "ctrl_left",
                 "1", "2", "3", "4", "q", "e", "r", "f", "tab",
                 "arrow_top", "arrow_left", "arrow_bottom", "arrow_right",
                 "game_mode", "logo"]:
        gaming[name] = 255
    typing = {name: 30 for name in K.ALL_KEYS}
    for name in K.zone_keys("keys"):
        typing[name] = 200
    for name in ["f", "j", "enter", "backspace", "shift_left", "shift_right",
                 "caps_indicator", "num_indicator", "scroll_indicator"]:
        typing[name] = 255
    return [
        Profile("Default"),
        Profile("Gaming", "freestyle", gaming),
        Profile("Typing", "freestyle", typing),
        Profile("Breathing", "effect", {}, dict(EFFECT_DEFAULTS, type="breathing", period=4000)),
        Profile("Stars", "effect", {}, dict(EFFECT_DEFAULTS, type="stars", period=1500, background=15)),
    ]


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "profile"


class Store:
    """Loads and saves settings and profiles."""

    def __init__(self, directory: Path | None = None):
        self.dir = directory or config_dir()
        self.profile_dir = self.dir / "profiles"
        self.settings: dict = dict(SETTINGS_DEFAULTS)
        self.profiles: dict[str, Profile] = {}
        self.load()

    def load(self) -> None:
        try:
            data = json.loads((self.dir / "settings.json").read_text())
            self.settings.update({k: v for k, v in data.items() if k in SETTINGS_DEFAULTS})
        except (OSError, ValueError):
            pass
        self.profiles = {}
        for path in sorted(self.profile_dir.glob("*.json")):
            try:
                profile = Profile.from_json(json.loads(path.read_text()))
            except (OSError, ValueError, TypeError):
                continue
            self.profiles[profile.name] = profile
        if not self.profiles:
            for profile in builtin_profiles():
                self.profiles[profile.name] = profile
                self.save_profile(profile)
        if self.settings["active_profile"] not in self.profiles:
            self.settings["active_profile"] = next(iter(self.profiles))

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
        tmp.replace(path)

    def save_settings(self) -> None:
        self._write(self.dir / "settings.json", self.settings)

    def _path(self, name: str) -> Path:
        return self.profile_dir / f"{_slug(name)}.json"

    def save_profile(self, profile: Profile) -> None:
        self._write(self._path(profile.name), profile.to_json())

    def delete_profile(self, name: str) -> None:
        self.profiles.pop(name, None)
        try:
            self._path(name).unlink()
        except OSError:
            pass

    def unique_name(self, wanted: str) -> str:
        taken = {_slug(n).lower() for n in self.profiles}
        name, n = wanted, 2
        while _slug(name).lower() in taken:
            name = f"{wanted} {n}"
            n += 1
        return name


# -- g810-led profile files -------------------------------------------------

def _intensity(text: str) -> int:
    text = text.strip()
    if len(text) == 6:  # RRGGBB from an RGB keyboard profile: keep the brightest channel
        return max(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    return max(0, min(255, int(text, 16)))


def import_g810(text: str, name: str) -> Profile:
    """Read a g810-led profile (a/g/k lines and simple fx lines)."""
    levels = {key: 255 for key in K.ALL_KEYS}
    effect = dict(EFFECT_DEFAULTS)
    mode = "freestyle"
    variables: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [variables.get(p[1:], p) if p.startswith("$") else p for p in line.split()]
        cmd, args = parts[0].lower(), parts[1:]
        try:
            if cmd == "var" and len(args) >= 2:
                variables[args[0]] = args[1]
            elif cmd == "a" and args:
                levels = {key: _intensity(args[0]) for key in K.ALL_KEYS}
            elif cmd == "g" and len(args) >= 2:
                for key in K.zone_keys(args[0].lower()):
                    levels[key] = _intensity(args[1])
            elif cmd == "k" and len(args) >= 2:
                key = K.canonical(args[0])
                if key:
                    levels[key] = _intensity(args[1])
            elif cmd == "fx" and len(args) >= 2 and args[1].lower() in ("all", "keys"):
                kind = args[0].lower()
                if kind == "color" and len(args) >= 3:
                    mode, effect["type"], effect["brightness"] = "effect", "fixed", _intensity(args[2])
                elif kind == "breathing" and len(args) >= 3:
                    mode, effect["type"], effect["brightness"] = "effect", "breathing", _intensity(args[2])
                elif kind in ("hwave", "vwave", "cwave", "waves"):
                    mode, effect["type"] = "effect", "wave"
                    effect["direction"] = {"vwave": "vertical", "cwave": "center"}.get(kind, "horizontal")
        except ValueError:
            continue
    return Profile(name, mode, levels, effect)


def export_g810(profile: Profile, brightness: int = 100) -> str:
    """Write the profile's static look as a g810-led profile (for /etc/g810-led/profile)."""
    scale = max(0, min(100, brightness)) / 100
    lines = [f"# {profile.name} - exported by G610 Control"]
    if profile.mode == "freestyle":
        for name in sorted(K.ALL_KEYS):
            lines.append(f"k {name} {round(profile.level(name) * scale):02x}")
    else:
        level = round(int(profile.effect.get("brightness", 255)) * scale)
        if profile.effect.get("type") != "fixed":
            lines.append("# animated effects need G610 Control running; this is the steady fallback")
        lines.append(f"a {level:02x}")
    lines.append("c")
    return "\n".join(lines) + "\n"
