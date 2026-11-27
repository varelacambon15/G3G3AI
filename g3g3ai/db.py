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
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL DEFAULT '[]',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS branches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    born REAL NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_branches_conv ON branches(conv_id, position);
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


class _Result:
    """Resultado ya leído de una consulta (con la misma interfaz que el cursor que se usaba)."""
    __slots__ = ("lastrowid", "rowcount", "_rows")

    def __init__(self, cur, rows):
        self.lastrowid, self.rowcount, self._rows = cur.lastrowid, cur.rowcount, rows or []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


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
                           ("messages", "uid TEXT"), ("conversations", "workdir TEXT"),
                           ("conversations", "project_id TEXT"), ("projects", "team_id TEXT"),
                           ("conversations", "pinned REAL"), ("conversations", "favorite INTEGER"),
                           ("conversations", "marked REAL"), ("conversations", "kind TEXT")):  # columnas añadidas después
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
                if col == "kind TEXT":   # las conversaciones que ya tenían carpeta de trabajo se crearon en Code
                    self.conn.execute("UPDATE conversations SET kind='code' WHERE workdir IS NOT NULL AND workdir != ''")
            except sqlite3.OperationalError:
                pass
        # Identificador global de cada mensaje (para sincronizar entre equipos)
        for (mid,) in self.conn.execute("SELECT id FROM messages WHERE uid IS NULL").fetchall():
            self.conn.execute("UPDATE messages SET uid=? WHERE id=?", (uuid.uuid4().hex, mid))
        self.conn.commit()
        self.lock = threading.Lock()

    def _q(self, sql, args=()):
        # Todo, también leer las filas, dentro del candado: la conexión es compartida entre hilos y algunas consultas
        # llaman a funciones de Python (norm); leer fuera del candado bloqueaba la app con dos búsquedas a la vez.
        with self.lock:
            cur = self.conn.execute(sql, args)
            rows = cur.fetchall() if cur.description else None
            self.conn.commit()
            return _Result(cur, rows)

    # Conversaciones ---------------------------------------------------------
    def list_conversations(self) -> list[dict]:
        rows = self._q(
            "SELECT id, title, provider, model, updated, project_id, pinned, favorite, kind, workdir FROM conversations ORDER BY updated DESC"
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
            f"SELECT m.id, m.conv_id, m.role, m.content, c.title, c.updated, c.kind FROM messages m "
            f"JOIN conversations c ON c.id = m.conv_id WHERE m.role IN ('user','assistant') AND {where} "
            f"ORDER BY c.updated DESC, m.id LIMIT 400", like).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            o = out.setdefault(r["conv_id"], {"id": r["conv_id"], "title": r["title"], "updated": r["updated"], "kind": r["kind"],
                                              "hits": 0, "message_id": r["id"], "role": r["role"],
                                              "snippet": snippet(r["content"], words)})
            o["hits"] += 1
        twhere = " AND ".join("norm(title) LIKE ?" for _ in words)
        for r in self._q(f"SELECT id, title, updated, kind FROM conversations WHERE {twhere} ORDER BY updated DESC LIMIT 50", like):
            out.setdefault(r["id"], {"id": r["id"], "title": r["title"], "updated": r["updated"], "kind": r["kind"], "hits": 0,
                                     "message_id": None, "role": None, "snippet": ""})
        return sorted(out.values(), key=lambda o: -o["updated"])[:limit]

    def create_conversation(self, title="Nueva conversación", provider=None, model=None, system=None,
                            project_id=None, kind: str | None = None) -> dict:
        cid = uuid.uuid4().hex[:12]
        now = time.time()
        self._q(
            "INSERT INTO conversations (id, title, provider, model, system, created, updated, project_id, kind) VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, title, provider, model, system, now, now, project_id, "code" if kind == "code" else None),
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
        conv["branches"] = self.branch_info(cid, conv["messages"])
        return conv

    # Ramas: al editar o regenerar, el final de la conversación se guarda como alternativa ----------
    def branch_info(self, cid: str, messages: list[dict]) -> dict:
        """{posición: {"n": total, "i": índice de la actual}} para cada punto con alternativas."""
        rows = self._q("SELECT position, born FROM branches WHERE conv_id=?", (cid,)).fetchall()
        out: dict[int, list[float]] = {}
        for r in rows:
            out.setdefault(r["position"], []).append(r["born"])
        info = {}
        for pos, borns in out.items():
            if pos >= len(messages):
                cur = None
            else:
                cur = messages[pos]["created"]
            allb = sorted(borns + ([cur] if cur is not None else []))
            info[str(pos)] = {"n": len(allb), "i": allb.index(cur) if cur is not None else -1}
        return info

    def archive_from(self, cid: str, message_id: int) -> int:
        """Guarda como rama alternativa el mensaje `message_id` y los siguientes (con sus propias ramas) y los quita."""
        pos = self._q("SELECT COUNT(*) FROM messages WHERE conv_id=? AND id<?", (cid, message_id)).fetchone()[0]
        tail = self._q("SELECT uid, role, content, reasoning, meta, created FROM messages WHERE conv_id=? AND id>=? ORDER BY id",
                       (cid, message_id)).fetchall()
        if tail:
            sub = self._q("SELECT position, born, data FROM branches WHERE conv_id=? AND position>?", (cid, pos)).fetchall()
            data = {"messages": [dict(r) for r in tail], "sub": [dict(r) for r in sub]}
            self._q("DELETE FROM branches WHERE conv_id=? AND position>?", (cid, pos))
            self._q("INSERT INTO branches (conv_id, position, born, data) VALUES (?,?,?,?)",
                    (cid, pos, tail[0]["created"], json.dumps(data, ensure_ascii=False)))
        self.delete_messages_from(cid, message_id)
        return pos

    def switch_branch(self, cid: str, position: int, step: int) -> None:
        """Cambia el final de la conversación desde `position` por la rama anterior (-1) o siguiente (+1)."""
        msgs = self._q("SELECT id, created FROM messages WHERE conv_id=? ORDER BY id", (cid,)).fetchall()
        rows = self._q("SELECT id, born FROM branches WHERE conv_id=? AND position=?", (cid, position)).fetchall()
        cur = msgs[position]["created"] if position < len(msgs) else None
        order = sorted([(r["born"], r["id"]) for r in rows] + ([(cur, None)] if cur is not None else []))
        idx = next((i for i, (b, rid) in enumerate(order) if rid is None), -1)
        target = idx + step if idx >= 0 else (len(order) - 1 if step < 0 else 0)
        if not 0 <= target < len(order) or order[target][1] is None:
            return
        row = self._q("SELECT data FROM branches WHERE id=?", (order[target][1],)).fetchone()
        if position < len(msgs):
            self.archive_from(cid, msgs[position]["id"])
        data = json.loads(row["data"])
        self._q("DELETE FROM branches WHERE id=?", (order[target][1],))
        for m in data["messages"]:
            self._q("INSERT INTO messages (conv_id, uid, role, content, reasoning, meta, created) VALUES (?,?,?,?,?,?,?)",
                    (cid, m["uid"] or uuid.uuid4().hex, m["role"], m["content"], m["reasoning"], m["meta"], m["created"]))
        for b in data.get("sub", []):
            self._q("INSERT INTO branches (conv_id, position, born, data) VALUES (?,?,?,?)",
                    (cid, b["position"], b["born"], b["data"]))
        self._q("UPDATE conversations SET summary=NULL, summary_upto=NULL, updated=? WHERE id=?", (time.time(), cid))

    def mark_conversation(self, cid: str, pinned: bool | None = None, favorite: bool | None = None) -> None:
        """Fijar / favorito: no cambia «updated» (la conversación no salta en la lista), pero sí «marked» para sincronizar."""
        sets, args = [], []
        if pinned is not None:
            sets.append("pinned=?")
            args.append(time.time() if pinned else None)
        if favorite is not None:
            sets.append("favorite=?")
            args.append(1 if favorite else 0)
        if sets:
            self._q(f"UPDATE conversations SET {', '.join(sets)}, marked=? WHERE id=?", (*args, time.time(), cid))

    def update_conversation(self, cid: str, **fields) -> None:
        keys = [k for k in ("title", "provider", "model", "system", "workdir", "project_id") if k in fields]
        if not keys:
            return
        sets = ", ".join(f"{k}=?" for k in keys)
        self._q(
            f"UPDATE conversations SET {sets}, updated=? WHERE id=?",
            (*[fields[k] for k in keys], time.time(), cid),
        )

    # Proyectos -------------------------------------------------------------
    def _project(self, row) -> dict:
        p = dict(row)
        p["files"] = json.loads(p.get("files") or "[]")
        return p

    def list_projects(self) -> list[dict]:
        rows = self._q("SELECT p.*, (SELECT COUNT(*) FROM conversations c WHERE c.project_id = p.id) AS conversations, "
                       "(SELECT MAX(c.updated) FROM conversations c WHERE c.project_id = p.id) AS last_used "
                       "FROM projects p").fetchall()
        return sorted((self._project(r) for r in rows), key=lambda p: -(p["last_used"] or p["updated"]))

    def get_project(self, pid: str) -> dict | None:
        row = self._q("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return self._project(row) if row else None

    def create_project(self, name: str, instructions: str = "", files: list | None = None) -> dict:
        pid, now = uuid.uuid4().hex[:12], time.time()
        self._q("INSERT INTO projects (id, name, instructions, files, created, updated) VALUES (?,?,?,?,?,?)",
                (pid, name, instructions, json.dumps(files or [], ensure_ascii=False), now, now))
        return self.get_project(pid)

    def update_project(self, pid: str, **fields) -> dict | None:
        sets, args = [], []
        for k in ("name", "instructions", "files", "team_id"):
            if k in fields:
                sets.append(f"{k}=?")
                args.append(json.dumps(fields[k], ensure_ascii=False) if k == "files" else fields[k])
        if sets:
            self._q(f"UPDATE projects SET {', '.join(sets)}, updated=? WHERE id=?", (*args, time.time(), pid))
        return self.get_project(pid)

    def delete_project(self, pid: str) -> None:
        """Borra el proyecto; sus conversaciones se conservan, sin proyecto."""
        self._q("UPDATE conversations SET project_id=NULL WHERE project_id=?", (pid,))
        self._q("DELETE FROM projects WHERE id=?", (pid,))
        self.tombstone("project", pid)

    def delete_conversation(self, cid: str) -> None:
        self._q("DELETE FROM messages WHERE conv_id=?", (cid,))
        self._q("DELETE FROM branches WHERE conv_id=?", (cid,))
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
