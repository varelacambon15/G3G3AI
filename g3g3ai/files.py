"""Acceso seguro a archivos dentro de las carpetas permitidas."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

TEXT_LIMIT = 200_000  # caracteres máximos leídos de un archivo de texto


class FileAccessError(Exception):
    pass


class Files:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def roots(self) -> list[Path]:
        return [Path(r).expanduser().resolve() for r in self.cfg["file_roots"] or []]

    def resolve(self, path: str | None) -> Path:
        """Convierte una ruta del usuario en ruta absoluta, comprobando que está permitida."""
        roots = self.roots
        if not roots:
            raise FileAccessError("No hay carpetas permitidas configuradas.")
        if not path:
            return roots[0]
        p = Path(os.path.expanduser(path))
        if not p.is_absolute():
            p = roots[0] / p
        p = p.resolve()
        for root in roots:
            if p == root or p.is_relative_to(root):
                return p
        raise FileAccessError(f"Acceso denegado fuera de las carpetas permitidas: {p}")

    def list_dir(self, path: str | None, show_hidden: bool = False) -> dict:
        p = self.resolve(path)
        if not p.is_dir():
            raise FileAccessError(f"No es una carpeta: {p}")
        entries = []
        try:
            it = list(os.scandir(p))
        except PermissionError as e:
            raise FileAccessError(str(e)) from e
        for e in it:
            if not show_hidden and e.name.startswith("."):
                continue
            try:
                st = e.stat()
                is_dir = e.is_dir()
            except OSError:
                continue
            entries.append({
                "name": e.name,
                "path": str(Path(e.path)),
                "is_dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": st.st_mtime,
            })
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        parent = str(p.parent) if any(p != r and p.is_relative_to(r) for r in self.roots) else None
        return {"path": str(p), "parent": parent, "entries": entries}

    def read_text(self, path: str, limit: int = TEXT_LIMIT) -> dict:
        p = self.resolve(path)
        if not p.is_file():
            raise FileAccessError(f"No es un archivo: {p}")
        with open(p, "rb") as f:
            raw = f.read(limit * 4 + 1)
        if b"\x00" in raw[:8192]:
            raise FileAccessError(f"Parece un archivo binario: {p.name}")
        text = raw.decode("utf-8", errors="replace")
        truncated = len(text) > limit or p.stat().st_size > len(raw)
        return {"path": str(p), "name": p.name, "content": text[:limit], "truncated": truncated}

    def write_text(self, path: str, content: str) -> dict:
        p = self.resolve(path)
        if p.is_dir():
            raise FileAccessError(f"Es una carpeta: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
        return {"path": str(p), "bytes": len(content.encode())}

    def search(self, query: str, path: str | None = None, max_results: int = 100) -> list[dict]:
        base = self.resolve(path)
        pattern = query if any(c in query for c in "*?[") else f"*{query}*"
        out = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
            for name in dirnames + filenames:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    full = Path(dirpath) / name
                    out.append({"path": str(full), "is_dir": full.is_dir()})
                    if len(out) >= max_results:
                        return out
        return out

    def safe_child(self, directory: str | None, filename: str) -> Path:
        name = Path(filename).name  # evita ../ en el nombre subido
        if not name or name in (".", ".."):
            raise FileAccessError("Nombre de archivo no válido")
        d = self.resolve(directory)
        if not d.is_dir():
            raise FileAccessError(f"No es una carpeta: {d}")
        return self.resolve(str(d / name))
