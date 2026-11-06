"""Herramientas del modo agente: archivos, edición, comandos y delegación al modelo local.

Las acciones que modifican algo (escribir, editar, ejecutar) respetan los permisos de Ajustes:
"off" (desactivado), "ask" (pide confirmación al usuario en la interfaz) o "auto".
"""
from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from .files import FileAccessError, Files

READ_LIMIT_FOR_AI = 30_000
OUTPUT_LIMIT = 20_000
TOOL_RESULT_PREVIEW = 800
APPROVAL_TIMEOUT = 900

# Aprobaciones pendientes: id -> Future[bool]. La interfaz las resuelve con /api/chat/approve.
PENDING: dict[str, asyncio.Future] = {}

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WRITE_TOOLS = {"write_file", "edit_file"}
COMMAND_TOOLS = {"run_command"}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    s = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    return s


ALL_SPECS = {
    "list_dir": ("Lista archivos y carpetas de una ruta. Sin ruta = carpeta personal.",
                 _schema({"path": {"type": "string", "description": "Ruta absoluta o relativa a la carpeta personal"}})),
    "read_file": ("Lee un archivo de texto. Usa start_line/max_lines para archivos grandes.",
                  _schema({"path": {"type": "string"}, "start_line": {"type": "integer"},
                           "max_lines": {"type": "integer"}}, ["path"])),
    "search_files": ("Busca archivos o carpetas por nombre (admite comodines * y ?).",
                     _schema({"query": {"type": "string", "description": "Texto o patrón, p.ej. '*.pdf'"},
                              "path": {"type": "string", "description": "Carpeta donde buscar (opcional)"}}, ["query"])),
    "write_file": ("Crea o sobrescribe un archivo de texto completo.",
                   _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])),
    "edit_file": ("Reemplaza un fragmento exacto de texto en un archivo (old_text debe aparecer una sola vez).",
                  _schema({"path": {"type": "string"}, "old_text": {"type": "string"},
                           "new_text": {"type": "string"}}, ["path", "old_text", "new_text"])),
    "run_command": ("Ejecuta un comando de terminal y devuelve su salida. "
                    "Úsalo para compilar, probar, instalar o inspeccionar el sistema.",
                    _schema({"command": {"type": "string"},
                             "cwd": {"type": "string", "description": "Carpeta de trabajo (opcional)"},
                             "timeout": {"type": "integer", "description": "Segundos, por defecto 120"}}, ["command"])),
    "ask_local_model": ("Delega una subtarea sencilla (resumir, traducir, extraer datos, reformatear) "
                        "en el modelo local gratuito. Devuelve su respuesta.",
                        _schema({"prompt": {"type": "string"}}, ["prompt"])),
}


