"""Protocol, profile and effect tests that run without a keyboard."""

import json

import pytest

from g610ctl import keys as K
from g610ctl.device import (FEAT_DISABLE_KEYS, FEAT_EFFECTS, FEAT_PER_KEY, FX_BREATHING, FX_FIXED,
                            FX_OFF, FX_RIPPLE, FX_STARLIGHT, FX_WAVE, G610, ZONE_KEYS, ZONE_LOGO)
from g610ctl.effects import EffectRenderer
from g610ctl.lighting import lighting_job
from g610ctl.profile import EFFECT_DEFAULTS, Profile, Store, export_g810, import_g810

# Feature table and effect lists as read from a real G610 (046d:c338, firmware 04.12).
FEATURES = {FEAT_DISABLE_KEYS: 0x03, FEAT_PER_KEY: 0x0C, FEAT_EFFECTS: 0x0D}
ZONE_EFFECTS = {0: (0x0001, [FX_OFF, FX_FIXED, FX_BREATHING, FX_WAVE, FX_STARLIGHT, FX_RIPPLE]),
                1: (0x0002, [FX_OFF, FX_FIXED, FX_BREATHING])}


class FakeHidpp:
    def __init__(self):
        self.sent = []  # (feature index, function, params, very_long)

    def feature_index(self, feature_id):
        return FEATURES.get(feature_id)

    def request(self, index, function, params=b"", very_long=False, timeout=1.0):
        params = bytes(params)
        if index == 0x0D and function == 0:
            return bytes([2, 0, 1, 0, 8]).ljust(16, b"\0")
        if index == 0x0D and function == 1:
            location, effects = ZONE_EFFECTS[params[0]]
            return bytes([params[0], location >> 8, location & 0xFF, len(effects)]).ljust(16, b"\0")
        if index == 0x0D and function == 2:
            effect = ZONE_EFFECTS[params[0]][1][params[1]]
            return bytes([params[0], params[1], effect >> 8, effect & 0xFF]).ljust(16, b"\0")
        self.sent.append((index, function, params, very_long))
        return bytes(16)

    def close(self):
        pass


@pytest.fixture
def dev():
    device = G610.__new__(G610)
    device.paths = {}
    device.hidpp = FakeHidpp()
    device._sent, device._effect_index, device._zone_index = {}, {}, {}
    device._features_loaded = False
    return device


def test_layouts_are_consistent():
    for name, layout in K.LAYOUTS.items():
        names = [k.name for k in layout]
        assert len(names) == len(set(names)), name
        for a in layout:  # no two keys overlap
            for b in layout:
                if a is not b:
                    assert (a.x + a.w <= b.x + 1e-6 or b.x + b.w <= a.x + 1e-6
                            or a.y + a.h <= b.y + 1e-6 or b.y + b.h <= a.y + 1e-6), (a.name, b.name)
            assert a.x >= 0 and a.x + a.w <= K.WIDTH + 1e-6
    assert len(K.LAYOUTS["ansi"]) == 104 + 11       # keys + logo, 5 indicators, 5 media
    assert len(K.LAYOUTS["iso"]) == 105 + 11
    assert K.USAGES["a"] == 0x04 and K.USAGES["caps_lock"] == 0x39
    assert K.USAGES["menu"] == 0x65 and K.USAGES["win_right"] == 0xE7


def test_single_key_packet_matches_g810_led(dev):
    dev.set_keys({"a": 0x80})
    assert dev.hidpp.sent == [
        (0x0C, 3, bytes([0x00, 0x01, 0x00, 0x01, 0x04, 0x80, 0x80, 0x80]), True),
        (0x0C, 5, b"", False),  # commit
    ]


