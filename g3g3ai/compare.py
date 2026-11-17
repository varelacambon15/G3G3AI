"""Comparar dos carpetas: qué falta en cada lado, qué difiere y qué se ha movido o renombrado.

Solo lectura. Respeta las rutas protegidas (nunca entra en ellas). Los archivos con el mismo nombre se comparan
primero por tamaño y después por contenido (SHA-1), así que «distinto» significa distinto de verdad, no solo de fecha.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import time
from pathlib import Path

DEFAULT_IGNORE = [".git", "node_modules", "__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini", "*.tmp", "~$*"]
MAX_FILES = 200_000          # tope de archivos por lado (evita recorrer un disco entero por error)
MAX_HASH_BYTES = 2_000_000_000


def _sha1(p: Path) -> str | None:
    h = hashlib.sha1()
    try:
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _ignored(rel_parts: tuple[str, ...], patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(part, pat) for part in rel_parts for pat in patterns)


def scan(root: Path, files, patterns: list[str], case_insensitive: bool) -> tuple[dict[str, dict], list[str]]:
    """{clave: {rel, size, mtime, path}} y avisos. La clave es la ruta relativa (en minúsculas si no distingue mayúsculas)."""
    out: dict[str, dict] = {}
    notes: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        keep = []
        for d in dirnames:
            full = base / d
            rel = full.relative_to(root).parts
            if _ignored(rel, patterns) or files.is_blocked(full) or full.is_symlink():
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            full = base / fn
            rel = full.relative_to(root)
            if _ignored(rel.parts, patterns) or files.is_blocked(full) or full.is_symlink():
                continue
            try:
                st = full.stat()
            except OSError:
                continue
            key = rel.as_posix().lower() if case_insensitive else rel.as_posix()
            out[key] = {"rel": rel.as_posix(), "size": st.st_size, "mtime": st.st_mtime, "path": full}
            if len(out) > MAX_FILES:
                notes.append(f"Se paró en {MAX_FILES} archivos: elige una carpeta más concreta.")
                return out, notes
    return out, notes


def compare(files, a: Path, b: Path, ignore: list[str] | None = None, content: bool = True,
            case_insensitive: bool | None = None, limit: int = 60) -> dict:
    ci = (os.name == "nt") if case_insensitive is None else case_insensitive
    patterns = DEFAULT_IGNORE + [p for p in (ignore or []) if p]
    sa, na = scan(a, files, patterns, ci)
    sb, nb = scan(b, files, patterns, ci)
    only_a = sorted(k for k in sa if k not in sb)
    only_b = sorted(k for k in sb if k not in sa)
    same, different = 0, []
    for k in sorted(set(sa) & set(sb)):
        x, y = sa[k], sb[k]
        if x["size"] != y["size"]:
            different.append((k, "tamaño"))
            continue
        if content and x["size"] and x["size"] <= MAX_HASH_BYTES:
            if _sha1(x["path"]) != _sha1(y["path"]):
                different.append((k, "contenido"))
                continue
        elif not content and abs(x["mtime"] - y["mtime"]) > 2:
            different.append((k, "fecha"))
            continue
        same += 1
    # ¿Los faltantes son en realidad movidos o renombrados? (mismo tamaño y mismo contenido en el otro lado)
    moved: list[tuple[str, str]] = []
    if content and only_a and only_b:
        by_size: dict[int, list[str]] = {}
        for k in only_b:
            by_size.setdefault(sb[k]["size"], []).append(k)
        hashes_b: dict[str, str] = {}
        taken: set[str] = set()
        for k in list(only_a):
            cands = [c for c in by_size.get(sa[k]["size"], []) if c not in taken]
            if not cands or sa[k]["size"] == 0:
                continue
            ha = _sha1(sa[k]["path"])
            for c in cands:
                hb = hashes_b.get(c) or hashes_b.setdefault(c, _sha1(sb[c]["path"]) or "")
                if ha and ha == hb:
                    moved.append((k, c))
                    taken.add(c)
                    break
        moved_a = {m[0] for m in moved}
        only_a = [k for k in only_a if k not in moved_a]
        only_b = [k for k in only_b if k not in taken]
    return {"a": str(a), "b": str(b), "same": same, "only_a": [sa[k] for k in only_a], "only_b": [sb[k] for k in only_b],
            "different": [(sa[k], sb[k], why) for k, why in different], "moved": [(sa[x], sb[y]) for x, y in moved],
            "total_a": len(sa), "total_b": len(sb), "notes": na + nb, "case_insensitive": ci, "content": content,
            "limit": limit}


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def format_report(r: dict) -> str:
    lim = r["limit"]
    lines = [f"A = {r['a']}  ({r['total_a']} archivos)", f"B = {r['b']}  ({r['total_b']} archivos)",
             f"Iguales: {r['same']} · Solo en A: {len(r['only_a'])} · Solo en B: {len(r['only_b'])} · "
             f"Distintos: {len(r['different'])} · Movidos/renombrados: {len(r['moved'])}"]
    if r["case_insensitive"]:
        lines.append("(No se distinguen mayúsculas en los nombres.)")
    if not r["content"]:
        lines.append("(Comparación rápida por tamaño y fecha: no se ha leído el contenido.)")

    def block(title: str, items: list[str]) -> None:
        if not items:
            return
        lines.append(f"\n{title} ({len(items)}):")
        lines.extend("  " + t for t in items[:lim])
        if len(items) > lim:
            lines.append(f"  … y {len(items) - lim} más")
    block("SOLO EN A (faltan en B)", [f"{x['rel']}  ({_size(x['size'])})" for x in r["only_a"]])
    block("SOLO EN B (faltan en A)", [f"{x['rel']}  ({_size(x['size'])})" for x in r["only_b"]])
    block("DISTINTOS (mismo nombre, contenido diferente)",
          [f"{x['rel']}  — {why}: A {_size(x['size'])} {_when(x['mtime'])} · B {_size(y['size'])} {_when(y['mtime'])}"
           for x, y, why in r["different"]])
    block("MOVIDOS O RENOMBRADOS (mismo contenido)", [f"{x['rel']}  →  {y['rel']}" for x, y in r["moved"]])
    lines.extend("\n" + n for n in r["notes"])
    if not (r["only_a"] or r["only_b"] or r["different"] or r["moved"]):
        lines.append("\nLas dos carpetas son idénticas.")
    return "\n".join(lines)
