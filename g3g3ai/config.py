"""Configuración persistente de G3G3AI (JSON en ~/.config/g3g3ai/config.json)."""
from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

APP = "g3g3ai"
HOME = Path.home()
CONFIG_VERSION = 4


def _default_dirs() -> tuple[Path, Path]:
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA") or HOME / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local")
        return roaming / "G3G3AI", local / "G3G3AI"
    if sys.platform == "darwin":
        base = HOME / "Library" / "Application Support" / "G3G3AI"
        return base, base
    return HOME / ".config" / APP, HOME / ".local" / "share" / APP


_CFG, _DATA = _default_dirs()
CONFIG_DIR = Path(os.environ.get("G3G3AI_CONFIG_DIR") or _CFG)
DATA_DIR = Path(os.environ.get("G3G3AI_DATA_DIR") or _DATA)
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
    # Carpetas que la IA puede modificar (y únicas escribibles por sus comandos aislados).
    "write_roots": [str(HOME / "G3G3AI-trabajo")],
    # Rutas protegidas: nadie las ve desde G3G3AI (ni la IA ni la interfaz remota).
    "blocked_paths": [],  # se rellena con default_blocked() al crear la configuración
    # Aislamiento de comandos (Linux: bubblewrap). "auto" = usarlo si está disponible.
    "command_sandbox": "auto",
    # Visión: modelo que describe imágenes a los modelos que no las ven ("" = el local si tiene visión)
    "vision_fallback": "",
    # Contexto máximo (tokens aprox.) que se envía a modelos por API antes de resumir lo antiguo
    "context_budget": 60000,
    # Generación de imágenes: "" (desactivada) | "local" | id de un proveedor API
    "image_provider": "",
    "image_model": "",          # p.ej. gpt-image-1, imagen-3.0-generate-002, google/gemini-2.5-flash-image
    "image_mode": "auto",       # auto | images (/images/generations) | chat (OpenRouter)
    "image_size": "1024x1024",
    "image_dir": "",            # vacío = ~/G3G3AI-imagenes
    "sd_path": "",              # ejecutable de stable-diffusion.cpp (vacío = autodetectar)
    "sd_model": "",             # modelo local de imagen (.gguf / .safetensors)
    "sd_steps": 4,              # 1-4 para modelos «turbo»; 20+ para modelos normales
    "sd_cfg": 1.0,              # 1.0 para «turbo»; ~7 para modelos normales
    "sd_max_side": 512,         # límite de tamaño en local (la Konkr tarda mucho con imágenes grandes)
    # Ollama (motor local alternativo)
    "ollama_url": "http://127.0.0.1:11434",
    # Python del entorno de compilación (vacío = el de G3G3AI en la carpeta de datos)
    "devenv_python": "",
    # Juegos de Steam: la IA puede leer y (siempre pidiendo permiso) modificar carpetas de juegos y prefijos de Proton
    "ai_game_write": True,
    "steam_dir": "",            # vacío = autodetectar
    # Sincronización entre equipos
    "device_id": "",
    "sync_key": "",             # clave común en todos los equipos que se sincronizan
    "sync_peers": [],           # [{"url": "http://192.168.1.50:8800", "name": "..."}]
    "settings_updated": 0,      # cuándo se cambiaron por última vez los ajustes comunes
    # Memoria entre conversaciones
    "memory_enabled": True,     # usar los recuerdos como contexto
    "memory_auto": True,        # la IA puede guardar recuerdos por su cuenta (se ve en el chat)
    "memory_api": True,         # enviar la memoria también a modelos por API (si no, sólo al local)
    # Búsqueda web
    "web_provider": "duckduckgo",  # duckduckgo | brave | tavily
    "web_api_key": "",
    # Permisos del modo agente: "off" | "ask" (pide confirmación) | "auto"
    "ai_write": "ask",
    "ai_commands": "ask",
    "agent_workdir": str(HOME / "G3G3AI-trabajo"),
    # Modo Auto: alterna entre un modelo rápido (local) y uno potente (API).
    "router_mode": "smart",  # smart | local_first | api_first
    "router_fast": "local::local",
    "router_strong": "deepseek::deepseek-chat",
    # Chat
    "default_system_prompt": "Eres un asistente útil. Responde en el idioma del usuario.",
    "temperature": 0.7,
    "max_tokens": 8192,
    # Proveedores API externos.
    "providers": [
        {
            "id": "ollama",
            "name": "Ollama (local)",
            "type": "openai",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key": "",
            "enabled": False,
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "type": "openai",
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "enabled": False,
        },
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
        {
            "id": "gemini",
            "name": "Google Gemini",
            "type": "openai",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "",
            "enabled": False,
        },
        {
            "id": "groq",
            "name": "Groq",
            "type": "openai",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "",
            "enabled": False,
        },
    ],
    "config_version": CONFIG_VERSION,
}

