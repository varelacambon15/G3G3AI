"""Memoria entre conversaciones: notas breves y duraderas sobre el usuario.

La IA las guarda con la herramienta memory_save (se ve en el chat) y el usuario las gestiona en
Ajustes → Memoria. Se inyectan como contexto al principio de cada conversación.
"""
from __future__ import annotations

import re
import time

MAX_ITEM = 500          # caracteres por recuerdo
MAX_PROMPT = 3500       # caracteres de memoria en el contexto
SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|xox[bp]-[A-Za-z0-9-]{10,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY|(contraseña|password|passwd|pin|token|api[_ -]?key)\s*[:=]\s*\S+)",
    re.I,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
"""


class MemoryRejected(Exception):
    pass


class Memory:
    def __init__(self, db):
        self.db = db
        with db.lock:
            db.conn.executescript(SCHEMA)
            db.conn.commit()

    def _check(self, content: str) -> str:
        content = " ".join(str(content or "").split())
        if not content:
            raise MemoryRejected("El recuerdo está vacío.")
        if len(content) > MAX_ITEM:
            raise MemoryRejected(f"Demasiado largo (máx. {MAX_ITEM} caracteres): resume la idea.")
        if SECRET.search(content):
            raise MemoryRejected("Parece una contraseña o clave: por seguridad no se guarda en memoria.")
        return content

    def list(self) -> list[dict]:
        rows = self.db._q("SELECT id, content, source, created, updated FROM memories ORDER BY updated DESC").fetchall()
        return [dict(r) for r in rows]

    def add(self, content: str, source: str | None = None) -> dict:
        content = self._check(content)
        for m in self.list():  # evita duplicados exactos
            if m["content"].lower() == content.lower():
                return m
        now = time.time()
        cur = self.db._q("INSERT INTO memories (content, source, created, updated) VALUES (?,?,?,?)",
                         (content, source, now, now))
        return {"id": cur.lastrowid, "content": content}

    def update(self, mid: int, content: str) -> dict:
        content = self._check(content)
        cur = self.db._q("UPDATE memories SET content=?, updated=? WHERE id=?", (content, time.time(), int(mid)))
        if not cur.rowcount:
            raise MemoryRejected(f"No existe el recuerdo {mid}.")
        return {"id": int(mid), "content": content}

    def delete(self, mid: int) -> bool:
        return bool(self.db._q("DELETE FROM memories WHERE id=?", (int(mid),)).rowcount)

    def clear(self) -> None:
        self.db._q("DELETE FROM memories")

    def prompt(self) -> str:
        items, total = [], 0
        for m in self.list():
            line = f"[{m['id']}] {m['content']}"
            if total + len(line) > MAX_PROMPT:
                break
            items.append(line)
            total += len(line)
        if not items:
            return ""
        return ("Memoria (cosas que sabes del usuario de conversaciones anteriores; úsalas con naturalidad "
                "y sólo cuando sean relevantes):\n" + "\n".join(items))


SAVE_GUIDE = (
    "Puedes recordar cosas entre conversaciones con memory_save. Guarda sólo información duradera y útil: "
    "preferencias, datos personales que el usuario comparta para que los recuerdes, sus proyectos, equipos y "
    "forma de trabajar, o lo que te pida recordar expresamente. No guardes contraseñas, claves ni datos "
    "sensibles de terceros, ni detalles de un solo uso. Si un recuerdo queda obsoleto, actualízalo "
    "(replaces_id) o bórralo con memory_delete. Cuando el usuario diga «olvida…», bórralo."
)
