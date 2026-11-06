"""Herramientas que la IA puede usar para acceder a archivos del Konkr."""
from __future__ import annotations

import json

from .files import FileAccessError, Files

READ_LIMIT_FOR_AI = 30_000


def tool_specs(allow_write: bool) -> list[dict]:
    """Especificación neutra: {name, description, parameters (JSON Schema)}."""
    specs = [
        {
            "name": "list_dir",
            "description": "Lista archivos y carpetas de una ruta del dispositivo. Sin ruta = carpeta personal.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Ruta absoluta o relativa a la carpeta personal"}},
            },
        },
        {
            "name": "read_file",
            "description": "Lee el contenido de un archivo de texto del dispositivo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "search_files",
            "description": "Busca archivos o carpetas por nombre (admite comodines * y ?).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto o patrón, p.ej. '*.pdf' o 'notas'"},
                    "path": {"type": "string", "description": "Carpeta donde buscar (opcional)"},
                },
                "required": ["query"],
            },
        },
    ]
    if allow_write:
        specs.append({
            "name": "write_file",
            "description": "Crea o sobrescribe un archivo de texto en el dispositivo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        })
    return specs


def openai_tools(allow_write: bool) -> list[dict]:
    return [{"type": "function", "function": s} for s in tool_specs(allow_write)]


def anthropic_tools(allow_write: bool) -> list[dict]:
    return [{"name": s["name"], "description": s["description"], "input_schema": s["parameters"]}
            for s in tool_specs(allow_write)]


def run_tool(files: Files, name: str, args: dict | str, allow_write: bool) -> str:
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except json.JSONDecodeError:
            return "Error: argumentos JSON no válidos"
    try:
        if name == "list_dir":
            res = files.list_dir(args.get("path"))
            lines = [f"Carpeta: {res['path']}"]
            for e in res["entries"][:300]:
                lines.append(f"{'[D]' if e['is_dir'] else '   '} {e['name']}" + ("" if e["is_dir"] else f"  ({e['size']} B)"))
            return "\n".join(lines)
        if name == "read_file":
            res = files.read_text(args["path"], READ_LIMIT_FOR_AI)
            note = "\n\n[... archivo truncado ...]" if res["truncated"] else ""
            return f"Archivo: {res['path']}\n\n{res['content']}{note}"
        if name == "search_files":
            res = files.search(args["query"], args.get("path"))
            return "\n".join(("[D] " if r["is_dir"] else "") + r["path"] for r in res) or "Sin resultados."
        if name == "write_file":
            if not allow_write:
                return "Error: la escritura de archivos está desactivada en Ajustes."
            res = files.write_text(args["path"], args.get("content", ""))
            return f"Guardado {res['path']} ({res['bytes']} bytes)"
        return f"Error: herramienta desconocida {name}"
    except FileAccessError as e:
        return f"Error: {e}"
    except (KeyError, OSError) as e:
        return f"Error: {e!r}"
