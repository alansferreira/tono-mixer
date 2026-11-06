#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID=io.github.alansferreira.tonomixer
kpackagetool6 -t Plasma/Applet --remove "$PLUGIN_ID"

echo "Tono Mixer v2 removed. Its configuration remains in ${XDG_CONFIG_HOME:-$HOME/.config}/tono-mixer-v2."
echo "To restore the original service: systemctl --user enable --now linux-audio-balance.service"