def test_groups_and_chunking(dev):
    packets = dev.set_keys({name: 255 for name in K.ALL_KEYS})
    sets = [s for s in dev.hidpp.sent if s[1] == 3]
    by_group = {}
    for _, _, params, very_long in sets:
        assert params[3] == (len(params) - 4) // 4 <= 14
        by_group.setdefault(params[1], []).append((params, very_long))
    assert set(by_group) == {K.ADDR_KEYS, K.ADDR_MEDIA, K.ADDR_LOGO, K.ADDR_INDICATORS}
    assert by_group[K.ADDR_LOGO] == [(bytes([0, 0x10, 0, 1, 0x01, 255, 255, 255]), False)]
    assert sum(p[3] for p, _ in by_group[K.ADDR_KEYS]) == 106   # ANSI + the two ISO extras
    assert sorted(p[4 + 4 * i] for p, _ in by_group[K.ADDR_MEDIA] for i in range(p[3])) == \
        [0xB5, 0xB6, 0xB7, 0xCD, 0xE2]
    assert dev.hidpp.sent[-1][:2] == (0x0C, 5)
    assert packets == len(dev.hidpp.sent)


def test_unchanged_keys_are_not_resent(dev):
    dev.set_keys({"a": 10, "b": 20})
    dev.hidpp.sent.clear()
    assert dev.set_keys({"a": 10, "b": 20}) == 0 and dev.hidpp.sent == []
    dev.set_keys({"a": 10, "b": 21})
    assert dev.hidpp.sent[0][2] == bytes([0, 1, 0, 1, 0x05, 21, 21, 21])
    dev.hidpp.sent.clear()
    dev.set_keys({"a": 10}, force=True)
    assert len(dev.hidpp.sent) == 2


def test_effects_use_the_indexes_the_keyboard_reports(dev):
    assert dev.effect_breathing(ZONE_KEYS, 0xFF, 3000)
    assert dev.effect_wave(0xFF, 5000, "vertical")
    assert dev.effect_ripple(0x80, 800)
    assert dev.effect_starlight(0x10, 0xFF)
    assert dev.effect_fixed(ZONE_LOGO, 0x40)
    assert not dev.set_zone_effect(ZONE_LOGO, FX_WAVE)       # the logo zone has no wave
    sent = [p for _, f, p, _ in dev.hidpp.sent if f == 3]
    assert all(len(p) == 13 for p in sent)
    # zone, effect index, then ten parameter bytes
    assert sent[0][:7] == bytes([0, 2, 0xFF, 0xFF, 0xFF, 0x0B, 0xB8])
    assert sent[1][:2] == bytes([0, 3]) and sent[1][8] == 0x88 and sent[1][9] == 2 \
        and sent[1][10] == 100 and sent[1][11] == 0x13
    assert sent[2][:8] == bytes([0, 5, 0x80, 0x80, 0x80, 0, 0x03, 0x20])
    assert sent[3][:8] == bytes([0, 4, 0x10, 0x10, 0x10, 0xFF, 0xFF, 0xFF])
    assert sent[4][:5] == bytes([1, 1, 0x40, 0x40, 0x40])


def test_an_effect_invalidates_the_per_key_cache(dev):
    dev.set_keys({"a": 255, "logo": 255, "caps_indicator": 255})
    dev.effect_breathing(ZONE_KEYS, 255, 3000)
    dev.hidpp.sent.clear()
    dev.set_keys({"a": 255, "logo": 255, "caps_indicator": 255})
    groups = [p[1] for _, f, p, _ in dev.hidpp.sent if f == 3]
    assert groups == [K.ADDR_KEYS]   # logo and indicators were untouched by the keys zone


def test_game_mode_keys(dev):
    dev.set_game_mode_keys(["win_left", "menu", "win_right", "mute", "nonsense"])
    assert dev.hidpp.sent == [(0x03, 3, b"", False), (0x03, 1, bytes([0x65, 0xE3]), False)]


def test_lighting_job_freestyle_scales_with_master_brightness(dev):
    profile = Profile("p", "freestyle", {name: 200 for name in K.ALL_KEYS})
    lighting_job(profile, 50)(dev)
    assert dev._sent["a"] == 100 and dev._sent["logo"] == 100


