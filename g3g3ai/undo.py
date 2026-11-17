"""Deshacer los cambios que la IA hace en archivos durante una conversación.

Antes de que la IA modifique un archivo por primera vez en una conversación se guarda una copia de su
estado original (o se anota que no existía). «Deshacer» devuelve cada archivo a ese estado: restaura la
copia o borra el archivo que la IA creó. No cubre lo que hagan los comandos (run_command).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import DATA_DIR

MAX_BACKUP = 25_000_000  # bytes por archivo; más grande no se copia (se avisa)


def _dir(cid: str) -> Path:
    return DATA_DIR / "undo" / "".join(c for c in cid if c.isalnum() or c in "-_")


class UndoJournal:
    def __init__(self, cid: str):
        self.dir = _dir(cid)
        self.path = self.dir / "journal.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        tmp.replace(self.path)

    def record(self, target: Path) -> None:
        """Guarda el estado original de `target` la primera vez que se toca en esta conversación."""
        data = self._load()
        key = str(target)
        if key in data:
            return
        entry: dict = {"existed": target.exists(), "backup": None, "skipped": None}
        if target.is_file():
            if target.stat().st_size > MAX_BACKUP:
                entry["skipped"] = "demasiado grande para guardar una copia"
            else:
                self.dir.mkdir(parents=True, exist_ok=True)
                backup = self.dir / f"{len(data):04d}-{target.name}"
                shutil.copy2(target, backup)
                entry["backup"] = backup.name
        data[key] = entry
        self._save(data)

    def changes(self) -> list[dict]:
        out = []
        for path, e in self._load().items():
            out.append({"path": path, "created": not e["existed"], "restorable": bool(e["backup"]) or not e["existed"],
                        "note": e.get("skipped")})
        return out

    def undo_all(self) -> dict:
        """Devuelve cada archivo a su estado original. Retorna {restored, deleted, failed}."""
        data = self._load()
        res = {"restored": [], "deleted": [], "failed": []}
        for path, e in reversed(list(data.items())):
            p = Path(path)
            try:
                if not e["existed"]:
                    if p.is_file():
                        p.unlink()
                    res["deleted"].append(path)
                elif e["backup"] and (self.dir / e["backup"]).is_file():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self.dir / e["backup"], p)
                    res["restored"].append(path)
                else:
                    res["failed"].append(f"{path} ({e.get('skipped') or 'sin copia'})")
            except OSError as ex:
                res["failed"].append(f"{path} ({ex})")
        if not res["failed"]:
            self.clear()
        else:  # conserva sólo lo que no se pudo deshacer
            keep = {p: data[p] for p in data if any(f.startswith(p) for f in res["failed"])}
            self._save(keep)
        return res

    def clear(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
