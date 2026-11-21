"""Acceso seguro a archivos.

Tres listas en Ajustes:
  file_roots     carpetas visibles (interfaz e IA pueden leer; tú puedes subir archivos)
  write_roots    carpetas que la IA puede modificar (y únicas escribibles para sus comandos aislados)
  blocked_paths  rutas protegidas: nadie las ve desde G3G3AI. Una entrada sin barra es un patrón de
                 nombre de archivo (p.ej. ".env", "*.pem").
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

TEXT_LIMIT = 200_000  # caracteres máximos leídos de un archivo de texto


class FileAccessError(Exception):
    pass


def _norm(p: Path) -> str:
    return os.path.normcase(str(p))


def is_under(p: Path, base: Path) -> bool:
    a, b = _norm(p), _norm(base)
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def _expand(entries) -> list[Path]:
    out = []
    for r in entries or []:
        try:
            out.append(Path(os.path.expandvars(os.path.expanduser(str(r)))).resolve())
        except (OSError, RuntimeError):
            continue
    return out


class Files:
    def __init__(self, cfg):
        self.cfg = cfg

    # Listas ---------------------------------------------------------------------
    @property
    def roots(self) -> list[Path]:
        return _expand(self.cfg["file_roots"])

    @property
    def write_roots(self) -> list[Path]:
        return _expand(self.cfg["write_roots"])

    @property
    def game_roots(self) -> list[Path]:
        """Carpetas de juegos de Steam (steamapps/common y compatdata de cada biblioteca), si está activado."""
        from .steam import game_write_roots
        try:
            return [p.resolve() for p in game_write_roots(self.cfg) if p.is_dir()]
        except OSError:
            return []

    def is_game_path(self, p: Path) -> bool:
        return any(is_under(p, r) for r in self.game_roots)

    def _blocked(self) -> tuple[list[Path], list[str]]:
        paths, patterns = [], []
        for b in self.cfg["blocked_paths"] or []:
            b = str(b).strip()
            if not b:
                continue
            if "/" in b or "\\" in b or b.startswith("~"):
                paths += _expand([b])
            else:
                patterns.append(b.lower())
        return paths, patterns

    def blocked_dirs_and_files(self) -> list[Path]:
        """Rutas protegidas existentes (para ocultarlas dentro del aislamiento de comandos)."""
        return [p for p in self._blocked()[0] if p.exists()]

    def is_blocked(self, p: Path) -> bool:
        paths, patterns = self._blocked()
        if any(is_under(p, b) for b in paths):
            return True
        name = p.name.lower()
        return any(fnmatch.fnmatch(name, pat) for pat in patterns)

    def can_ai_write(self, p: Path) -> bool:
        return any(is_under(p, r) for r in self.write_roots + self.game_roots) and not self.is_blocked(p)

    # Resolución -------------------------------------------------------------------
    def resolve(self, path: str | None, scope: str = "read") -> Path:
        """scope: "read" (carpetas visibles), "ai_write" (carpetas modificables por la IA)."""
        roots = (self.write_roots + self.game_roots) if scope == "ai_write" else (self.roots + self.game_roots)
        if not roots:
            raise FileAccessError("No hay carpetas configuradas para esta operación.")
        if not path:
            return roots[0]
        p = Path(os.path.expandvars(os.path.expanduser(str(path))))
        if not p.is_absolute():
            p = roots[0] / p
        p = p.resolve()
        if self.is_blocked(p):
            raise FileAccessError(f"Ruta protegida: {p}")
        if not any(is_under(p, r) for r in roots):
            if scope == "ai_write":
                allowed = ", ".join(str(r) for r in roots)
                raise FileAccessError(f"La IA sólo puede modificar archivos en: {allowed}. "
                                      f"Puedes añadir carpetas en Ajustes → Carpetas que la IA puede modificar.")
            raise FileAccessError(f"Acceso denegado fuera de las carpetas permitidas: {p}")
        return p

    # Operaciones ------------------------------------------------------------------
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
            full = Path(e.path)
            if self.is_blocked(full):
                continue
            try:
                st = e.stat()
                is_dir = e.is_dir()
            except OSError:
                continue
            entries.append({
                "name": e.name,
                "path": str(full),
                "is_dir": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mtime": st.st_mtime,
                "ai_write": self.can_ai_write(full),
            })
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        parent = str(p.parent) if any(p != r and is_under(p, r) for r in self.roots) else None
        return {"path": str(p), "parent": parent, "entries": entries, "ai_write": self.can_ai_write(p)}

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

    def write_text(self, path: str, content: str, scope: str = "read") -> dict:
        p = self.resolve(path, scope)
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
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")
                           and not self.is_blocked(Path(dirpath) / d)]
            for name in dirnames + filenames:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    full = Path(dirpath) / name
                    if self.is_blocked(full):
                        continue
                    out.append({"path": str(full), "is_dir": full.is_dir()})
                    if len(out) >= max_results:
                        return out
        return out

    def grep(self, pattern: str, path: str | None = None, glob: str = "", ignore_case: bool = False,
             max_results: int = 100, context: int = 0) -> dict:
        """Busca un texto o una expresión regular DENTRO de los archivos de texto de una carpeta."""
        import re
        import time
        base = self.resolve(path)
        note = ""
        try:
            rx = re.compile(pattern, re.I if ignore_case else 0)
        except re.error:
            rx = re.compile(re.escape(pattern), re.I if ignore_case else 0)
            note = "(el patrón no era una expresión regular válida: se buscó como texto literal)"
        globs = [g.strip().lower() for g in glob.split(",") if g.strip()]
        skip_dirs = {"node_modules", "__pycache__", "venv", ".venv", "dist", "build", "target", "site-packages"}
        results, scanned, files_with, truncated = [], 0, set(), False
        deadline = time.time() + 20
        files = [base] if base.is_file() else []
        if base.is_dir():
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip_dirs
                               and not self.is_blocked(Path(dirpath) / d)]
                files += [Path(dirpath) / n for n in sorted(filenames)]
        for fp in files:
            if globs and not any(fnmatch.fnmatch(fp.name.lower(), g) for g in globs):
                continue
            try:
                fp = fp.resolve()
            except (OSError, RuntimeError):
                continue
            if fp.name.startswith(".") and not base.is_file() or self.is_blocked(fp):
                continue
            if scanned >= 20000 or time.time() > deadline:
                truncated = True
                break
            try:
                if fp.stat().st_size > 2_000_000:
                    continue
                with open(fp, "rb") as fh:
                    head = fh.read(4096)
                    if b"\x00" in head:
                        continue
                    data = head + fh.read()
            except OSError:
                continue
            scanned += 1
            lines = data.decode("utf-8", errors="replace").split("\n")
            for i, line in enumerate(lines):
                if rx.search(line):
                    files_with.add(str(fp))
                    block = [(j + 1, lines[j]) for j in range(max(0, i - context), min(len(lines), i + context + 1))]
                    results.append({"path": str(fp), "line": i + 1, "text": line, "block": block})
                    if len(results) >= max_results:
                        truncated = True
                        break
            if len(results) >= max_results:
                break
        return {"results": results, "files": len(files_with), "scanned": scanned, "truncated": truncated, "note": note}

    def safe_child(self, directory: str | None, filename: str) -> Path:
        name = Path(filename).name  # evita ../ en el nombre subido
        if not name or name in (".", ".."):
            raise FileAccessError("Nombre de archivo no válido")
        d = self.resolve(directory)
        if not d.is_dir():
            raise FileAccessError(f"No es una carpeta: {d}")
        return self.resolve(str(d / name))
