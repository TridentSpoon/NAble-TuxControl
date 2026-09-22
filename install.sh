#!/usr/bin/env bash
# Install NAble TuxControl to ~/.local (no root needed).
# Re-run after 'git pull' to upgrade; staged bundles are kept separately.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/nable-tuxcontrol-app"
BIN="$HOME/.local/bin"
SHARE_APPS="$HOME/.local/share/applications"
DESKTOP_ID="io.github.tridentspoon.TuxControl"

err() { echo "Error: $*" >&2; }

check_python() {
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        err "Python 3.8 or newer is required."
        exit 1
    fi
}

check_gtk() {
    if ! python3 -c "
import gi
gi.require_version('Adw', '1')
from gi.repository import Adw
import sys
sys.exit(0 if (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 5) else 1)
" 2>/dev/null; then
        echo "Note: libadwaita 1.5+ not found -- the CLI works; the GUI needs:"
        echo "  Arch:          sudo pacman -S python-gobject gtk4 libadwaita"
        echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
        echo "  Fedora:        sudo dnf install python3-gobject gtk4 libadwaita"
        echo "  openSUSE:      sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"
        echo ""
    fi
}

install_files() {
    mkdir -p "$DEST"
    rm -rf "$DEST/tuxcontrol"
    cp -r "$SRC_DIR/tuxcontrol" "$DEST/"
    cp "$SRC_DIR/tuxcontrol_cli.py" "$SRC_DIR/tuxcontrol_gui.py" "$DEST/"

    mkdir -p "$BIN"

    cat > "$BIN/tuxcontrol" << 'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/nable-tuxcontrol-app/tuxcontrol_cli.py" "$@"
EOF
    chmod +x "$BIN/tuxcontrol"

    cat > "$BIN/tuxcontrol-gui" << 'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/nable-tuxcontrol-app/tuxcontrol_gui.py" "$@"
EOF
    chmod +x "$BIN/tuxcontrol-gui"

    mkdir -p "$SHARE_APPS"
    cat > "$SHARE_APPS/${DESKTOP_ID}.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=NAble TuxControl
Comment=Install N-able Take Control on any Linux distro
Exec=tuxcontrol-gui
Icon=preferences-desktop-remote-desktop
Categories=Network;RemoteAccess;
Terminal=false
EOF
    update-desktop-database "$SHARE_APPS" 2>/dev/null || true
}

check_python
check_gtk
install_files

echo "Installed to $DEST"
echo "  CLI: tuxcontrol"
echo "  GUI: tuxcontrol-gui  (or find 'NAble TuxControl' in your app menu)"
echo ""
if [[ ":$PATH:" != *":$BIN:"* ]]; then
    echo "Add ~/.local/bin to your PATH, e.g.:"
    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi
