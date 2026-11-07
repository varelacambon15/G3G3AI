"""Sincronización entre equipos con G3G3AI (p.ej. Konkr ↔ PC).

- Los equipos se emparejan con una **clave de sincronización** común (se genera en uno y se pega en el otro)
  y la dirección del otro equipo.
- Todo lo que viaja va cifrado y autenticado con esa clave (Fernet = AES + HMAC). Sin la clave no se puede
  leer ni enviar nada, aunque se esté en la misma red.
- Se sincronizan conversaciones, memoria y los ajustes comunes (proveedores con sus claves API, modo Auto,
  imágenes, web, instrucciones…). Lo propio de cada equipo (carpetas, modelos locales, puerto, contraseña)
  no se toca.
- Regla de conflictos: gana el cambio más reciente. Los borrados también se sincronizan.
"""
from __future__ import annotations

import asyncio
import base64
import json
import secrets
import socket
import time
import uuid

import httpx

SYNC_KEYS = [
    "providers", "default_system_prompt", "temperature", "max_tokens",
    "router_mode", "router_fast", "router_strong", "ai_write", "ai_commands",
    "web_provider", "web_api_key", "hf_token", "memory_enabled", "memory_auto", "memory_api",
    "vision_fallback", "context_budget", "image_provider", "image_model", "image_mode", "image_size",
    "sd_steps", "sd_cfg",
]
INTERVAL = 120  # segundos entre sincronizaciones automáticas
SALT = b"g3g3ai-sync-v1"


class SyncError(Exception):
    pass


