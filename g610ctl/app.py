"""Entry point: the GUI with its tray icon, plus a few command-line actions."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from . import APP_ID, APP_NAME, __version__


# -- command line (no GUI) ---------------------------------------------------

def _cli(args: argparse.Namespace) -> int:
    from .device import G610, find_devices
    from .hidpp import HidppError, HidppTimeout
    from .lighting import lighting_job
    from .profile import Store
    from . import keys as K

    if not find_devices():
        print("No Logitech G610 keyboard found.", file=sys.stderr)
        return 1
    try:
        dev = G610.open_first()
    except OSError as exc:
        print(f"Cannot open the keyboard: {exc}", file=sys.stderr)
        return 1
    try:
        if args.command == "info":
            info = dev.read_info()
            print(f"Model:         {info.name}")
            print(f"Serial:        {info.serial}")
            print(f"Firmware:      {info.firmware}")
            print(f"Bootloader:    {info.bootloader}")
            print(f"Layout:        {info.layout} (code {info.layout_code})")
            print(f"Polling rate:  {1000 // info.report_rate if info.report_rate else '?'} Hz "
                  f"(supports {', '.join(str(1000 // r) for r in info.report_rates)})")
            print(f"Power-on:      {'light wave' if info.startup_wave else 'steady light'}")
            for zone, effects in info.effects.items():
                print(f"Zone {zone:#06x}:   effects {', '.join(f'{e:#06x}' for e in effects)}")
        elif args.command == "apply":
            store = Store()
            name = args.profile or store.settings["active_profile"]
            if name not in store.profiles:
                print(f"No profile named {name!r}. Available: {', '.join(store.profiles)}",
                      file=sys.stderr)
                return 1
            lighting_job(store.profiles[name], store.settings["brightness"], full=True)(dev)
            dev.set_game_mode_keys(store.settings["game_keys"])
            print(f"Applied profile {name!r}.")
        elif args.command == "off":
            dev.set_keys({name: 0 for name in K.ALL_KEYS}, force=True)
        elif args.command == "raw-effect":
            dev.raw_zone_effect(args.zone, args.effect, bytes(int(x, 16) for x in args.params))
            print("Sent.")
    except (HidppError, HidppTimeout, OSError) as exc:
        print(f"Keyboard error: {exc}", file=sys.stderr)
        return 1
    finally:
        dev.close()
    return 0


# -- GUI ---------------------------------------------------------------------

def _gui(minimized: bool) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from .autostart import ICON_PATH
    from .controller import Controller
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLE)
    icon = QIcon(str(ICON_PATH))
    app.setWindowIcon(icon)

    # One instance per user: a second launch just raises the first one's window.
    socket_name = f"{APP_ID}-{os.getuid()}"
    probe = QLocalSocket()
    probe.connectToServer(socket_name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(socket_name)
    server = QLocalServer()
    server.listen(socket_name)

    controller = Controller()
    window = MainWindow(controller)

    def show_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def quit_app() -> None:
        window.force_quit = True
        controller.shutdown()
        app.quit()

    def on_connection() -> None:
        while server.hasPendingConnections():
            server.nextPendingConnection().deleteLater()
        show_window()

    server.newConnection.connect(on_connection)

    def setup_tray() -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        tray = QSystemTrayIcon(icon, app)
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Open G610 Control", show_window)
        lights = QAction("Lights on", menu, checkable=True)
        lights.triggered.connect(lambda on: controller.set_setting("lights_on", on))
        menu.addAction(lights)
        profiles_menu = menu.addMenu("Profile")
        menu.addSeparator()
        menu.addAction("Quit", quit_app)

        def rebuild() -> None:
            lights.setChecked(controller.settings["lights_on"])
            profiles_menu.clear()
            for name in controller.store.profiles:
                action = profiles_menu.addAction(name, lambda n=name: controller.select_profile(n))
                action.setCheckable(True)
                action.setChecked(name == controller.profile.name)

        controller.profilesChanged.connect(rebuild)
        controller.stateChanged.connect(rebuild)
        rebuild()
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: show_window() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        app._tray, app._tray_menu = tray, menu  # keep alive
        window.setProperty("has_tray", True)
        return True

    # At login the desktop's tray may not be up yet: keep trying for a while, and
    # only fall back to showing the window if it never appears.
    attempts = {"left": 40}

    def try_tray() -> None:
        if setup_tray():
            return
        attempts["left"] -= 1
        if attempts["left"] > 0:
            QTimer.singleShot(500, try_tray)
        elif minimized:
            show_window()

    window.setProperty("has_tray", False)
    try_tray()

    # Let Ctrl+C in a terminal close the app cleanly.
    signal.signal(signal.SIGINT, lambda *_: quit_app())
    signal.signal(signal.SIGTERM, lambda *_: quit_app())
    heartbeat = QTimer(interval=300)
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start()

    controller.start()
    if not minimized:
        show_window()
    code = app.exec()
    controller.shutdown()
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="g610-control", description="Lighting and settings for the Logitech G610 keyboard.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info", help="print what the keyboard reports about itself")
    apply_cmd = sub.add_parser("apply", help="apply a saved profile and exit")
    apply_cmd.add_argument("profile", nargs="?", help="profile name (default: the active one)")
    sub.add_parser("off", help="turn all lights off")
    raw = sub.add_parser("raw-effect", help="send a raw on-board effect (for experiments)")
    raw.add_argument("zone", type=int, help="zone index (0 = keys, 1 = logo)")
    raw.add_argument("effect", type=int, help="effect index within the zone")
    raw.add_argument("params", nargs="*", help="up to 11 parameter bytes in hex")
    args = parser.parse_args(argv)
    if args.command:
        return _cli(args)
    return _gui(args.minimized)


if __name__ == "__main__":
    sys.exit(main())
