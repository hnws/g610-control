"""Frame generators for lighting effects.

Used two ways: to draw the animated preview for effects the keyboard runs
itself, and to produce the actual per-key frames for the software effects.
"""

from __future__ import annotations

import math
import random

from . import keys as K

ANIMATED = {"breathing", "wave", "ripple", "stars", "reactive"}
_STATIC_ZONES = ("indicators", "logo")


class EffectRenderer:
    def __init__(self, layout: list[K.Key]):
        self.set_layout(layout)
        self._stars: dict[str, float] = {}       # key -> start time
        self._presses: list[tuple[float, float, float]] = []  # (time, x, y)
        self._hits: dict[str, float] = {}        # key -> last press time
        self._last_t = 0.0
        self._rng = random.Random()

    def set_layout(self, layout: list[K.Key]) -> None:
        self.layout = layout
        self._animated = [k for k in layout if k.zone not in _STATIC_ZONES]

    def reset(self) -> None:
        self._stars.clear()
        self._presses.clear()
        self._hits.clear()

    def key_pressed(self, name: str, t: float) -> None:
        key = K.ALL_KEYS.get(name)
        if key is None:
            return
        self._hits[name] = t
        self._presses.append((t, key.cx, key.cy))
        del self._presses[:-12]

    def render(self, effect: dict, t: float) -> dict[str, int]:
        """Brightness (0-255) of every key at time t (seconds)."""
        kind = effect.get("type", "fixed")
        peak = int(effect.get("brightness", 255))
        base = min(int(effect.get("background", 0)), peak)
        period = max(0.05, int(effect.get("period", 3000)) / 1000)
        dt, self._last_t = max(0.0, min(0.5, t - self._last_t)), t
        levels = {k.name: peak for k in self.layout}

        if kind == "breathing":
            level = round(peak * (0.5 - 0.5 * math.cos(2 * math.pi * t / period)))
            return {k.name: level for k in self.layout}

        if kind == "wave":
            direction = effect.get("direction", "horizontal")
            for k in self._animated:
                if direction == "vertical":
                    pos = (k.cy - K.TOP_Y) / K.HEIGHT
                elif direction == "center":
                    pos = math.hypot(k.cx - K.WIDTH / 2, (k.cy - 2.6) * 1.6) / (K.WIDTH / 2)
                else:
                    pos = k.cx / K.WIDTH
                levels[k.name] = round(peak * (0.5 + 0.5 * math.sin(2 * math.pi * (t / period - pos))))
            return levels

        if kind == "ripple":
            self._presses = [p for p in self._presses if t - p[0] < period * 1.5]
            speed = K.WIDTH / period  # key units per second
            for k in self._animated:
                best = 0.0
                for t0, x, y in self._presses:
                    age = max(0.0, t - t0)
                    edge = abs(math.hypot(k.cx - x, k.cy - y) - speed * age)
                    best = max(best, max(0.0, 1 - edge / 1.6) * max(0.0, 1 - age / (period * 1.5)))
                levels[k.name] = round(peak * best)
            return levels

        if kind == "stars":
            density = max(1, min(100, int(effect.get("density", 40)))) / 100
            # Aim for `density` of the keys to be lit at any moment.
            births = density * len(self._animated) * dt / period
            count = int(births) + (1 if self._rng.random() < births % 1 else 0)
            for _ in range(count):
                name = self._rng.choice(self._animated).name
                self._stars.setdefault(name, t)
            self._stars = {n: t0 for n, t0 in self._stars.items() if t - t0 < period}
            for k in self._animated:
                t0 = self._stars.get(k.name)
                age = max(0.0, min(period, t - t0)) if t0 is not None else 0.0
                glow = math.sin(math.pi * age / period) ** 2
                levels[k.name] = round(base + (peak - base) * glow)
            return levels

        if kind == "reactive":
            self._hits = {n: t0 for n, t0 in self._hits.items() if t - t0 < period}
            for k in self._animated:
                t0 = self._hits.get(k.name)
                glow = max(0.0, min(1.0, 1 - (t - t0) / period)) if t0 is not None else 0.0
                levels[k.name] = round(base + (peak - base) * glow * glow)
            return levels

        return levels  # fixed
