import json
import os
from pathlib import Path

from . import APP_ID

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_ID
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_SETTINGS = {
    # Mostra a janela quando aparece um stream de saída novo
    "popup_on_new_stream": True,
    # Mostra a janela quando um stream existente começa a tocar (descorked)
    "popup_on_playback_start": True,
    # Esconde a janela automaticamente após N segundos se aberta por evento (0 = nunca)
    "auto_hide_seconds": 20,
    # Intervalo mínimo entre popups do mesmo grupo
    "popup_cooldown_seconds": 15,
    # Reaplica o volume salvo do grupo quando um stream novo da instância aparece
    "restore_group_volume": True,
    "max_volume_percent": 150,
    "keep_on_top_when_popup": True,
    # Apps escondidos da lista (application.name ou binário)
    "hidden_apps": ["speech-dispatcher-dummy", "sd_dummy", "pactl"],
    # Apps que nunca disparam popup (ex.: navegador tocando música)
    "no_popup_apps": [],
    # Streams com media.role=event (sons de notificação) não disparam popup
    "ignore_event_sounds": True,
}


class Config:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.groups: dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except (OSError, ValueError):
            return
        self.settings.update(data.get("settings", {}))
        self.groups = data.get("groups", {})

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"settings": self.settings, "groups": self.groups}, indent=2, ensure_ascii=False))
        tmp.replace(CONFIG_FILE)

    def group(self, stable_key: str) -> dict:
        return self.groups.setdefault(stable_key, {})

    def set_group_value(self, stable_key: str, key: str, value):
        g = self.group(stable_key)
        if value is None:
            g.pop(key, None)
        else:
            g[key] = value
        self.save()