def test_lighting_job_wave_sets_indicators_then_effects(dev):
    profile = Profile("p", "effect", {}, dict(EFFECT_DEFAULTS, type="wave", period=4000))
    lighting_job(profile, 100)(dev)
    functions = [(i, f) for i, f, _, _ in dev.hidpp.sent]
    assert functions == [(0x0C, 3), (0x0C, 5), (0x0D, 3), (0x0D, 3)]


def test_lighting_job_falls_back_for_software_effects(dev):
    profile = Profile("p", "effect", {}, dict(EFFECT_DEFAULTS, type="stars", brightness=128))
    lighting_job(profile, 100)(dev)
    assert dev._sent["q"] == 128


def test_profile_store_roundtrip(tmp_path):
    store = Store(tmp_path)
    assert "Default" in store.profiles and store.settings["active_profile"] == "Default"
    profile = store.profiles["Gaming"]
    profile.keys["w"] = 7
    store.save_profile(profile)
    store.settings["brightness"] = 60
    store.save_settings()
    again = Store(tmp_path)
    assert again.profiles["Gaming"].keys["w"] == 7 and again.settings["brightness"] == 60
    assert again.unique_name("Gaming") == "Gaming 2"
    again.delete_profile("Gaming")
    assert "Gaming" not in Store(tmp_path).profiles


def test_profile_ignores_bad_data():
    profile = Profile.from_json({"name": "x", "mode": "weird", "keys": {"a": 999, "zz": 1},
                                 "effect": {"type": "nope", "junk": 1}})
    assert profile.mode == "effect" and profile.keys == {"a": 255}
    assert profile.effect["type"] == "fixed" and "junk" not in profile.effect
    json.dumps(profile.to_json())


def test_g810_import_and_export():
    text = """
    # sample
    var dim 20
    a 10          # everything low
    g fkeys ff
    k w 80
    k esc $dim
    k logo 0000c0 # RGB colour from another model
    c
    """
    profile = import_g810(text, "Imported")
    assert profile.mode == "freestyle"
    assert profile.keys["q"] == 0x10 and profile.keys["f5"] == 0xFF and profile.keys["w"] == 0x80
    assert profile.keys["escape"] == 0x20 and profile.keys["logo"] == 0xC0
    exported = export_g810(profile)
    assert "k w 80" in exported and exported.rstrip().endswith("c")
    assert import_g810(exported, "again").keys == profile.keys
    fx = import_g810("fx vwave keys 5s\n", "fx")
    assert fx.mode == "effect" and fx.effect["type"] == "wave" and fx.effect["direction"] == "vertical"


@pytest.mark.parametrize("kind", ["fixed", "breathing", "wave", "ripple", "stars", "reactive"])
def test_effect_frames_stay_in_range(kind):
    renderer = EffectRenderer(K.LAYOUTS["ansi"])
    effect = dict(EFFECT_DEFAULTS, type=kind, brightness=200, background=20, period=500)
    renderer.key_pressed("g", 0.05)
    seen = set()
    for step in range(120):
        frame = renderer.render(effect, step * 0.04)
        assert set(frame) == {k.name for k in K.LAYOUTS["ansi"]}
        assert all(0 <= v <= 200 for v in frame.values())
        seen.update(frame.values())
    if kind != "fixed":
        assert len(seen) > 3   # it actually animates


def test_reactive_lights_the_pressed_key_and_fades():
    renderer = EffectRenderer(K.LAYOUTS["ansi"])
    effect = dict(EFFECT_DEFAULTS, type="reactive", brightness=255, background=10, period=1000)
    renderer.key_pressed("g", 1.0)
    assert renderer.render(effect, 1.0)["g"] == 255
    assert 10 < renderer.render(effect, 1.5)["g"] < 255
    assert renderer.render(effect, 2.5)["g"] == 10
    assert renderer.render(effect, 1.2)["h"] == 10
