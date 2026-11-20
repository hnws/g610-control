# G610 Control

A desktop app for the Logitech G610 keyboard on Linux: per-key brightness, lighting
effects, game mode keys, polling rate and power-on behaviour. It talks to the keyboard
directly over HID++ (no `g810-led` binary needed at runtime) and is not affiliated with
Logitech.

Tested on a G610 (USB `046d:c338`, firmware 04.12) on Arch Linux / KDE Plasma 6 Wayland.
The `046d:c333` variant is recognised too but has not been tried.

## Run

```bash
./g610-control
```

Requirements: Python 3.10+ and PySide6 (`pacman -S pyside6`). To add it to the
application menu:

```bash
./install.sh
```

The keyboard's `hidraw` nodes must be accessible to your user. The udev rules shipped
with `g810-led` already do that (`TAG+="uaccess"`); without that package, add a rule like

```
SUBSYSTEMS=="usb", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="c338", MODE="660", TAG+="uaccess"
```

## What it does

**Lighting**

- *Effects*: Fixed, Breathing, Light wave (three directions) and Key press ripple run
  inside the keyboard. Star effect and Typing glow are drawn by the app, frame by frame.
- *Freestyle*: click or drag across keys on the on-screen keyboard and set their
  brightness. Ctrl+click adds keys, double-click selects a zone, Ctrl+A selects all.
- Master brightness and a lights on/off switch in the header and the tray menu.
- Profiles: create, duplicate, rename, delete, switch from the tray. Five are created on
  first run (Default, Gaming, Typing, Breathing, Stars).

**Game mode** - choose which keys the keyboard ignores while its game mode button is on.

**Settings**

- Power-on behaviour (steady light or the wave animation), stored in the keyboard.
- Polling rate: 1000 / 500 / 250 / 125 Hz.
- Lighting sleep after 1-60 minutes without a key press, and lights off while the
  screen is locked.
- Start at login (hidden in the tray), keep running in the tray.
- Import and export of `g810-led` profile files.

Lighting is restored automatically when the keyboard is plugged in again and after the
computer resumes from suspend.

## Command line

```bash
./g610-control info            # what the keyboard reports about itself
./g610-control apply [NAME]    # apply a saved profile and exit
./g610-control off             # all lights off
./g610-control --minimized     # start the GUI hidden in the tray
```

`raw-effect ZONE INDEX [BYTES...]` sends an arbitrary on-board effect, for experiments.

## Lighting before login

The keyboard cannot store a per-key layout or an effect of its own (it reports no
persistent lighting storage), so custom lighting needs something on the computer to send
it. After login that is this app. Before login, `g810-led`'s udev rule applies
`/etc/g810-led/profile`; use *Settings > Export current profile* and copy the result
there if you want the same look at the login screen:

```bash
sudo cp ~/default.g810 /etc/g810-led/profile
```

## How it works

| Module | Role |
| --- | --- |
| `g610ctl/hidpp.py` | HID++ 2.0 requests and replies over `/dev/hidrawN` |
| `g610ctl/device.py` | G610 features: per-key lighting, effects, game mode, polling rate, info |
| `g610ctl/keys.py` | Key names, LED addresses and the on-screen geometry (ANSI and ISO) |
| `g610ctl/effects.py` | Frame generators for previews and software effects |
| `g610ctl/lighting.py` | Turns a profile into device calls |
| `g610ctl/controller.py` | Device thread with auto-reconnect, profiles, sleep / lock / resume |
| `g610ctl/ui/` | Qt widgets: keyboard view, pages, theme |

Feature and effect indexes are read from the keyboard rather than hard-coded. That
matters on the G610: its effect list is off / fixed / breathing / wave / starlight /
ripple, so the fixed table in `g810-led` (written for the RGB models) selects the wrong
effect for anything after breathing.

HID++ features used: `0x8080` per-key lighting, `0x8070` colour LED effects (also holds
the power-on setting), `0x4522` disable keys by usage (game mode), `0x8060` report rate,
`0x4540` keyboard layout, `0x0003` firmware and `0x0005` name.

To notice typing (for the sleep timer, the ripple preview and Typing glow) the app reads
this keyboard's own key reports from its `hidraw` nodes. Key presses are only used in
memory for timing and animation; nothing is stored or sent anywhere.

Settings and profiles live in `~/.config/g610-control/`.

## Limits

- The sleep timer only sees this keyboard. Mouse movement does not count as activity
  (Wayland offers no general idle time to ordinary apps).
- Star effect and Typing glow stop when the app is closed; the keyboard keeps the last
  frame.
- The keyboard's own starlight effect is not used: its parameters are undocumented. The
  `raw-effect` command can be used to explore it (zone 0, effect index 4).
- No macros, key remapping or per-application profiles.

## Tests

```bash
python3 -m pytest
```

The tests run without a keyboard, against the feature table of a real G610.
