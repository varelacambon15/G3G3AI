"""Ayudantes que ESCRIBEN: trabajan en una copia aislada del proyecto y devuelven un parche.

El ayudante nunca toca los archivos reales. Al terminar se compara su copia con el original y se guarda una
propuesta (diff + contenido nuevo) que el agente principal puede aplicar con `apply_patch` (pide permiso al usuario
mostrando el diff). Si el archivo real cambió mientras tanto, ese archivo no se pisa y se avisa del conflicto.
Varios ayudantes pueden trabajar a la vez porque cada uno tiene su copia.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from .files import Files

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".next", ".cache",
             ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
MAX_COPY_BYTES = 150_000_000
MAX_FILE_BYTES = 2_000_000
MAX_DIFF_CHARS = 60_000


class SubagentError(Exception):
    pass


class ScopedFiles(Files):
    """Files restringido a una carpeta (la copia del ayudante): lee y escribe sólo ahí."""

    def __init__(self, cfg, root: Path):
        super().__init__(cfg)
        self._root = root

    @property
    def roots(self) -> list[Path]:
        return [self._root]

    @property
    def write_roots(self) -> list[Path]:
        return [self._root]

    @property
    def game_roots(self) -> list[Path]:
        return []


def _sha(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.is_file() and not p.is_symlink():
                yield p


def make_copy(src: Path) -> tuple[Path, dict[str, str]]:
    """Copia el proyecto a una carpeta temporal. Devuelve (copia, {ruta relativa: sha1 del original})."""
    total = 0
    manifest: dict[str, str] = {}
    files = list(_walk(src))
    for p in files:
        total += p.stat().st_size
        if total > MAX_COPY_BYTES:
            raise SubagentError(f"El proyecto es demasiado grande para copiarlo ({MAX_COPY_BYTES // 1_000_000} MB máx.). "
                                "Abre una subcarpeta más pequeña como proyecto.")
    # resolve(): en Windows mkdtemp devuelve nombres cortos (RUNNER~1) y las comprobaciones de carpeta usan rutas largas
    dst = Path(tempfile.mkdtemp(prefix="g3g3ai-helper-")).resolve()
    for p in files:
        rel = p.relative_to(src)
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, t)
        manifest[rel.as_posix()] = _sha(p)
    return dst, manifest


def _text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return None
        return p.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def collect_patch(src: Path, copy: Path, manifest: dict[str, str]) -> dict:
    """Compara la copia con el original. {changes: {rel: {base, new}}, diff, skipped}."""
    changes: dict[str, dict] = {}
    skipped: list[str] = []
    seen = set()
    for p in _walk(copy):
        rel = p.relative_to(copy).as_posix()
        seen.add(rel)
        base = manifest.get(rel)
        if base is not None and _sha(p) == base:
            continue
        new = _text(p)
        if new is None:
            skipped.append(rel)
            continue
        changes[rel] = {"base": base, "new": new}
    for rel, base in manifest.items():
        if rel not in seen:
            changes[rel] = {"base": base, "new": None}  # borrado
    parts = []
    for rel, c in sorted(changes.items()):
        old = _text(src / rel) if c["base"] is not None else ""
        new = c["new"] or ""
        d = "".join(difflib.unified_diff((old or "").splitlines(keepends=True), new.splitlines(keepends=True),
                                          f"a/{rel}" if c["base"] is not None else "/dev/null",
                                          f"b/{rel}" if c["new"] is not None else "/dev/null", n=2))
        parts.append(d or f"(sin cambios de texto en {rel})")
    return {"changes": changes, "diff": "".join(parts)[:MAX_DIFF_CHARS], "skipped": skipped}


def new_patch_id() -> str:
    return uuid.uuid4().hex[:6]


def conflicts(src: Path, patch: dict) -> list[str]:
    """Archivos reales que cambiaron desde que se hizo la copia (no se deben pisar)."""
    bad = []
    for rel, c in patch["changes"].items():
        p = src / rel
        if c["base"] is None:
            if p.exists():
                bad.append(rel)       # el ayudante creó un archivo que ahora ya existe
        elif not p.is_file() or _sha(p) != c["base"]:
            bad.append(rel)
    return bad
