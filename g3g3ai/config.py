"""Configuración persistente de G3G3AI (JSON en ~/.config/g3g3ai/config.json)."""
from __future__ import annotations

import copy
import json
import os
import secrets
import threading
from pathlib import Path

APP = "g3g3ai"
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("G3G3AI_CONFIG_DIR", HOME / ".config" / APP))
DATA_DIR = Path(os.environ.get("G3G3AI_DATA_DIR", HOME / ".local" / "share" / APP))
CONFIG_FILE = CONFIG_DIR / "config.json"

MASK = "••••••••"

DEFAULTS: dict = {
    # Red: 0.0.0.0 = accesible desde otros dispositivos de la red local.
    "host": "0.0.0.0",
    "port": 8800,
    # Contraseña de acceso para móvil/portátil. Se genera en el primer arranque.
    "token": "",
    # Si es True, el propio Konkr (127.0.0.1) entra sin contraseña.
    "localhost_without_token": True,
    # Modelos GGUF descargados.
    "models_dir": str(HOME / "Models"),
    # llama.cpp
    "llama_server_path": "",  # vacío = autodetectar
    "llama_port": 8801,
    "llama_ctx": 8192,
    "llama_threads": 0,  # 0 = automático
    "llama_gpu_layers": 0,  # >0 sólo si compilaste con Vulkan
    "llama_extra_args": "",
    "autoload_last_model": True,
    "last_model": "",
    # Hugging Face (opcional, para modelos restringidos)
    "hf_token": "",
    # Archivos: carpetas a las que la interfaz y la IA pueden acceder.
    "file_roots": [str(HOME)],
    "allow_ai_file_write": False,
    # Chat
    "default_system_prompt": "Eres un asistente útil. Responde en el idioma del usuario.",
    "temperature": 0.7,
    "max_tokens": 2048,
    # Proveedores API externos.
    "providers": [
        {
            "id": "openai",
            "name": "OpenAI",
            "type": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "enabled": False,
        },
        {
            "id": "anthropic",
            "name": "Anthropic (Claude)",
            "type": "anthropic",
            "base_url": "https://api.anthropic.com",
            "api_key": "",
            "enabled": False,
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "type": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "",
            "enabled": False,
        },
    ],
}

SECRET_KEYS = {"token", "hf_token"}


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text("utf-8"))
                self.data.update(stored)
            except (OSError, json.JSONDecodeError):
                pass
        changed = False
        if not self.data.get("token"):
            self.data["token"] = secrets.token_urlsafe(9)
            changed = True
        if changed or not self.path.exists():
            self.save()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    # --- Vista pública (sin secretos) -------------------------------------
    def public(self) -> dict:
        out = copy.deepcopy(self.data)
        for k in SECRET_KEYS:
            if out.get(k):
                out[k] = MASK
        for p in out.get("providers", []):
            if p.get("api_key"):
                p["api_key"] = MASK
        return out

    def update_public(self, incoming: dict) -> None:
        """Aplica cambios llegados de la interfaz, conservando secretos enmascarados."""
        allowed = set(DEFAULTS) - {"last_model"}
        for key, value in incoming.items():
            if key not in allowed:
                continue
            if key in SECRET_KEYS and value == MASK:
                continue
            if key == "providers":
                old = {p["id"]: p for p in self.data.get("providers", [])}
                merged = []
                for p in value:
                    p = dict(p)
                    if p.get("api_key") == MASK and p.get("id") in old:
                        p["api_key"] = old[p["id"]].get("api_key", "")
                    merged.append(p)
                value = merged
            self.data[key] = value
        self.save()

    def provider(self, pid: str) -> dict | None:
        for p in self.data.get("providers", []):
            if p.get("id") == pid:
                return p
        return None
