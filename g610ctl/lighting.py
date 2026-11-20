"""Turns a profile into the device calls that show it (everything except software effects)."""

from __future__ import annotations

from typing import Callable

from . import keys as K
from .device import G610, ZONE_KEYS, ZONE_LOGO
from .profile import EFFECTS, Profile


def lighting_job(profile: Profile, brightness: int = 100, full: bool = False) -> Callable[[G610], None]:
    """A callable that applies `profile` at a master brightness (percent).

    Software effects cannot be shown this way; they fall back to a steady light.
    """
    def scale(level: int) -> int:
        return round(max(0, min(255, int(level))) * brightness / 100)

    effect = dict(profile.effect)
    kind = "freestyle" if profile.mode == "freestyle" else effect.get("type", "fixed")
    if kind != "freestyle" and not EFFECTS.get(kind, {}).get("onboard"):
        kind = "fixed"
    level = scale(effect.get("brightness", 255))
    period = int(effect.get("period", 3000))
    if kind == "freestyle":
        levels = {name: scale(profile.level(name)) for name in K.ALL_KEYS}
    else:
        levels = {name: level for name in K.ALL_KEYS}
    indicators = {name: level for name in K.zone_keys("indicators")}

    def job(dev: G610) -> None:
        if full:
            dev.forget_sent()
        if kind in ("freestyle", "fixed"):
            dev.set_keys(levels)
            return
        # Indicators are not part of an effect zone; set them first, as g810-led does.
        dev.set_keys(indicators, force=True)
        if kind == "breathing":
            dev.effect_breathing(ZONE_KEYS, level, period)
            dev.effect_breathing(ZONE_LOGO, level, period)
        elif kind == "wave":
            dev.effect_wave(level, period, effect.get("direction", "horizontal"))
            dev.effect_fixed(ZONE_LOGO, level)
        elif kind == "ripple":
            dev.effect_ripple(level, period)
            dev.effect_fixed(ZONE_LOGO, level)

    return job
