"""Historial de conversaciones en SQLite."""
from __future__ import annotations

import json
import sqlite3
import threading
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
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        for col in ("summary TEXT", "summary_upto INTEGER"):  # columnas añadidas en v0.4
            try:
                self.conn.execute(f"ALTER TABLE conversations ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
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
            "SELECT id, role, content, reasoning, meta, created FROM messages WHERE conv_id=? ORDER BY id", (cid,)
        ).fetchall()
        conv["messages"] = [
            {**dict(m), "meta": json.loads(m["meta"]) if m["meta"] else None} for m in msgs
        ]
        return conv

    def update_conversation(self, cid: str, **fields) -> None:
        keys = [k for k in ("title", "provider", "model", "system") if k in fields]
        if not keys:
            return
        sets = ", ".join(f"{k}=?" for k in keys)
        self._q(
            f"UPDATE conversations SET {sets}, updated=? WHERE id=?",
            (*[fields[k] for k in keys], time.time(), cid),
        )

    def delete_conversation(self, cid: str) -> None:
        self._q("DELETE FROM conversations WHERE id=?", (cid,))

    # Mensajes ---------------------------------------------------------------
    def add_message(self, cid: str, role: str, content: str, reasoning: str | None = None, meta: dict | None = None) -> int:
        now = time.time()
        cur = self._q(
            "INSERT INTO messages (conv_id, role, content, reasoning, meta, created) VALUES (?,?,?,?,?,?)",
            (cid, role, content, reasoning, json.dumps(meta, ensure_ascii=False) if meta else None, now),
        )
        self._q("UPDATE conversations SET updated=? WHERE id=?", (now, cid))
        return cur.lastrowid

    def delete_messages_from(self, cid: str, message_id: int) -> None:
        """Borra un mensaje y todos los posteriores (para editar/regenerar)."""
        self._q("DELETE FROM messages WHERE conv_id=? AND id>=?", (cid, message_id))
        # Si el resumen cubría mensajes borrados, se descarta
        self._q("UPDATE conversations SET summary=NULL, summary_upto=NULL WHERE id=? AND summary_upto>=?",
                (cid, message_id))

    def update_message_meta(self, message_id: int, meta: dict) -> None:
        self._q("UPDATE messages SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), message_id))

    def set_summary(self, cid: str, summary: str, upto: int) -> None:
        self._q("UPDATE conversations SET summary=?, summary_upto=? WHERE id=?", (summary, upto, cid))
