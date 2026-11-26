"""Historial de conversaciones en SQLite."""
from __future__ import annotations

import json
import sqlite3
import threading
import unicodedata
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    system TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    reasoning TEXT,
    meta TEXT,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id, id);
CREATE TABLE IF NOT EXISTS tombstones (
    kind TEXT NOT NULL,
    uid TEXT NOT NULL,
    deleted REAL NOT NULL,
    PRIMARY KEY (kind, uid)
);
"""


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def snippet(text: str, words: list[str], width: int = 160) -> str:
    """Fragmento alrededor de la primera coincidencia (la posición se calcula sobre el texto normalizado,
    que tiene la misma longitud que el original salvo en casos raros de Unicode)."""
    n = norm(text)
    pos = min((n.find(w) for w in words if n.find(w) >= 0), default=0)
    if len(n) != len(text):
        pos = 0
    start = max(0, pos - width // 3)
    frag = " ".join(text[start:start + width].split())
    return ("…" if start else "") + frag + ("…" if start + width < len(text) else "")


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("norm", 1, norm, deterministic=True)   # búsqueda sin tildes ni mayúsculas
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        for table, col in (("conversations", "summary TEXT"), ("conversations", "summary_upto INTEGER"),
                           ("messages", "uid TEXT"), ("conversations", "workdir TEXT")):  # columnas añadidas en versiones posteriores
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        # Identificador global de cada mensaje (para sincronizar entre equipos)
        for (mid,) in self.conn.execute("SELECT id FROM messages WHERE uid IS NULL").fetchall():
            self.conn.execute("UPDATE messages SET uid=? WHERE id=?", (uuid.uuid4().hex, mid))
        self.conn.commit()
        self.lock = threading.Lock()

    def _q(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    # Conversaciones ---------------------------------------------------------
    def list_conversations(self) -> list[dict]:
        rows = self._q(
            "SELECT id, title, provider, model, updated FROM conversations ORDER BY updated DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 30) -> list[dict]:
        """Conversaciones cuyo título o mensajes contienen todas las palabras (sin tildes ni mayúsculas)."""
        words = [w for w in norm(query).split() if w][:8]
        if not words:
            return []
        like = [f"%{w.replace('%', '').replace('_', '')}%" for w in words]
        where = " AND ".join("norm(m.content) LIKE ?" for _ in words)
        rows = self._q(
            f"SELECT m.id, m.conv_id, m.role, m.content, c.title, c.updated FROM messages m "
            f"JOIN conversations c ON c.id = m.conv_id WHERE m.role IN ('user','assistant') AND {where} "
            f"ORDER BY c.updated DESC, m.id LIMIT 400", like).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            o = out.setdefault(r["conv_id"], {"id": r["conv_id"], "title": r["title"], "updated": r["updated"],
                                              "hits": 0, "message_id": r["id"], "role": r["role"],
                                              "snippet": snippet(r["content"], words)})
            o["hits"] += 1
        twhere = " AND ".join("norm(title) LIKE ?" for _ in words)
        for r in self._q(f"SELECT id, title, updated FROM conversations WHERE {twhere} ORDER BY updated DESC LIMIT 50", like):
            out.setdefault(r["id"], {"id": r["id"], "title": r["title"], "updated": r["updated"], "hits": 0,
                                     "message_id": None, "role": None, "snippet": ""})
        return sorted(out.values(), key=lambda o: -o["updated"])[:limit]

    def create_conversation(self, title="Nueva conversación", provider=None, model=None, system=None) -> dict:
        cid = uuid.uuid4().hex[:12]
        now = time.time()
        self._q(
            "INSERT INTO conversations (id, title, provider, model, system, created, updated) VALUES (?,?,?,?,?,?,?)",
            (cid, title, provider, model, system, now, now),
        )
        return self.get_conversation(cid)

    def get_conversation(self, cid: str) -> dict | None:
        row = self._q("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        conv = dict(row)
        msgs = self._q(
            "SELECT id, uid, role, content, reasoning, meta, created FROM messages WHERE conv_id=? ORDER BY id", (cid,)
        ).fetchall()
        conv["messages"] = [
            {**dict(m), "meta": json.loads(m["meta"]) if m["meta"] else None} for m in msgs
        ]
        return conv

    def update_conversation(self, cid: str, **fields) -> None:
        keys = [k for k in ("title", "provider", "model", "system", "workdir") if k in fields]
        if not keys:
            return
        sets = ", ".join(f"{k}=?" for k in keys)
        self._q(
            f"UPDATE conversations SET {sets}, updated=? WHERE id=?",
            (*[fields[k] for k in keys], time.time(), cid),
        )

    def delete_conversation(self, cid: str) -> None:
        self._q("DELETE FROM messages WHERE conv_id=?", (cid,))
        self._q("DELETE FROM conversations WHERE id=?", (cid,))
        self.tombstone("conversation", cid)

    def tombstone(self, kind: str, uid: str, when: float | None = None) -> None:
        self._q("INSERT OR REPLACE INTO tombstones (kind, uid, deleted) VALUES (?,?,?)", (kind, uid, when or time.time()))

    # Mensajes ---------------------------------------------------------------
    def add_message(self, cid: str, role: str, content: str, reasoning: str | None = None, meta: dict | None = None) -> int:
        now = time.time()
        cur = self._q(
            "INSERT INTO messages (conv_id, uid, role, content, reasoning, meta, created) VALUES (?,?,?,?,?,?,?)",
            (cid, uuid.uuid4().hex, role, content, reasoning, json.dumps(meta, ensure_ascii=False) if meta else None, now),
        )
        self._q("UPDATE conversations SET updated=? WHERE id=?", (now, cid))
        return cur.lastrowid

    def assistant_usage(self, since: float) -> list[dict]:
        rows = self._q("SELECT meta, created FROM messages WHERE role='assistant' AND created>=? AND meta LIKE '%\"usage\"%'",
                       (since,)).fetchall()
        return [{"meta": json.loads(r["meta"]), "created": r["created"]} for r in rows]

    def delete_messages_from(self, cid: str, message_id: int) -> None:
        """Borra un mensaje y todos los posteriores (para editar/regenerar)."""
        self._q("DELETE FROM messages WHERE conv_id=? AND id>=?", (cid, message_id))
        self._q("UPDATE conversations SET updated=? WHERE id=?", (time.time(), cid))
        # Si el resumen cubría mensajes borrados, se descarta
        self._q("UPDATE conversations SET summary=NULL, summary_upto=NULL WHERE id=? AND summary_upto>=?",
                (cid, message_id))

    def update_message_meta(self, message_id: int, meta: dict) -> None:
        self._q("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), message_id))

    def set_summary(self, cid: str, summary: str, upto: int) -> None:
        self._q("UPDATE conversations SET summary=?, summary_upto=? WHERE id=?", (summary, upto, cid))
