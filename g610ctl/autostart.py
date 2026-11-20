"""Start-at-login entry (~/.config/autostart) and the command that launches the app."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from . import APP_ID, APP_NAME

PACKAGE_DIR = Path(__file__).resolve().parent
ICON_PATH = PACKAGE_DIR / "data" / "g610-control.svg"


def launch_command() -> list[str]:
    """How to start the GUI from anywhere: the checkout's launcher, or `python -m`."""
    launcher = PACKAGE_DIR.parent / "g610-control"
    if launcher.is_file():
        return [sys.executable, str(launcher)]
    return [sys.executable, "-m", "g610ctl"]


def desktop_entry(minimized: bool = False) -> str:
    command = launch_command() + (["--minimized"] if minimized else [])
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_NAME}",
        "Comment=Lighting and settings for the Logitech G610 keyboard",
        f"Exec={shlex.join(command)}",
        f"Icon={ICON_PATH}",
        "Terminal=false",
        "Categories=Settings;HardwareSettings;",
        "Keywords=keyboard;logitech;backlight;led;",
        f"StartupWMClass={APP_ID}",
        "",
    ])


def _autostart_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart" / f"{APP_ID}.desktop"


def is_enabled() -> bool:
    return _autostart_file().is_file()


def set_enabled(enabled: bool) -> None:
    path = _autostart_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(minimized=True))
    elif path.exists():
        path.unlink()
