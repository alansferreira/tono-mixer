#!/usr/bin/env bash
set -euo pipefail

WIDGETS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$WIDGETS_DIR/.." && pwd)"
PLUGIN_ID=io.github.alansferreira.tonomixer
PLUGIN_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/plasma/plasmoids/$PLUGIN_ID"

for dependency in python3 pactl kpackagetool6 systemctl; do
    command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done

if kpackagetool6 -t Plasma/Applet --show "$PLUGIN_ID" >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --upgrade "$WIDGETS_DIR/plasmoid"
else
    kpackagetool6 -t Plasma/Applet --install "$WIDGETS_DIR/plasmoid"
fi

mkdir -p "$PLUGIN_DIR/contents/code/audio_balance"
install -m 644 "$PROJECT_DIR/windowed/audio_balance/__init__.py" "$PROJECT_DIR/windowed/audio_balance/backend.py" \
    "$PLUGIN_DIR/contents/code/audio_balance/"

if systemctl --user cat linux-audio-balance.service >/dev/null 2>&1; then
    systemctl --user disable --now linux-audio-balance.service
fi

echo "Tono Mixer v2 installed. Add it to the Plasma panel or enable it in the system tray settings."
echo "The original application is still installed; its user service has been disabled."
