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
    """Diario de cambios de una conversación. Además del diario global (estado original de cada archivo), guarda un
    «checkpoint» por turno (`cp` = id del mensaje del usuario que lo provocó): con él se puede volver al estado
    de los archivos justo antes de cualquier mensaje."""

    def __init__(self, cid: str, cp: int | str | None = None, _dir_override: Path | None = None):
        self.cid, self.cp = cid, cp
        self.dir = _dir_override or _dir(cid)
        self.path = self.dir / "journal.json"

    # --- checkpoints
    def _cp_journal(self, cp) -> "UndoJournal":
        return UndoJournal(self.cid, None, self.dir / "cp" / str(cp))

    def checkpoints(self) -> list[dict]:
        """[{id, files}] de los turnos que modificaron archivos, del más antiguo al más reciente."""
        base = self.dir / "cp"
        out = []
        if base.is_dir():
            for d in base.iterdir():
                if d.name.isdigit():
                    files = self._cp_journal(d.name).changes()
                    if files:
                        out.append({"id": int(d.name), "files": files})
        return sorted(out, key=lambda c: c["id"])

    def restore_to(self, cp: int) -> dict:
        """Deja los archivos como estaban justo antes del mensaje `cp`: deshace ese turno y los posteriores."""
        res = {"restored": [], "deleted": [], "failed": []}
        for c in sorted(self.checkpoints(), key=lambda c: c["id"], reverse=True):
            if c["id"] < int(cp):
                break
            part = self._cp_journal(c["id"]).undo_all()  # undo_all limpia el checkpoint si todo fue bien
            for k in res:
                res[k] += part[k]
        # el diario global ya no describe el estado actual con fidelidad: se descarta lo restaurado
        main = self._load()
        for p in res["restored"] + res["deleted"]:
            main.pop(p, None)
        self._save(main)
        return res

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
        """Guarda el estado original de `target` la primera vez que se toca en esta conversación (y en este turno)."""
        if self.cp is not None:
            self._cp_journal(self.cp).record(target)
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

    def diff(self, path: str) -> str:
        """Diff unificado entre el estado original guardado y el actual de un archivo."""
        import difflib
        e = self._load().get(path)
        if e is None:
            return ""

        def text(p: Path) -> list[str]:
            try:
                return p.read_text("utf-8", errors="replace").splitlines(keepends=True)
            except OSError:
                return []
        before = text(self.dir / e["backup"]) if e.get("backup") else []
        after = text(Path(path))
        name = Path(path).name
        out = "".join(difflib.unified_diff(before, after, "/dev/null" if not e["existed"] else f"a/{name}",
                                           f"b/{name}", n=3))
        return out[:60_000] or "(sin diferencias)"

    def _restore(self, path: str, e: dict, res: dict) -> None:
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

    def undo_one(self, path: str) -> dict:
        """Deshace un solo archivo y lo quita del registro (la copia se conserva hasta limpiar la conversación)."""
        data = self._load()
        res = {"restored": [], "deleted": [], "failed": []}
        if path not in data:
            res["failed"].append(f"{path} (no consta en esta conversación)")
            return res
        self._restore(path, data[path], res)
        if not res["failed"]:
            del data[path]
            self._save(data)
        return res

    def undo_all(self) -> dict:
        """Devuelve cada archivo a su estado original. Retorna {restored, deleted, failed}."""
        data = self._load()
        res = {"restored": [], "deleted": [], "failed": []}
        for path, e in reversed(list(data.items())):
            self._restore(path, e, res)
        if not res["failed"]:
            self.clear()
        else:  # conserva sólo lo que no se pudo deshacer
            keep = {p: data[p] for p in data if any(f.startswith(p) for f in res["failed"])}
            self._save(keep)
        return res

    def clear(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
