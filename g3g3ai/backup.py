"""Copia de seguridad cifrada de la configuración (con claves API), la memoria y, si quieres, las conversaciones.

El archivo se cifra con una contraseña (PBKDF2-SHA256 con sal aleatoria + Fernet = AES + HMAC). Sin la contraseña
no se puede leer, así que es seguro guardarlo en la nube o enviarlo a otro equipo. Se importa con «Ajustes → Copia
de seguridad». Lo propio de cada equipo (carpetas, modelos descargados, puerto, contraseña de acceso) no se incluye.
"""
from __future__ import annotations

import base64
import json
import secrets
import time

MAGIC = b"G3G3AI-BACKUP-1\n"
ITERATIONS = 600_000


class BackupError(Exception):
    pass


def _fernet(password: str, salt: bytes):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))


def export_bytes(sync, cfg, password: str, include_conversations: bool = False) -> bytes:
    if len(password or "") < 6:
        raise BackupError("Elige una contraseña de al menos 6 caracteres.")
    from .sync import SYNC_KEYS
    ch = sync.export(0)
    if not include_conversations:
        ch["conversations"] = []
    ch["tombstones"] = []
    ch["settings"] = {"updated": time.time(), "values": {k: cfg[k] for k in SYNC_KEYS}}
    payload = json.dumps({"app": "g3g3ai", "version": 1, "created": time.time(), "changes": ch},
                         ensure_ascii=False).encode("utf-8")
    salt = secrets.token_bytes(16)
    return MAGIC + base64.b64encode(salt) + b"\n" + _fernet(password, salt).encrypt(payload)


def import_bytes(sync, data: bytes, password: str) -> dict:
    """Aplica una copia. Devuelve un resumen de lo importado."""
    from cryptography.fernet import InvalidToken
    if not data.startswith(MAGIC):
        raise BackupError("Este archivo no es una copia de seguridad de G3G3AI.")
    try:
        salt_b64, token = data[len(MAGIC):].split(b"\n", 1)
        payload = _fernet(password, base64.b64decode(salt_b64)).decrypt(token)
        doc = json.loads(payload)
    except (InvalidToken, ValueError):
        raise BackupError("Contraseña incorrecta o archivo dañado.")
    ch = doc.get("changes") or {}
    ch.setdefault("settings", None)
    if ch.get("settings"):
        ch["settings"]["updated"] = time.time()  # lo importado manda sobre lo actual
    # lo que se importa «resucita» aunque se hubiera borrado aquí después (se quitan sus lápidas de borrado)
    for kind, key, items in (("memory", "uid", ch.get("memories", [])), ("conversation", "id", ch.get("conversations", []))):
        for it in items:
            sync.db._q("DELETE FROM tombstones WHERE kind=? AND uid=?", (kind, it.get(key) or it.get("uid")))
    n = sync.apply(ch)
    return {"settings": bool(ch.get("settings")), "memories": len(ch.get("memories", [])),
            "conversations": len(ch.get("conversations", [])), "applied": n}
