#!/bin/sh
# Adds G610 Control to the application menu for the current user.
# Nothing is copied: the menu entry points at this checkout, so keep the folder.
#   ./install.sh            install the menu entry
#   ./install.sh --remove   remove it (and the start-at-login entry)
set -e
here=$(cd "$(dirname "$0")" && pwd)
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
entry="$apps/g610-control.desktop"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/g610-control.desktop"

if [ "$1" = "--remove" ]; then
    rm -f "$entry" "$autostart"
    echo "Removed the menu and start-at-login entries."
    exit 0
fi

mkdir -p "$apps"
cd "$here"
python3 -c 'from g610ctl import autostart; print(autostart.desktop_entry(), end="")' > "$entry"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
echo "Installed $entry"
echo "G610 Control is now in your application menu."