SECRET_KEYS = {"token", "hf_token", "web_api_key", "sync_key"}


def default_blocked() -> list[str]:
    """Secretos y datos personales que la IA nunca debería leer."""
    items = [
        "~/.ssh", "~/.gnupg", "~/.aws", "~/.azure", "~/.kube", "~/.docker", "~/.password-store",
        "~/.local/share/keyrings", "~/.mozilla", "~/.thunderbird", "~/.config/chromium",
        "~/.config/google-chrome", "~/.config/BraveSoftware", "~/.config/microsoft-edge",
        "~/.var/app/org.chromium.Chromium", "~/.var/app/com.google.Chrome", "~/.var/app/org.mozilla.firefox",
        "~/.var/app/com.brave.Browser", "~/.local/share/Steam/config", "~/.steam/steam/config",
        "~/.config/gh", "~/.local/share/g3g3ai/g3g3ai.db",
        str(CONFIG_DIR),
        ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "id_rsa*", "id_ed25519*", "id_ecdsa*",
        ".netrc", ".git-credentials", ".pgpass", "credentials.json",
    ]
    if sys.platform == "win32":
        items += [
            "~/AppData/Local/Google/Chrome/User Data", "~/AppData/Local/Microsoft/Edge/User Data",
            "~/AppData/Roaming/Mozilla", "~/AppData/Local/BraveSoftware", "~/AppData/Roaming/Microsoft/Credentials",
            "~/AppData/Local/Microsoft/Credentials", str(DATA_DIR / "g3g3ai.db"),
        ]
    if sys.platform == "darwin":
        items += ["~/Library/Keychains", "~/Library/Application Support/Google/Chrome",
                  "~/Library/Application Support/Firefox", "~/Library/Cookies"]
    return items


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self._stored_keys: set = set()
        self._lock = threading.Lock()
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text("utf-8"))
                self.data.update(stored)
                self._stored_keys = set(stored)
            except (OSError, json.JSONDecodeError):
                pass
        changed = self._migrate()
        if not self.data.get("blocked_paths"):
            self.data["blocked_paths"] = default_blocked()
            changed = True
        if not self.data.get("token"):
            self.data["token"] = secrets.token_urlsafe(9)
            changed = True
        if changed or not self.path.exists():
            self.save()

    def _migrate(self) -> bool:
        d = self.data
        if d.get("config_version", 1) >= CONFIG_VERSION:
            return False
        if d.get("config_version", 1) < 4:  # v4: proveedor Ollama
            have = {p.get("id") for p in d.get("providers", [])}
            if "ollama" not in have:
                d.setdefault("providers", []).insert(0, copy.deepcopy(DEFAULTS["providers"][0]))
        if "write_roots" not in self._stored_keys and d.get("agent_workdir"):
            # v3: la carpeta de trabajo del agente pasa a ser la carpeta modificable inicial
            d["write_roots"] = [d["agent_workdir"]]
        if d.get("config_version", 1) >= 2:
            d["config_version"] = CONFIG_VERSION
            return True
        if "allow_ai_file_write" in d:
            d["ai_write"] = "auto" if d.pop("allow_ai_file_write") else "off"
        have = {p.get("id") for p in d.get("providers", [])}
        for p in DEFAULTS["providers"]:
            if p["id"] not in have:
                d.setdefault("providers", []).append(copy.deepcopy(p))
        d["config_version"] = CONFIG_VERSION
        return True

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
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
        from .sync import SYNC_KEYS
        allowed = set(DEFAULTS) - {"last_model", "config_version", "device_id", "settings_updated"}
        before = {k: copy.deepcopy(self.data.get(k)) for k in SYNC_KEYS}
        for key, value in incoming.items():
            if key not in allowed:
                continue
            if key in SECRET_KEYS and value == MASK:
                continue
            if key == "sync_peers":
                old_peers = {p.get("url"): p for p in self.data.get("sync_peers", [])}
                value = [{**old_peers.get(p.get("url"), {}), **p} for p in value if p.get("url")]
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
        if any(self.data.get(k) != before[k] for k in SYNC_KEYS):
            self.data["settings_updated"] = time.time()
        self.save()

    def provider(self, pid: str) -> dict | None:
        for p in self.data.get("providers", []):
            if p.get("id") == pid:
                return p
        return None