class ToolContext:
    def __init__(self, files: Files, cfg, local_chat: Callable[[str], Awaitable[str]] | None = None):
        self.files = files
        self.cfg = cfg
        self.local_chat = local_chat  # sólo si el modelo local está disponible y no es el que responde

    # Permisos ------------------------------------------------------------------
    def mode(self, name: str) -> str:
        if name in WRITE_TOOLS:
            return self.cfg["ai_write"] or "off"
        if name in COMMAND_TOOLS:
            return self.cfg["ai_commands"] or "off"
        return "auto"

    def names(self) -> list[str]:
        out = ["list_dir", "read_file", "search_files"]
        if self.mode("write_file") != "off":
            out += ["write_file", "edit_file"]
        if self.mode("run_command") != "off":
            out.append("run_command")
        if self.local_chat:
            out.append("ask_local_model")
        return out

    def openai_specs(self) -> list[dict]:
        return [{"type": "function", "function": {"name": n, "description": ALL_SPECS[n][0],
                                                  "parameters": ALL_SPECS[n][1]}} for n in self.names()]

    def anthropic_specs(self) -> list[dict]:
        return [{"name": n, "description": ALL_SPECS[n][0], "input_schema": ALL_SPECS[n][1]} for n in self.names()]

    def system_hint(self) -> str:
        roots = ", ".join(str(r) for r in self.files.roots)
        osname = f"{platform.system()} {platform.machine()}"
        parts = [f"Tienes herramientas para trabajar en el dispositivo del usuario ({osname}). "
                 f"Carpetas accesibles: {roots}."]
        if "run_command" in self.names():
            shell = "cmd.exe" if sys.platform == "win32" else "bash"
            parts.append(f"Los comandos se ejecutan con {shell} en {self.workdir()} salvo que indiques cwd.")
        if "ask_local_model" in self.names():
            parts.append("Para subtareas sencillas y voluminosas (resumir archivos largos, traducir, extraer) "
                         "puedes usar ask_local_model y ahorrar coste.")
        parts.append("Trabaja paso a paso: inspecciona antes de modificar y verifica el resultado.")
        return " ".join(parts)

    def workdir(self) -> Path:
        p = Path(self.cfg["agent_workdir"] or Path.home()).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Ejecución -----------------------------------------------------------------
    async def run(self, name: str, args: dict) -> str:
        try:
            if name == "ask_local_model":
                if not self.local_chat:
                    return "Error: el modelo local no está disponible."
                return await self.local_chat(args.get("prompt", ""))
            return await asyncio.to_thread(self._run_sync, name, args)
        except FileAccessError as e:
            return f"Error: {e}"
        except (KeyError, TypeError) as e:
            return f"Error: falta el argumento {e}"
        except OSError as e:
            return f"Error: {e}"

    def _run_sync(self, name: str, a: dict) -> str:
        f = self.files
        if name == "list_dir":
            res = f.list_dir(a.get("path"))
            lines = [f"Carpeta: {res['path']}"]
            for e in res["entries"][:400]:
                lines.append(("[D] " if e["is_dir"] else "    ") + e["name"] + ("" if e["is_dir"] else f"  ({e['size']} B)"))
            return "\n".join(lines)
        if name == "read_file":
            res = f.read_text(a["path"], 2_000_000)
            lines = res["content"].splitlines()
            start = max(int(a.get("start_line") or 1), 1)
            maxl = int(a.get("max_lines") or 0)
            chunk = lines[start - 1:start - 1 + maxl] if maxl else lines[start - 1:]
            text = "\n".join(f"{i}: {l}" for i, l in enumerate(chunk, start))
            note = ""
            if len(text) > READ_LIMIT_FOR_AI:
                text = text[:READ_LIMIT_FOR_AI]
                note = "\n[... truncado: usa start_line/max_lines para leer el resto ...]"
            return f"Archivo: {res['path']} ({len(lines)} líneas)\n{text}{note}"
        if name == "search_files":
            res = f.search(a["query"], a.get("path"))
            return "\n".join(("[D] " if r["is_dir"] else "") + r["path"] for r in res) or "Sin resultados."
        if name == "write_file":
            res = f.write_text(a["path"], a.get("content", ""))
            return f"Guardado {res['path']} ({res['bytes']} bytes)"
        if name == "edit_file":
            p = f.resolve(a["path"])
            text = p.read_text("utf-8")
            n = text.count(a["old_text"])
            if n == 0:
                return "Error: no se encontró old_text en el archivo."
            if n > 1:
                return f"Error: old_text aparece {n} veces; añade más contexto para que sea único."
            p.write_text(text.replace(a["old_text"], a["new_text"], 1), "utf-8")
            return f"Editado {p}"
        if name == "run_command":
            cwd = f.resolve(a["cwd"]) if a.get("cwd") else self.workdir()
            timeout = min(int(a.get("timeout") or 120), 1800)
            try:
                r = subprocess.run(a["command"], shell=True, cwd=cwd, capture_output=True, text=True,
                                   errors="replace", timeout=timeout, creationflags=NO_WINDOW,
                                   stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired as e:
                out = (e.stdout or "") if isinstance(e.stdout, str) else ""
                return f"Tiempo agotado ({timeout}s).\n{out[-OUTPUT_LIMIT:]}"
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            if len(out) > OUTPUT_LIMIT:
                out = "[... salida recortada ...]\n" + out[-OUTPUT_LIMIT:]
            return f"Código de salida: {r.returncode}\n{out}"
        return f"Error: herramienta desconocida {name}"


def parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


async def tool_events(ctx: ToolContext, name: str, raw_args, sink: list[str]) -> AsyncIterator[dict]:
    """Ejecuta una herramienta emitiendo eventos para la interfaz; deja el resultado en `sink`."""
    args = parse_args(raw_args)
    yield {"type": "tool_call", "name": name,
           "args": raw_args if isinstance(raw_args, str) else json.dumps(raw_args, ensure_ascii=False)}
    result = None
    if name not in ctx.names():
        result = f"Error: la herramienta {name} no está disponible o está desactivada."
    elif ctx.mode(name) == "ask":
        aid = uuid.uuid4().hex[:10]
        fut = asyncio.get_running_loop().create_future()
        PENDING[aid] = fut
        yield {"type": "approval", "id": aid, "name": name, "args": args}
        try:
            ok = await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
        except asyncio.TimeoutError:
            ok = False
        finally:
            PENDING.pop(aid, None)
        yield {"type": "approval_result", "id": aid, "approved": ok}
        if not ok:
            result = "El usuario ha denegado esta acción. Pregunta o propón otra alternativa."
    if result is None:
        result = await ctx.run(name, args)
    yield {"type": "tool_result", "name": name, "result": result[:TOOL_RESULT_PREVIEW]}
    sink.append(result)


def resolve_approval(aid: str, approved: bool) -> bool:
    fut = PENDING.get(aid)
    if not fut or fut.done():
        return False
    fut.set_result(bool(approved))
    return True
