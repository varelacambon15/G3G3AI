"""Herramientas de la IA: archivos, edición, comandos, web y delegación al modelo local.

Seguridad:
- Lectura: sólo carpetas visibles, nunca rutas protegidas.
- Escritura/edición: sólo «carpetas que la IA puede modificar» + permiso (off/ask/auto).
- Comandos: permiso (off/ask/auto) + evaluación (bloqueados / siempre preguntar) + aislamiento bubblewrap
  en Linux. Sin aislamiento (Windows/macOS) se pregunta siempre, salvo «permitir siempre en esta conversación».
- Web: búsqueda y lectura de páginas públicas (nunca la red local).
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

import httpx

from . import sandbox, web
from .documents import DocumentError
from .files import FileAccessError, Files

READ_LIMIT_FOR_AI = 30_000
OUTPUT_LIMIT = 20_000
TOOL_RESULT_PREVIEW = 800
APPROVAL_TIMEOUT = 900

# Aprobaciones pendientes: id -> Future[str] ("yes" | "always" | "no").
PENDING: dict[str, asyncio.Future] = {}

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

FILE_TOOLS = {"list_dir", "read_file", "search_files"}
WRITE_TOOLS = {"write_file", "edit_file"}
COMMAND_TOOLS = {"run_command"}
WEB_TOOLS = {"web_search", "fetch_url"}
MEMORY_TOOLS = {"memory_save", "memory_delete"}


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
    "write_file": ("Crea o sobrescribe un archivo de texto completo (sólo en las carpetas modificables).",
                   _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])),
    "edit_file": ("Reemplaza un fragmento exacto de texto en un archivo (old_text debe aparecer una sola vez).",
                  _schema({"path": {"type": "string"}, "old_text": {"type": "string"},
                           "new_text": {"type": "string"}}, ["path", "old_text", "new_text"])),
    "run_command": ("Ejecuta un comando de terminal y devuelve su salida. "
                    "Úsalo para compilar, probar, instalar o inspeccionar el sistema.",
                    _schema({"command": {"type": "string"},
                             "cwd": {"type": "string", "description": "Carpeta de trabajo (opcional)"},
                             "timeout": {"type": "integer", "description": "Segundos, por defecto 120"}}, ["command"])),
    "web_search": ("Busca en internet. Devuelve títulos, enlaces y resúmenes. Úsalo para información actual "
                   "o que no conozcas; después lee las páginas relevantes con fetch_url.",
                   _schema({"query": {"type": "string"},
                            "max_results": {"type": "integer", "description": "Por defecto 6"}}, ["query"])),
    "fetch_url": ("Abre una página web pública y devuelve su texto.",
                  _schema({"url": {"type": "string"}}, ["url"])),
    "memory_save": ("Guarda (o actualiza) un recuerdo breve y duradero sobre el usuario para próximas conversaciones.",
                    _schema({"content": {"type": "string", "description": "Una frase clara, en tercera persona"},
                             "replaces_id": {"type": "integer", "description": "Id del recuerdo que sustituye (opcional)"}},
                            ["content"])),
    "memory_delete": ("Borra un recuerdo por su id (cuando quede obsoleto o el usuario pida olvidarlo).",
                      _schema({"id": {"type": "integer"}}, ["id"])),
    "ask_local_model": ("Delega una subtarea sencilla (resumir, traducir, extraer datos, reformatear) "
                        "en el modelo local gratuito. Devuelve su respuesta.",
                        _schema({"prompt": {"type": "string"}}, ["prompt"])),
}


class ToolContext:
    def __init__(self, files: Files, cfg, local_chat: Callable[[str], Awaitable[str]] | None = None, *,
                 agent: bool = True, web: bool = False, session_allow: set | None = None,
                 memory=None, source: str | None = None):
        self.files = files
        self.cfg = cfg
        self.local_chat = local_chat
        self.agent = agent
        self.web = web
        self.memory = memory  # objeto Memory si la IA puede guardar recuerdos
        self.source = source
        # Herramientas que el usuario permitió «siempre» en esta conversación
        self.session_allow = session_allow if session_allow is not None else set()

    # Permisos ------------------------------------------------------------------
    def mode(self, name: str) -> str:
        if name in WRITE_TOOLS:
            return self.cfg["ai_write"] or "off"
        if name in COMMAND_TOOLS:
            return self.cfg["ai_commands"] or "off"
        return "auto"

    def names(self) -> list[str]:
        out = []
        if self.agent:
            out += ["list_dir", "read_file", "search_files"]
            if self.mode("write_file") != "off" and self.files.write_roots:
                out += ["write_file", "edit_file"]
            if self.mode("run_command") != "off":
                out.append("run_command")
            if self.local_chat:
                out.append("ask_local_model")
        if self.web:
            out += ["web_search", "fetch_url"]
        if self.memory is not None:
            out += ["memory_save", "memory_delete"]
        return out

    def openai_specs(self) -> list[dict]:
        return [{"type": "function", "function": {"name": n, "description": ALL_SPECS[n][0],
                                                  "parameters": ALL_SPECS[n][1]}} for n in self.names()]

    def anthropic_specs(self) -> list[dict]:
        return [{"name": n, "description": ALL_SPECS[n][0], "input_schema": ALL_SPECS[n][1]} for n in self.names()]

    @property
    def sandboxed(self) -> bool:
        return sandbox.available(self.cfg)

    def system_hint(self) -> str:
        names = self.names()
        parts = []
        if self.agent:
            roots = ", ".join(str(r) for r in self.files.roots)
            wroots = ", ".join(str(r) for r in self.files.write_roots) or "ninguna"
            osname = f"{platform.system()} {platform.machine()}"
            parts.append(f"Tienes herramientas para trabajar en el dispositivo del usuario ({osname}). "
                         f"Puedes leer en: {roots}. Sólo puedes modificar archivos en: {wroots}.")
            if "run_command" in names:
                shell = "cmd.exe" if sys.platform == "win32" else "bash"
                parts.append(f"Los comandos se ejecutan con {shell} en {self.workdir()} salvo que indiques cwd"
                             + (" dentro de un entorno aislado donde el resto del sistema es de sólo lectura."
                                if self.sandboxed else "."))
            if "ask_local_model" in names:
                parts.append("Para subtareas sencillas y voluminosas (resumir archivos largos, traducir, extraer) "
                             "puedes usar ask_local_model y ahorrar coste.")
            parts.append("Trabaja paso a paso: inspecciona antes de modificar y verifica el resultado.")
        if self.memory is not None:
            from .memory import SAVE_GUIDE
            parts.append(SAVE_GUIDE)
        if self.web:
            parts.append("Puedes buscar en internet con web_search y leer páginas con fetch_url. "
                         "Cuando uses información de la web, cita las fuentes con enlaces.")
        return " ".join(parts)

    def workdir(self) -> Path:
        wroots = self.files.write_roots
        p = Path(self.cfg["agent_workdir"] or (wroots[0] if wroots else Path.home())).expanduser().resolve()
        if wroots and not self.files.can_ai_write(p):
            p = wroots[0]
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Comprobaciones previas a la aprobación ---------------------------------------------
    def precheck(self, name: str, args: dict) -> tuple[str | None, list[str], list[str]]:
        """Devuelve (error, avisos_fuertes, avisos_suaves). Los fuertes obligan a preguntar siempre."""
        try:
            if name in WRITE_TOOLS:
                self.files.resolve(args.get("path"), "ai_write")
            if name == "run_command":
                cmd = str(args.get("command", ""))
                if not cmd.strip():
                    return "Error: comando vacío.", [], []
                level, reasons = sandbox.assess(cmd)
                if level == "block":
                    return (f"Bloqueado por seguridad: el comando intenta {reasons[0]}. "
                            "No se puede ejecutar desde G3G3AI."), [], []
                if args.get("cwd"):
                    self.files.resolve(args["cwd"])
                soft = [] if self.sandboxed else [
                    "sin aislamiento: el comando puede modificar cualquier archivo de tu usuario"]
                return None, reasons, soft
        except FileAccessError as e:
            return f"Error: {e}", [], []
        return None, [], []

    # Ejecución -----------------------------------------------------------------
    async def run(self, name: str, args: dict) -> str:
        try:
            if name == "ask_local_model":
                if not self.local_chat:
                    return "Error: el modelo local no está disponible."
                return await self.local_chat(args.get("prompt", ""))
            if name == "web_search":
                q = str(args.get("query", "")).strip()
                res = await web.search(self.cfg, q, min(int(args.get("max_results") or 6), 10))
                return web.format_results(q, res)
            if name == "fetch_url":
                return await web.fetch(str(args.get("url", "")).strip())
            if name in MEMORY_TOOLS:
                return self._memory(name, args)
            return await asyncio.to_thread(self._run_sync, name, args)
        except (FileAccessError, DocumentError, web.WebError) as e:
            return f"Error: {e}"
        except httpx.HTTPError as e:
            return f"Error de red: {e}"
        except (KeyError, TypeError, ValueError) as e:
            return f"Error: argumento no válido ({e})"
        except OSError as e:
            return f"Error: {e}"

    def _run_sync(self, name: str, a: dict) -> str:
        f = self.files
        if name == "list_dir":
            res = f.list_dir(a.get("path"))
            lines = [f"Carpeta: {res['path']}" + ("  [modificable]" if res["ai_write"] else "  [sólo lectura]")]
            for e in res["entries"][:400]:
                lines.append(("[D] " if e["is_dir"] else "    ") + e["name"] + ("" if e["is_dir"] else f"  ({e['size']} B)"))
            return "\n".join(lines)
        if name == "read_file":
            from . import documents as D
            path = f.resolve(a["path"])
            kind = D.kind_of(path)
            if kind == "image":
                return (f"{path} es una imagen. Pide al usuario que la adjunte al chat (📎) para verla "
                        "con un modelo con visión.")
            if kind == "document":
                text = D.extract_text(path) or "(documento sin texto: puede ser un PDF escaneado; adjúntalo al chat)"
                res = {"path": str(path), "content": text}
            else:
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
            res = f.write_text(a["path"], a.get("content", ""), scope="ai_write")
            return f"Guardado {res['path']} ({res['bytes']} bytes)"
        if name == "edit_file":
            p = f.resolve(a["path"], "ai_write")
            text = p.read_text("utf-8")
            n = text.count(a["old_text"])
            if n == 0:
                return "Error: no se encontró old_text en el archivo."
            if n > 1:
                return f"Error: old_text aparece {n} veces; añade más contexto para que sea único."
            p.write_text(text.replace(a["old_text"], a["new_text"], 1), "utf-8")
            return f"Editado {p}"
        if name == "run_command":
            return self._run_command(a)
        return f"Error: herramienta desconocida {name}"

    def _memory(self, name: str, a: dict) -> str:
        from .memory import MemoryRejected
        if self.memory is None:
            return "Error: la memoria está desactivada."
        try:
            if name == "memory_save":
                if a.get("replaces_id"):
                    m = self.memory.update(int(a["replaces_id"]), a.get("content", ""))
                    return f"Recuerdo {m['id']} actualizado."
                m = self.memory.add(a.get("content", ""), self.source)
                return f"Recuerdo {m['id']} guardado."
            if self.memory.delete(int(a.get("id"))):
                return f"Recuerdo {a.get('id')} borrado."
            return f"No existe el recuerdo {a.get('id')}."
        except MemoryRejected as e:
            return f"No guardado: {e}"

    def _run_command(self, a: dict) -> str:
        cwd = self.files.resolve(a["cwd"]) if a.get("cwd") else self.workdir()
        timeout = min(int(a.get("timeout") or 120), 1800)
        kw = dict(cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout,
                  creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        if self.sandboxed:
            home = Path.home()
            caches = [home / ".cache", home / ".npm"]  # escribibles pero temporales
            hidden = self.files.blocked_dirs_and_files()
            argv = sandbox.wrap(a["command"], cwd, self.files.write_roots + [self.workdir()],
                                hidden + [c for c in caches if c.is_dir()])
            run = lambda: subprocess.run(argv, **kw)  # noqa: E731
        else:
            run = lambda: subprocess.run(a["command"], shell=True, **kw)  # noqa: E731
        try:
            r = run()
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(e.stdout, str) else ""
            return f"Tiempo agotado ({timeout}s).\n{(out or '')[-OUTPUT_LIMIT:]}"
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        if len(out) > OUTPUT_LIMIT:
            out = "[... salida recortada ...]\n" + out[-OUTPUT_LIMIT:]
        tag = " (aislado)" if self.sandboxed else ""
        return f"Código de salida{tag}: {r.returncode}\n{out}"


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
    else:
        error, strong, soft = ctx.precheck(name, args)
        if error:
            result = error
        else:
            mode = ctx.mode(name)
            must_ask = mode == "ask" or bool(strong) or (mode == "auto" and bool(soft))
            if must_ask and not strong and name in ctx.session_allow:
                must_ask = False
            if must_ask:
                aid = uuid.uuid4().hex[:10]
                fut = asyncio.get_running_loop().create_future()
                PENDING[aid] = fut
                yield {"type": "approval", "id": aid, "name": name, "args": args,
                       "warnings": strong + soft, "dangerous": bool(strong), "can_always": not strong,
                       "sandboxed": ctx.sandboxed if name == "run_command" else None}
                try:
                    answer = await asyncio.wait_for(fut, APPROVAL_TIMEOUT)
                except asyncio.TimeoutError:
                    answer = "no"
                finally:
                    PENDING.pop(aid, None)
                if answer == "always" and not strong:
                    ctx.session_allow.add(name)
                yield {"type": "approval_result", "id": aid, "approved": answer in ("yes", "always")}
                if answer not in ("yes", "always"):
                    result = "El usuario ha denegado esta acción. Pregunta o propón otra alternativa."
    if result is None:
        result = await ctx.run(name, args)
    yield {"type": "tool_result", "name": name, "result": result[:TOOL_RESULT_PREVIEW]}
    sink.append(result)


def resolve_approval(aid: str, answer) -> bool:
    fut = PENDING.get(aid)
    if not fut or fut.done():
        return False
    if answer is True:
        answer = "yes"
    elif answer is False or answer not in ("yes", "always", "no"):
        answer = "no"
    fut.set_result(answer)
    return True
