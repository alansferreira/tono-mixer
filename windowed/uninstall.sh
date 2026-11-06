#!/usr/bin/env bash
set -euo pipefail
APP_ID=linux-audio-balance
systemctl --user disable --now "$APP_ID.service" 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$APP_ID.service" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP_ID.desktop" \
      "$HOME/.local/bin/audio-balance"
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
systemctl --user daemon-reload
echo "Removido. Configuração mantida em ${XDG_CONFIG_HOME:-$HOME/.config}/$APP_ID/"
