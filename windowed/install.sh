#!/usr/bin/env bash
# Instala o Tono Mixer para o usuário atual e ativa o serviço (systemd --user).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
APP_ID=linux-audio-balance
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
BIN="$HOME/.local/bin/audio-balance"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

for dep in python3 pactl; do
    command -v "$dep" >/dev/null || { echo "Falta dependência: $dep" >&2; exit 1; }
done
python3 -c 'import PyQt6.QtWidgets, PyQt6.QtNetwork' 2>/dev/null || {
    echo "Falta PyQt6: sudo apt install python3-pyqt6" >&2; exit 1; }

# Copia (em vez de linkar) para funcionar mesmo se o disco do repositório não estiver montado no login.
mkdir -p "$PREFIX" "$(dirname "$BIN")" "$UNIT_DIR" "$APPS_DIR"
rm -rf "$PREFIX/audio_balance"
cp -r "$SRC/audio_balance" "$PREFIX/"
find "$PREFIX" -name '__pycache__' -prune -exec rm -rf {} +

cat > "$BIN" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$PREFIX\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m audio_balance "\$@"
EOF
chmod +x "$BIN"

install -m644 "$SRC/packaging/$APP_ID.desktop" "$APPS_DIR/$APP_ID.desktop"
install -m644 "$SRC/packaging/$APP_ID.service" "$UNIT_DIR/$APP_ID.service"

systemctl --user daemon-reload
systemctl --user enable "$APP_ID.service"
if systemctl --user is-active --quiet graphical-session.target; then
    systemctl --user restart "$APP_ID.service"
fi

echo "Instalado. Serviço: systemctl --user status $APP_ID"
echo "Abrir janela: audio-balance  |  Listar grupos: audio-balance --list"
