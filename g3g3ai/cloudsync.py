"""Copia en la nube a través de la carpeta de OneDrive o Google Drive del propio equipo.

G3G3AI no habla con Microsoft ni con Google: escribe un único archivo cifrado con tu contraseña
(PBKDF2-SHA256 + AES, el mismo formato que «Exportar copia») dentro de la carpeta que ya sincroniza su
aplicación de escritorio. En cada equipo se elige esa carpeta y la contraseña una vez; a partir de ahí:

  1. si el archivo de la nube cambió (otro equipo guardó), se mezcla con lo de aquí (gana lo más reciente
     de cada conversación, recuerdo, proyecto y ajuste, igual que la sincronización entre equipos);
  2. si aquí hay cambios, se vuelve a escribir el archivo.

Lo propio de cada equipo (carpetas, modelos, puerto, contraseña de acceso) no viaja.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path

from . import backup

SUBDIR = "G3G3AI"
FILENAME = "g3g3ai-nube.g3bak"
MAGIC = b"G3G3AI-CLOUD-1\n"
INTERVAL = 180          # segundos entre comprobaciones automáticas


class CloudError(Exception):
    pass


def candidates() -> list[dict]:
    """Carpetas de OneDrive y Google Drive encontradas en este equipo."""
    home = Path.home()
    found: list[tuple[str, Path]] = []
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(var):
            found.append(("OneDrive", Path(os.environ[var])))
    for p in sorted(home.glob("OneDrive*")):
        found.append(("OneDrive", p))
    # Google Drive para escritorio: unidad virtual (G:\Mi unidad) o carpeta en el perfil
    names = ("Mi unidad", "My Drive", "Meine Ablage", "Mon Drive")
    if sys.platform == "win32":
        for letter in "GHIJKLMNOPQRSTUVWXYZ":
            for n in names:
                found.append(("Google Drive", Path(f"{letter}:\\") / n))
    for base in (home / "Google Drive", home / "GoogleDrive", home / "google-drive", home / "My Drive"):
        found.append(("Google Drive", base))
        for n in names:
            found.append(("Google Drive", base / n))
    cloud = home / "Library" / "CloudStorage"                      # macOS
    if cloud.is_dir():
        for p in sorted(cloud.iterdir()):
            kind = "OneDrive" if p.name.startswith("OneDrive") else "Google Drive" if p.name.startswith("GoogleDrive") else None
            if kind:
                found.append((kind, p / "My Drive" if kind == "Google Drive" and (p / "My Drive").is_dir() else p))
    out, seen = [], set()
    for kind, p in found:
        try:
            if p.is_dir() and str(p.resolve()) not in seen:
                seen.add(str(p.resolve()))
                out.append({"kind": kind, "path": str(p), "has_copy": (p / SUBDIR / FILENAME).is_file()})
        except OSError:
            continue
    return out


def _seal(payload: bytes, password: str) -> bytes:
    salt = secrets.token_bytes(16)
    return MAGIC + base64.b64encode(salt) + b"\n" + backup._fernet(password, salt).encrypt(payload)


def _open(data: bytes, password: str) -> dict:
    from cryptography.fernet import InvalidToken
    if not data.startswith(MAGIC):
        raise CloudError("El archivo de la nube no es una copia de G3G3AI.")
    try:
        salt_b64, token = data[len(MAGIC):].split(b"\n", 1)
        return json.loads(backup._fernet(password, base64.b64decode(salt_b64)).decrypt(token))
    except (InvalidToken, ValueError) as e:
        raise CloudError("La contraseña no coincide con la de la copia que ya hay en la nube.") from e


class CloudSync:
    def __init__(self, cfg, sync):
        self.cfg, self.sync = cfg, sync
        self.state = {"last_pull": None, "last_push": None, "error": None, "running": False}
        self._mtime = None
        self._hash = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.cfg["cloud_dir"] and self.cfg["cloud_password"])

    @property
    def path(self) -> Path:
        return Path(self.cfg["cloud_dir"]).expanduser() / SUBDIR / FILENAME

    def status(self) -> dict:
        p = self.path if self.cfg["cloud_dir"] else None
        info = None
        if p and p.is_file():
            st = p.stat()
            info = {"size": st.st_size, "modified": st.st_mtime}
        return {"enabled": self.enabled, "dir": self.cfg["cloud_dir"], "file": str(p) if p else None, "remote": info,
                "conversations": bool(self.cfg["cloud_conversations"]), **self.state, "candidates": candidates()}

    # --- Operaciones (síncronas: se llaman en un hilo) ---------------------------------
    def _changes(self) -> dict:
        ch = self.sync.export(0)
        if not self.cfg["cloud_conversations"]:
            ch["conversations"] = []
        from .sync import SYNC_KEYS
        ch["settings"] = {"updated": self.cfg["settings_updated"] or 0, "values": {k: self.cfg[k] for k in SYNC_KEYS}}
        return ch

    def pull(self, password: str | None = None, force: bool = False) -> int:
        p = self.path
        if not p.is_file():
            return 0
        mtime = p.stat().st_mtime
        if not force and self._mtime == mtime:
            return 0
        doc = _open(p.read_bytes(), password or self.cfg["cloud_password"])
        n = self.sync.apply(doc.get("changes") or {})
        self._mtime = mtime
        self.state["last_pull"] = time.time()
        return n

    def push(self, force: bool = False) -> bool:
        ch = self._changes()
        h = hashlib.sha256(json.dumps(ch, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        if not force and h == self._hash and self.path.is_file():
            return False
        doc = {"app": "g3g3ai", "version": 1, "saved": time.time(), "device": socket.gethostname(), "changes": ch}
        data = _seal(json.dumps(doc, ensure_ascii=False).encode("utf-8"), self.cfg["cloud_password"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self.path)                    # nunca queda un archivo a medias en la nube
        self._hash = h
        self._mtime = self.path.stat().st_mtime
        self.state["last_push"] = time.time()
        return True

    def run_once(self, force: bool = False) -> dict:
        if not self.enabled:
            return {"pulled": 0, "pushed": False}
        try:
            pulled = self.pull(force=force)
            pushed = self.push(force=force)
            self.state["error"] = None
            return {"pulled": pulled, "pushed": pushed}
        except (CloudError, OSError) as e:
            self.state["error"] = str(e)
            raise

    def setup(self, folder: str, password: str, conversations: bool = True) -> dict:
        """Activa la copia: comprueba la carpeta y la contraseña, trae lo que haya y guarda lo de aquí."""
        if len(password or "") < 6:
            raise CloudError("Elige una contraseña de al menos 6 caracteres (la misma en todos tus equipos).")
        d = Path(folder).expanduser()
        if not d.is_dir():
            raise CloudError(f"No existe la carpeta {d}.")
        existing = d / SUBDIR / FILENAME
        if existing.is_file():
            _open(existing.read_bytes(), password)    # contraseña incorrecta → error, sin tocar nada
        self.cfg.update_public({"cloud_conversations": bool(conversations)})
        self.cfg.data["cloud_dir"], self.cfg.data["cloud_password"] = str(d), password
        self.cfg.save()
        self._mtime = self._hash = None
        return self.run_once(force=True)

    def disable(self) -> None:
        self.cfg.data["cloud_dir"], self.cfg.data["cloud_password"] = "", ""
        self.cfg.save()
        self._mtime = self._hash = None

    # --- Bucle automático -------------------------------------------------------------
    def start(self):
        async def loop():
            await asyncio.sleep(5)
            while True:
                if self.enabled:
                    async with self._lock:
                        try:
                            await asyncio.to_thread(self.run_once)
                        except Exception:  # noqa: BLE001  (el estado ya guarda el error para mostrarlo)
                            pass
                await asyncio.sleep(INTERVAL)
        self._task = asyncio.get_event_loop().create_task(loop())

    def stop(self):
        if self._task:
            self._task.cancel()

    async def now(self, force: bool = False) -> dict:
        async with self._lock:
            return await asyncio.to_thread(self.run_once, force)
