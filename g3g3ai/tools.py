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
import os
import re
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

import httpx

from . import sandbox, web
from .documents import DocumentError
from .files import FileAccessError, Files, is_under

READ_LIMIT_FOR_AI = 30_000
OUTPUT_LIMIT = 20_000
TOOL_RESULT_PREVIEW = 800
APPROVAL_TIMEOUT = 900

# Aprobaciones pendientes: id -> Future[str] ("yes" | "always" | "no").
PENDING: dict[str, asyncio.Future] = {}

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

FILE_TOOLS = {"list_dir", "read_file", "search_files", "grep_files", "glob_files", "git", "update_plan", "table_info", "table_query"}
WRITE_TOOLS = {"write_file", "edit_file", "create_document", "git_commit", "table_export"}
COMMAND_TOOLS = {"run_command", "build_exe"}
WEB_TOOLS = {"web_search", "fetch_url"}
MEMORY_TOOLS = {"memory_save", "memory_delete"}
GAME_TOOLS = {"steam_games", "game_diagnostics"}


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
                           "max_lines": {"type": "integer"},
                           "pages": {"type": "string", "description": "Sólo PDF: páginas a leer, p.ej. '3', '2-5' o '1,4,7-9'"}},
                          ["path"])),
    "search_files": ("Busca archivos o carpetas por nombre (admite comodines * y ?).",
                     _schema({"query": {"type": "string", "description": "Texto o patrón, p.ej. '*.pdf'"},
                              "path": {"type": "string", "description": "Carpeta donde buscar (opcional)"}}, ["query"])),
    "table_info": ("Describe una hoja de cálculo (xlsx/xls/csv): hojas, columnas, nº de filas y ejemplos. Úsalo SIEMPRE "
                   "antes de consultar un Excel grande; no lo leas con read_file.",
                   _schema({"path": {"type": "string"}, "sheet": {"type": "string"},
                            "header_row": {"type": "integer"}}, ["path"])),
    "table_query": ("Consulta un Excel/CSV grande sin leerlo entero: filtra filas, elige columnas, cuenta, quita repetidos y "
                    "CRUZA dos archivos (p.ej. las personas del archivo A que NO están en el archivo B). Devuelve las "
                    "primeras filas y el total; para guardar todo el resultado usa table_export.",
                    _schema({"path": {"type": "string", "description": "Archivo .xlsx/.xls/.csv"},
                            "sheet": {"type": "string", "description": "Hoja (por defecto la primera)"},
                            "header_row": {"type": "integer", "description": "Fila de encabezados (se detecta sola)"},
                            "columns": {"type": "array", "items": {"type": "string"}, "description": "Columnas a devolver"},
                            "where": {"type": "array", "items": {"type": "object", "properties": {
                                "column": {"type": "string"},
                                "op": {"type": "string", "description": "=, !=, contains, not_contains, empty, not_empty, >, <, >=, <="},
                                "value": {"type": "string"}}, "required": ["column", "op"]},
                                "description": "Condiciones (todas deben cumplirse)"},
                            "distinct": {"type": "boolean", "description": "Quitar filas repetidas"},
                            "other_path": {"type": "string", "description": "Segundo archivo para cruzar"},
                            "other_sheet": {"type": "string"}, "other_header_row": {"type": "integer"},
                            "column": {"type": "string", "description": "Columna de ESTE archivo con la que cruzar (p.ej. NOMBRE)"},
                            "other_column": {"type": "string", "description": "Columna del OTRO archivo con la que cruzar"},
                            "mode": {"type": "string", "enum": ["missing", "common"], "description": "missing = los que NO están en el otro archivo; common = los que sí"}}, ["path"])),
    "table_export": ("Igual que table_query pero guarda TODO el resultado en un archivo .xlsx o .csv (save_as), sin que "
                     "tengas que escribir las filas tú. Úsalo para entregar listas completas.",
                     _schema({"path": {"type": "string", "description": "Archivo .xlsx/.xls/.csv"},
                            "sheet": {"type": "string", "description": "Hoja (por defecto la primera)"},
                            "header_row": {"type": "integer", "description": "Fila de encabezados (se detecta sola)"},
                            "columns": {"type": "array", "items": {"type": "string"}, "description": "Columnas a devolver"},
                            "where": {"type": "array", "items": {"type": "object", "properties": {
                                "column": {"type": "string"},
                                "op": {"type": "string", "description": "=, !=, contains, not_contains, empty, not_empty, >, <, >=, <="},
                                "value": {"type": "string"}}, "required": ["column", "op"]},
                                "description": "Condiciones (todas deben cumplirse)"},
                            "distinct": {"type": "boolean", "description": "Quitar filas repetidas"},
                            "other_path": {"type": "string", "description": "Segundo archivo para cruzar"},
                            "other_sheet": {"type": "string"}, "other_header_row": {"type": "integer"},
                            "column": {"type": "string", "description": "Columna de ESTE archivo con la que cruzar (p.ej. NOMBRE)"},
                            "other_column": {"type": "string", "description": "Columna del OTRO archivo con la que cruzar"},
                            "mode": {"type": "string", "enum": ["missing", "common"], "description": "missing = los que NO están en el otro archivo; common = los que sí"},
                              "save_as": {"type": "string", "description": "Archivo de salida, p.ej. sin_descargo.xlsx"}},
                             ["path", "save_as"])),
    "glob_files": ("Encuentra archivos por patrón de ruta, p.ej. '**/*.py' o 'src/**/test_*.js' (los más recientes primero).",
                   _schema({"pattern": {"type": "string"},
                            "path": {"type": "string", "description": "Carpeta base (opcional)"}}, ["pattern"])),
    "git": ("Consulta un repositorio git (sólo lectura). action: status, diff, log, show, branch. "
            "diff admite staged=true y path; log admite max_count; show y diff admiten rev (commit, rama o HEAD~1).",
            _schema({"action": {"type": "string", "enum": ["status", "diff", "log", "show", "branch"]},
                     "repo": {"type": "string", "description": "Carpeta del repositorio (opcional)"},
                     "rev": {"type": "string"}, "path": {"type": "string", "description": "Limita a un archivo"},
                     "staged": {"type": "boolean"}, "max_count": {"type": "integer"}}, ["action"])),
    "git_commit": ("Añade archivos al área de preparación de git y crea un commit (no hace push). "
                   "Sólo en repositorios dentro de las carpetas modificables.",
                   _schema({"path": {"type": "string", "description": "Carpeta del repositorio"},
                            "message": {"type": "string"},
                            "files": {"type": "array", "items": {"type": "string"},
                                      "description": "Archivos a incluir (relativos al repo). Vacío = todos los cambios"}},
                           ["path", "message"])),
    "update_plan": ("Escribe o actualiza tu lista de tareas para trabajos de varios pasos. Cada tarea: "
                    "{content, status: pending|in_progress|done}. Mantén una sola en curso y márcalas al terminarlas.",
                    _schema({"todos": {"type": "array", "items": {"type": "object", "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
                        "required": ["content", "status"]}}}, ["todos"])),
    "grep_files": ("Busca texto DENTRO de los archivos (expresión regular o texto literal) en una carpeta y sus subcarpetas. "
                   "Devuelve líneas `ruta:nº: texto`. Úsalo para localizar dónde se define o se usa algo.",
                   _schema({"pattern": {"type": "string", "description": "Texto o expresión regular"},
                            "path": {"type": "string", "description": "Carpeta o archivo donde buscar (opcional)"},
                            "glob": {"type": "string", "description": "Filtrar por nombre, p.ej. '*.py' (opcional)"}},
                           ["pattern"])),
    "write_file": ("Crea o sobrescribe un archivo de texto completo (sólo en las carpetas modificables).",
                   _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])),
    "create_document": ("Crea un documento Word (.docx), Excel (.xlsx), PowerPoint (.pptx) o PDF (.pdf); el formato sale "
                        "de la extensión de path. Para .docx y .pdf, content es Markdown (títulos #, listas, tablas |, "
                        "**negrita**). Para .xlsx, content es JSON {\"sheets\": [{\"name\": \"Hoja1\", \"rows\": "
                        "[[\"Producto\", \"Total\"], [\"A\", \"=B3*2\"]], \"number_formats\": {\"B\": \"0.00\"}}]} "
                        "(las celdas con = son fórmulas; la primera fila es el encabezado). Para .pptx, content es JSON "
                        "{\"title\": \"...\", \"slides\": [{\"title\": \"...\", \"bullets\": [\"...\"], \"notes\": \"...\"}]}. "
                        "El archivo se ofrece al usuario para descargar.",
                        _schema({"path": {"type": "string", "description": "Ruta del archivo, p.ej. informe.docx"},
                                 "content": {"type": "string", "description": "Markdown o JSON según el formato"}},
                                ["path", "content"])),
    "edit_file": ("Reemplaza un fragmento exacto de texto en un archivo (old_text debe aparecer una sola vez).",
                  _schema({"path": {"type": "string"}, "old_text": {"type": "string"},
                           "new_text": {"type": "string"}}, ["path", "old_text", "new_text"])),
    "run_command": ("Ejecuta un comando de terminal y devuelve su salida. "
                    "Úsalo para compilar, probar, instalar o inspeccionar el sistema.",
                    _schema({"command": {"type": "string"},
                             "cwd": {"type": "string", "description": "Carpeta de trabajo (opcional)"},
                             "timeout": {"type": "integer", "description": "Segundos, por defecto 120"},
                             "unsandboxed": {"type": "boolean", "description":
                                             "true sólo si el comando necesita escribir fuera de las carpetas permitidas "
                                             "(p.ej. flatpak install --user, cambiar ~/.config). Siempre pide permiso."}},
                            ["command"])),
    "build_exe": ("Compila un script de Python a un único ejecutable (.exe en Windows, binario en Linux) con PyInstaller. "
                  "Escribe antes el script con write_file en una carpeta modificable. El ejecutable se ofrece al usuario "
                  "para descargar.",
                  _schema({"script": {"type": "string", "description": "Ruta del .py principal"},
                           "name": {"type": "string", "description": "Nombre del ejecutable (sin extensión)"},
                           "windowed": {"type": "boolean", "description": "true para programas con ventana (sin consola)"},
                           "packages": {"type": "array", "items": {"type": "string"},
                                        "description": "Paquetes de pip que necesita el script (p.ej. requests)"},
                           "icon": {"type": "string", "description": "Ruta de un .ico (opcional)"}},
                          ["script"])),
    "steam_games": ("Lista los juegos de Steam instalados (appid, tamaño, versión de Proton forzada).",
                    _schema({"query": {"type": "string", "description": "Filtro por nombre (opcional)"}})),
    "game_diagnostics": ("Diagnostica un juego de Steam: carpeta, Proton, opciones de lanzamiento, prefijo de Wine, "
                         "registros de Proton/Steam y archivos de configuración y volcados recientes.",
                         _schema({"game": {"type": "string", "description": "Nombre o appid del juego"}}, ["game"])),
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
    "generate_image": ("Genera una imagen a partir de una descripción detallada (en inglés suele dar mejor resultado). "
                       "La imagen se muestra al usuario automáticamente.",
                       _schema({"prompt": {"type": "string", "description": "Descripción detallada de la imagen"},
                                "size": {"type": "string", "description": "Opcional, p.ej. 1024x1024 o 1024x1536"}},
                               ["prompt"])),
    "ask_local_model": ("Delega una subtarea sencilla (resumir, traducir, extraer datos, reformatear) "
                        "en el modelo local gratuito. Devuelve su respuesta.",
                        _schema({"prompt": {"type": "string"}}, ["prompt"])),
}


