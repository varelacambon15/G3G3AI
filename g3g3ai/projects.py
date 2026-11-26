"""Proyectos: conversaciones agrupadas que comparten instrucciones y documentos de referencia.

El contexto del proyecto se añade al mensaje del sistema de cada conversación que pertenece a él.
Los documentos se incluyen enteros mientras quepan en el presupuesto del modelo; los que no caben se
listan con su ruta para que la IA los lea con sus herramientas si los necesita.
"""
from __future__ import annotations

from pathlib import Path

from . import documents as D

_cache: dict[tuple[str, float], str] = {}


def doc_text(files, path: str) -> str:
    """Texto de un documento (PDF, Word, Excel…) o archivo de texto, respetando las carpetas permitidas."""
    p = files.resolve(path)
    key = (str(p), p.stat().st_mtime)
    if key not in _cache:
        if D.kind_of(p) == "document":
            text = D.extract_text(p)
        elif D.kind_of(p) == "image":
            text = ""
        else:
            text = files.read_text(str(p), 400_000)["content"]
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = text
    return _cache[key]


def context(project: dict, files, budget_chars: int) -> str:
    out = [f"# Proyecto: {project['name']}",
           "Esta conversación pertenece a este proyecto. Ten en cuenta sus instrucciones y documentos en todas tus respuestas."]
    if project.get("instructions", "").strip():
        out += ["", "## Instrucciones del proyecto", project["instructions"].strip()]
    left = max(0, budget_chars - sum(len(x) for x in out))
    included, skipped = [], []
    for path in project.get("files") or []:
        try:
            text = doc_text(files, path)
        except Exception as e:  # noqa: BLE001  (un documento ilegible no impide usar el proyecto)
            skipped.append(f"- `{path}` (no se pudo leer: {e})")
            continue
        if not text.strip():
            skipped.append(f"- `{path}` (sin texto: imagen o PDF escaneado)")
        elif len(text) + 200 <= left:
            included.append(f"### {Path(path).name}\nRuta: `{path}`\n```\n{text}\n```")
            left -= len(text) + 200
        else:
            skipped.append(f"- `{path}` ({len(text):,} caracteres; no cabe entero: léelo con tus herramientas si lo necesitas)")
    if included:
        out += ["", "## Documentos del proyecto", *included]
    if skipped:
        out += ["", "## Otros documentos del proyecto", *skipped]
    return "\n".join(out)