def new_key() -> str:
    """Clave legible para copiar a mano: 6 grupos de 4 caracteres."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(24))
    return "-".join(raw[i:i + 4] for i in range(0, 24, 4))


def _fernet(key: str):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    norm = "".join(key.upper().split()).replace("-", "")
    if len(norm) < 12:
        raise SyncError("La clave de sincronización es demasiado corta.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=SALT, iterations=200_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(norm.encode())))


class Sync:
    def __init__(self, cfg, db, memory):
        self.cfg = cfg
        self.db = db
        self.memory = memory
        self.status: dict[str, dict] = {}   # url -> {ok, when, message, received, sent}
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._fernet_cache: tuple[str, object] | None = None
        if not cfg["device_id"]:
            cfg.set("device_id", uuid.uuid4().hex[:12])

    # Cifrado ----------------------------------------------------------------------
    def fernet(self):
        key = self.cfg["sync_key"] or ""
        if not key:
            raise SyncError("No hay clave de sincronización.")
        if not self._fernet_cache or self._fernet_cache[0] != key:
            self._fernet_cache = (key, _fernet(key))
        return self._fernet_cache[1]

    def seal(self, obj) -> bytes:
        return self.fernet().encrypt(json.dumps(obj, ensure_ascii=False).encode())

    def open(self, token: bytes) -> dict:
        from cryptography.fernet import InvalidToken
        try:
            return json.loads(self.fernet().decrypt(token, ttl=600))
        except InvalidToken as e:
            raise SyncError("Clave de sincronización distinta en el otro equipo.") from e

    # Exportar / importar ------------------------------------------------------------
    def export(self, since: float) -> dict:
        q = self.db._q
        convs = []
        for row in q("SELECT * FROM conversations WHERE updated > ?", (since,)).fetchall():
            c = dict(row)
            msgs = q("SELECT id, uid, role, content, reasoning, meta, created FROM messages WHERE conv_id=? ORDER BY id",
                     (c["id"],)).fetchall()
            upto_uid = None
            for m in msgs:
                if c.get("summary_upto") and m["id"] == c["summary_upto"]:
                    upto_uid = m["uid"]
            c["summary_upto_uid"] = upto_uid
            c.pop("summary_upto", None)
            c["messages"] = [{k: m[k] for k in ("uid", "role", "content", "reasoning", "meta", "created")} for m in msgs]
            convs.append(c)
        mems = [dict(r) for r in q("SELECT uid, content, source, created, updated FROM memories WHERE updated > ?",
                                   (since,)).fetchall()]
        tombs = [dict(r) for r in q("SELECT kind, uid, deleted FROM tombstones WHERE deleted > ?", (since,)).fetchall()]
        out = {"conversations": convs, "memories": mems, "tombstones": tombs}
        if (self.cfg["settings_updated"] or 0) > since:
            out["settings"] = {"updated": self.cfg["settings_updated"],
                               "values": {k: self.cfg[k] for k in SYNC_KEYS}}
        return out

    def apply(self, ch: dict) -> int:
        """Aplica cambios recibidos. Devuelve cuántos elementos se actualizaron."""
        q, n = self.db._q, 0
        tomb = {(t["kind"], t["uid"]): t["deleted"]
                for t in (dict(r) for r in q("SELECT kind, uid, deleted FROM tombstones").fetchall())}
        for t in ch.get("tombstones", []):
            key = (t["kind"], t["uid"])
            if t["deleted"] <= tomb.get(key, 0):
                continue
            if t["kind"] == "conversation":
                row = q("SELECT updated FROM conversations WHERE id=?", (t["uid"],)).fetchone()
                if row and row["updated"] < t["deleted"]:
                    q("DELETE FROM messages WHERE conv_id=?", (t["uid"],))
                    q("DELETE FROM conversations WHERE id=?", (t["uid"],))
                    n += 1
            elif t["kind"] == "memory":
                row = q("SELECT updated FROM memories WHERE uid=?", (t["uid"],)).fetchone()
                if row and row["updated"] < t["deleted"]:
                    q("DELETE FROM memories WHERE uid=?", (t["uid"],))
                    n += 1
            self.db.tombstone(t["kind"], t["uid"], t["deleted"])
            tomb[key] = t["deleted"]

        for c in ch.get("conversations", []):
            if tomb.get(("conversation", c["id"]), 0) >= c["updated"]:
                continue
            row = q("SELECT updated FROM conversations WHERE id=?", (c["id"],)).fetchone()
            if row and row["updated"] >= c["updated"]:
                continue
            with self.db.lock:
                conn = self.db.conn
                conn.execute("DELETE FROM messages WHERE conv_id=?", (c["id"],))
                conn.execute("INSERT OR REPLACE INTO conversations (id, title, provider, model, system, created, updated,"
                             " summary, summary_upto) VALUES (?,?,?,?,?,?,?,?,NULL)",
                             (c["id"], c["title"], c.get("provider"), c.get("model"), c.get("system"), c["created"],
                              c["updated"], c.get("summary")))
                upto = None
                for m in c["messages"]:
                    cur = conn.execute("INSERT INTO messages (conv_id, uid, role, content, reasoning, meta, created) "
                                       "VALUES (?,?,?,?,?,?,?)",
                                       (c["id"], m["uid"], m["role"], m["content"], m.get("reasoning"), m.get("meta"),
                                        m["created"]))
                    if m["uid"] == c.get("summary_upto_uid"):
                        upto = cur.lastrowid
                if upto:
                    conn.execute("UPDATE conversations SET summary_upto=? WHERE id=?", (upto, c["id"]))
                conn.commit()
            n += 1

        for m in ch.get("memories", []):
            if tomb.get(("memory", m["uid"]), 0) >= m["updated"]:
                continue
            row = q("SELECT updated FROM memories WHERE uid=?", (m["uid"],)).fetchone()
            if row and row["updated"] >= m["updated"]:
                continue
            if row:
                q("UPDATE memories SET content=?, source=?, updated=? WHERE uid=?",
                  (m["content"], m.get("source"), m["updated"], m["uid"]))
            else:
                q("INSERT INTO memories (uid, content, source, created, updated) VALUES (?,?,?,?,?)",
                  (m["uid"], m["content"], m.get("source"), m["created"], m["updated"]))
            n += 1

        st = ch.get("settings")
        if st and st["updated"] > (self.cfg["settings_updated"] or 0):
            for k, v in st["values"].items():
                if k in SYNC_KEYS:
                    self.cfg.data[k] = v
            self.cfg.data["settings_updated"] = st["updated"]
            self.cfg.save()
            n += 1
        return n

    # Protocolo ----------------------------------------------------------------------
    def handle(self, token: bytes) -> bytes:
        """Lado servidor: recibe cambios de otro equipo y devuelve los propios."""
        req = self.open(token)
        if req.get("device") == self.cfg["device_id"]:
            raise SyncError("Es este mismo equipo.")
        now = time.time()
        received = self.apply(req.get("changes") or {})
        changes = self.export(float(req.get("since") or 0))
        self.status[f"recibido de {req.get('name') or req.get('device')}"] = {
            "ok": True, "when": now, "message": "", "received": received,
            "sent": len(changes["conversations"]) + len(changes["memories"])}
        return self.seal({"device": self.cfg["device_id"], "name": socket.gethostname(), "now": now,
                          "changes": changes})

    async def sync_peer(self, peer: dict) -> dict:
        url = peer["url"].rstrip("/")
        started = time.time()
        changes = self.export(float(peer.get("last_sent") or 0))
        body = self.seal({"device": self.cfg["device_id"], "name": socket.gethostname(),
                          "since": peer.get("last_recv") or 0, "changes": changes})
        async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
            r = await c.post(f"{url}/api/sync/exchange", content=body,
                             headers={"Content-Type": "application/octet-stream"})
        if r.status_code == 403:
            raise SyncError("El otro equipo tiene otra clave de sincronización (o no la tiene configurada).")
        if r.status_code >= 400:
            raise SyncError(f"El otro equipo respondió {r.status_code}: {r.text[:200]}")
        resp = self.open(r.content)
        received = self.apply(resp.get("changes") or {})
        peer["last_sent"] = started
        peer["last_recv"] = resp["now"]
        peer["name"] = peer.get("name") or resp.get("name")
        return {"ok": True, "when": time.time(), "message": "", "received": received,
                "sent": len(changes["conversations"]) + len(changes["memories"]) + (1 if "settings" in changes else 0),
                "remote": resp.get("name")}

    async def sync_all(self) -> dict:
        async with self._lock:
            if not self.cfg["sync_key"]:
                return self.status
            peers = self.cfg["sync_peers"] or []
            for peer in peers:
                try:
                    self.status[peer["url"]] = await self.sync_peer(peer)
                except (SyncError, httpx.HTTPError, ValueError, KeyError) as e:
                    self.status[peer["url"]] = {"ok": False, "when": time.time(), "message": str(e) or type(e).__name__}
            self.cfg.data["sync_peers"] = peers
            self.cfg.save()
            return self.status

    def start(self):
        async def loop():
            while True:
                await asyncio.sleep(INTERVAL)
                try:
                    await self.sync_all()
                except Exception:  # noqa: BLE001 — el bucle no debe morir
                    pass
        self._task = asyncio.create_task(loop())

    def stop(self):
        if self._task:
            self._task.cancel()