_NUM_RE = re.compile(r"\d{1,3}(?:[.,\u00a0 ]\d{3})+(?:[.,]\d+)?|\d+[.,]\d+|\d{4,}")


def numbers_in(text: str) -> set[str]:
    """Cifras relevantes de un texto, normalizadas a sus dígitos (150.322,54 y 150,322.54 → 15032254).
    Se ignoran números pequeños, años y fechas, que no son importes."""
    out = set()
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0)
        digits = re.sub(r"\D", "", tok)
        plain4 = re.fullmatch(r"\d{4}", tok)
        if plain4 and 1900 <= int(tok) <= 2100:
            continue
        if len(digits) >= 4:
            out.add(digits)
    return out


class ToolContext:
    def __init__(self, files: Files, cfg, local_chat: Callable[[str], Awaitable[str]] | None = None, *,
                 agent: bool = True, web: bool = False, session_allow: set | None = None,
                 memory=None, source: str | None = None, image_gen=None):
        self.files = files
        self.cfg = cfg
        self.local_chat = local_chat
        self.agent = agent
        self.web = web
        self.memory = memory  # objeto Memory si la IA puede guardar recuerdos
        self.source = source
        self.image_gen = image_gen  # async (prompt, size) -> Path
        self.plan: list[dict] = []
        self.known: set[str] | None = None  # cifras de los archivos adjuntos y resultados de herramientas
        self.generated: list[str] = []
        self.files_out: list[str] = []  # archivos creados para ofrecer al usuario
        # Herramientas que el usuario permitió «siempre» en esta conversación
        self.session_allow = session_allow if session_allow is not None else set()

    # Verificación de cifras -------------------------------------------------------
    def set_sources(self, texts: list[str]) -> None:
        """Textos de partida (mensajes del usuario con sus adjuntos): sus cifras son las «conocidas»."""
        self.known = set()
        for t in texts:
            self.known |= numbers_in(t)

    def note_source(self, text: str) -> None:
        if self.known is not None:
            self.known |= numbers_in(text)

    def unverified_numbers(self, content: str) -> list[str]:
        """Cifras del documento que no aparecen en ninguna fuente. Vacío si no hay fuentes con cifras."""
        if not self.known:
            return []
        seen, out = set(), []
        for m in _NUM_RE.finditer(content or ""):
            tok = m.group(0)
            digits = re.sub(r"\D", "", tok)
            if len(digits) < 4 or digits in self.known or digits in seen:
                continue
            if re.fullmatch(r"\d{4}", tok) and 1900 <= int(tok) <= 2100:
                continue
            seen.add(digits)
            out.append(tok)
        return out[:12]

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
            out += ["list_dir", "read_file", "search_files", "grep_files", "glob_files", "git", "update_plan", "table_info", "table_query"]
            if self.mode("write_file") != "off" and self.files.write_roots:
                out += ["write_file", "edit_file", "create_document", "git_commit", "table_export"]
            if self.mode("run_command") != "off":
                out.append("run_command")
                from .devtools import devenv_python
                if devenv_python(self.cfg):
                    out.append("build_exe")
            if self._steam_present():
                out += ["steam_games", "game_diagnostics"]
            if self.local_chat:
                out.append("ask_local_model")
        elif self.mode("create_document") != "off" and self.files.write_roots:
            # Crear documentos (docx/xlsx/pptx/pdf) no requiere activar el modo Agente (pide permiso igualmente).
            out.append("create_document")
        if self.web:
            out += ["web_search", "fetch_url"]
        if self.memory is not None:
            out += ["memory_save", "memory_delete"]
        if self.image_gen is not None:
            out.append("generate_image")
        return out

    def openai_specs(self) -> list[dict]:
        return [{"type": "function", "function": {"name": n, "description": ALL_SPECS[n][0],
                                                  "parameters": ALL_SPECS[n][1]}} for n in self.names()]

    def anthropic_specs(self) -> list[dict]:
        return [{"name": n, "description": ALL_SPECS[n][0], "input_schema": ALL_SPECS[n][1]} for n in self.names()]

    def _steam_present(self) -> bool:
        if not hasattr(self, "_steam"):
            from .steam import steam_roots
            self._steam = bool(steam_roots(self.cfg))
        return self._steam

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
            if "run_command" in names:
                from .devtools import summary as dev_summary
                parts.append(f"Herramientas de programación instaladas: {dev_summary(self.cfg)}.")
                if "build_exe" in names:
                    parts.append("Para crear un programa ejecutable escribe el script de Python y compílalo con build_exe "
                                 + ("(genera un .exe de Windows)." if sys.platform == "win32" else
                                    "(en este equipo genera un binario de Linux; los .exe de Windows se crean en un PC con Windows)."))
            if "table_query" in names:
                parts.append("Para Excel o CSV grandes NO uses read_file: llama a table_info para ver las columnas y a "
                             "table_query para filtrar, contar o cruzar dos archivos (por ejemplo «los que NO están en el "
                             "otro archivo»); con table_export guardas el resultado completo en un .xlsx sin escribir las "
                             "filas a mano. Si tras table_info no sabes qué columna usar para cruzar, pregunta al usuario.")
            if "ask_local_model" in names:
                parts.append("Para subtareas sencillas y voluminosas (resumir archivos largos, traducir, extraer) "
                             "puedes usar ask_local_model y ahorrar coste.")
            parts.append("Trabaja paso a paso: inspecciona antes de modificar y verifica el resultado. "
                         "No anuncies lo que vas a hacer («ahora leo…»): llama directamente a la herramienta. "
                         "Termina tu respuesta sólo cuando la tarea esté hecha o necesites que el usuario decida algo.")
            from .steam import system_hint as steam_hint
            hint = steam_hint()
            if hint:
                parts.append(hint)
        if "create_document" in names or "table_export" in names:
            parts.append("CIFRAS: al resumir o crear documentos copia los importes, códigos y fechas literalmente del original; "
                         "no los recalcules, redondees ni reescribas de memoria. Si un dato no está en el original, no lo "
                         "inventes: indícalo. Si la herramienta te avisa de cifras sin verificar, corrígelas.")
        if not self.agent and "create_document" in names:
            wr = self.files.write_roots[0]
            parts.append("Puedes crear documentos Word (.docx), Excel (.xlsx), PowerPoint (.pptx) o PDF con create_document "
                         f"cuando el usuario los pida (usa una ruta relativa como informe.docx; se guarda en {wr}). "
                         "No le des scripts para generarlos: créalos tú con la herramienta.")
        if self.memory is not None:
            from .memory import SAVE_GUIDE
            parts.append(SAVE_GUIDE)
        if self.image_gen is not None:
            parts.append("Puedes crear imágenes con generate_image cuando el usuario lo pida.")
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
                p = self.files.resolve(args.get("save_as") if name == "table_export" else args.get("path"), "ai_write")
                if self.files.is_game_path(p) and not any(is_under(p, r) for r in self.files.write_roots):
                    return None, ["modifica archivos de un juego (se guarda una copia de seguridad del original)"], []
            if name == "build_exe":
                script = self.files.resolve(args.get("script"), "ai_write")
                if script.suffix.lower() != ".py" or not script.is_file():
                    return f"Error: {script} no es un script de Python existente.", [], []
                strong = [f"instala paquetes de internet: {', '.join(args['packages'])}"] if args.get("packages") else []
                soft = [] if self.sandboxed else ["compila y ejecuta código sin aislamiento"]
                return None, strong, soft
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
                if self.sandboxed and args.get("unsandboxed"):
                    reasons = reasons + ["se ejecuta FUERA del aislamiento: puede modificar cualquier archivo de tu usuario"]
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
            if name == "steam_games":
                from .steam import games_summary
                return await asyncio.to_thread(games_summary, self.cfg, args.get("query", ""))
            if name == "game_diagnostics":
                from .steam import diagnose
                return await asyncio.to_thread(diagnose, self.cfg, str(args.get("game", "")))
            if name == "generate_image":
                from .images import ImageError
                try:
                    path = await self.image_gen(str(args.get("prompt", "")), args.get("size"))
                except ImageError as e:
                    return f"Error al generar la imagen: {e}"
                self.generated.append(str(path))
                return f"Imagen generada y mostrada al usuario. Guardada en {path}"
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
            if kind == "document" and a.get("pages") and path.suffix.lower() == ".pdf":
                res = {"path": str(path), "content": D.pdf_pages_text(path, a["pages"])}
            elif kind == "document":
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
        if name in ("table_info", "table_query", "table_export"):
            return self._table(name, a)
        if name == "glob_files":
            res = f.glob(a["pattern"], a.get("path"))
            return "\n".join(r["path"] for r in res) or "Sin resultados."
        if name == "git":
            return self._git(a)
        if name == "git_commit":
            return self._git_commit(a)
        if name == "update_plan":
            icons = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
            self.plan = [{"content": str(t.get("content", ""))[:200], "status": t.get("status", "pending")}
                         for t in (a.get("todos") or [])][:30]
            return "Plan actualizado:\n" + "\n".join(f"{icons.get(t['status'], '[ ]')} {t['content']}" for t in self.plan)
        if name == "grep_files":
            res = f.grep(a["pattern"], a.get("path"), a.get("glob"))
            return "\n".join(res) + ("\n[... más resultados omitidos ...]" if len(res) >= 100 else "") if res else "Sin resultados."
        if name == "search_files":
            res = f.search(a["query"], a.get("path"))
            return "\n".join(("[D] " if r["is_dir"] else "") + r["path"] for r in res) or "Sin resultados."
        if name in WRITE_TOOLS:
            self._backup_if_game(f.resolve(a["path"], "ai_write"))
        if name == "write_file":
            res = f.write_text(a["path"], a.get("content", ""), scope="ai_write")
            self.files_out.append(res["path"])
            return f"Guardado {res['path']} ({res['bytes']} bytes)"
        if name == "create_document":
            from . import office
            p = f.resolve(a["path"], "ai_write")
            try:
                office.create(p, a.get("content", ""))
            except (office.OfficeError, ValueError, KeyError, TypeError) as e:
                return f"Error al crear el documento: {e}"
            self.files_out.append(str(p))
            msg = f"Documento creado: {p} ({p.stat().st_size} bytes). El usuario ya puede descargarlo."
            bad = self.unverified_numbers(a.get("content", "") if isinstance(a.get("content"), str)
                                          else json.dumps(a.get("content", ""), ensure_ascii=False))
            if bad:
                msg += ("\n⚠ VERIFICA ESTAS CIFRAS: no aparecen en los archivos adjuntos ni en los resultados de las "
                        f"herramientas: {', '.join(bad)}. Si te has equivocado al copiarlas, corrige el documento y vuelve "
                        "a generarlo con las cifras exactas del original; si son un cálculo tuyo, dilo claramente al usuario.")
            return msg
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
        if name == "build_exe":
            return self._build_exe(a)
        return f"Error: herramienta desconocida {name}"

    def _backup_if_game(self, p: Path) -> None:
        """Antes de tocar un archivo de un juego, guarda una copia del original (sólo la primera vez)."""
        if p.is_file() and self.files.is_game_path(p):
            bak = p.with_name(p.name + ".g3g3ai-original")
            if not bak.exists():
                import shutil
                shutil.copy2(p, bak)

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

    def _table(self, name: str, a: dict) -> str:
        from . import tables as T
        try:
            src = self.files.resolve(a["path"])
            if name == "table_info":
                return T.describe(src, a.get("sheet"), a.get("header_row"))
            kw = dict(sheet=a.get("sheet"), header_row=a.get("header_row"), columns=a.get("columns") or None,
                      where=a.get("where"), distinct=bool(a.get("distinct")), column=a.get("column"),
                      other_column=a.get("other_column"), mode=a.get("mode") or "missing",
                      other_sheet=a.get("other_sheet"), other_header_row=a.get("other_header_row"),
                      other_path=self.files.resolve(a["other_path"]) if a.get("other_path") else None)
            res = T.query(src, **kw)
            if name == "table_query":
                return T.format_result(res)
            dest = self.files.resolve(a["save_as"], "ai_write")
            n = T.export(res, dest)
            self.files_out.append(str(dest))
            return (" · ".join(res["info"]) + f"\nGuardado {dest} con {n} filas. El usuario ya puede descargarlo.")
        except T.TableError as e:
            return f"Error: {e}"
        except (OSError, ValueError, KeyError) as e:
            return f"Error al leer la hoja de cálculo: {e}"

    _REV = re.compile(r"^[\w./~^@{}:-]+$")

    def _run_git(self, cwd: Path, args: list[str]) -> str:
        import shutil
        import subprocess
        exe = shutil.which("git")
        if not exe:
            return "Error: git no está instalado en este equipo."
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C.UTF-8"}
        try:
            r = subprocess.run([exe, "--no-pager", "-c", "core.quotepath=false", *args], cwd=cwd, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        except subprocess.TimeoutExpired:
            return "Error: git tardó demasiado."
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
        if len(out) > OUTPUT_LIMIT:
            out = out[:OUTPUT_LIMIT] + "\n[... salida recortada ...]"
        return out.strip() or ("(sin salida)" if r.returncode == 0 else f"git terminó con código {r.returncode}")

    def _rev(self, rev) -> str | None:
        if not rev:
            return None
        rev = str(rev)
        if rev.startswith("-") or not self._REV.match(rev):
            raise ValueError(f"rev no válido: {rev}")
        return rev

    def _git(self, a: dict) -> str:
        cwd = self.files.resolve(a.get("repo"))
        if not cwd.is_dir():
            return f"Error: {cwd} no es una carpeta."
        act, rev = a.get("action"), self._rev(a.get("rev"))
        path = [str(self.files.resolve(a["path"]))] if a.get("path") else []
        if act == "status":
            return self._run_git(cwd, ["status", "--short", "--branch"])
        if act == "diff":
            return self._run_git(cwd, ["diff", *(["--staged"] if a.get("staged") else []), *([rev] if rev else []), "--", *path])
        if act == "log":
            n = max(1, min(int(a.get("max_count") or 20), 100))
            return self._run_git(cwd, ["log", f"--max-count={n}", "--date=short", "--format=%h %ad %an  %s", *([rev] if rev else []), "--", *path])
        if act == "show":
            return self._run_git(cwd, ["show", "--stat", "--patch", rev or "HEAD", "--", *path])
        if act == "branch":
            return self._run_git(cwd, ["branch", "-vv", "--all"])
        return "Error: action debe ser status, diff, log, show o branch."

    def _git_commit(self, a: dict) -> str:
        cwd = self.files.resolve(a["path"], "ai_write")
        msg = str(a.get("message", "")).strip()
        if not msg:
            return "Error: el mensaje del commit está vacío."
        paths = [str(self.files.resolve(str(p), "ai_write")) for p in (a.get("files") or [])]
        out = self._run_git(cwd, ["add", "--", *paths] if paths else ["add", "-A"])
        if out.startswith("Error"):
            return out
        res = self._run_git(cwd, ["commit", "-m", msg])
        return res

    def _build_exe(self, a: dict) -> str:
        from . import devtools
        script = self.files.resolve(a["script"], "ai_write")
        icon = self.files.resolve(a["icon"]) if a.get("icon") else None
        wrap = None
        if self.sandboxed and not a.get("packages"):
            import shlex
            hidden = self.files.blocked_dirs_and_files()
            py = devtools.devenv_python(self.cfg)
            # El Python de compilación (un entorno virtual) debe verse dentro del aislamiento
            ro = [py.parent.parent] if py else []
            wrap = lambda cmd, cwd, tmp: sandbox.wrap(  # noqa: E731
                shlex.join(cmd), cwd, self.files.write_roots + [self.workdir(), cwd, tmp], hidden, ro)
        try:
            exe, log = devtools.build(self.cfg, script, a.get("name"), bool(a.get("windowed")),
                                      a.get("packages") or [], icon, wrap)
        except RuntimeError as e:
            return f"Error: {e}"
        self.files_out.append(str(exe))
        size = exe.stat().st_size / 1e6
        return f"Ejecutable creado: {exe} ({size:.1f} MB). El usuario ya puede descargarlo.\n\nÚltimas líneas:\n{log[-1500:]}"

    def _run_command(self, a: dict) -> str:
        cwd = self.files.resolve(a["cwd"]) if a.get("cwd") else self.workdir()
        timeout = min(int(a.get("timeout") or 120), 1800)
        kw = dict(cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout,
                  creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        if self.sandboxed and not a.get("unsandboxed"):
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
        tag = " (aislado)" if self.sandboxed and not a.get("unsandboxed") else ""
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
        if name not in ("create_document", "table_export", "write_file", "edit_file"):
            ctx.note_source(result)
    yield {"type": "tool_result", "name": name, "result": result[:TOOL_RESULT_PREVIEW]}
    while ctx.generated:
        yield {"type": "image", "path": ctx.generated.pop(0)}
    while ctx.files_out:
        yield {"type": "file", "path": ctx.files_out.pop(0)}
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
