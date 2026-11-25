"""G3G3AI como servidor MCP (transporte HTTP «streamable»): Claude Code y otros clientes MCP pueden delegarle trabajo.

    claude mcp add --transport http g3g3ai http://127.0.0.1:8800/mcp

Herramientas:
- ask: pregunta o encarga algo a G3G3AI con el modelo que elijas (local o de API). Queda como conversación en la app.
- list_models: modelos disponibles (local cargado y proveedores activos).

Las tareas con herramientas se ejecutan SIN SUPERVISIÓN (nadie puede aprobar acciones desde Claude): todo lo que pediría
permiso se deniega. Por defecto solo lectura; mode="edit" permite editar dentro de las carpetas modificables.
"""
from __future__ import annotations

import json

PROTOCOL = "2025-06-18"
TOOLS = [
    {"name": "ask",
     "description": ("Pregunta o encarga una tarea a G3G3AI, el cliente de IA local del usuario. Úsalo para consultas que "
                     "conviene resolver con un modelo local (privado, gratis) o con otro proveedor (OpenCode Go, DeepSeek, "
                     "Gemini…), o para tareas sobre los archivos y el correo del usuario en su equipo. Devuelve la respuesta "
                     "y un conversation_id para continuar la conversación."),
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "La pregunta o tarea, completa y autosuficiente"},
         "model": {"type": "string", "description": "«local» o «proveedor::modelo» (ver list_models). Vacío = el predeterminado"},
         "use_tools": {"type": "boolean", "description": "Dejarle usar herramientas (archivos, comandos, correo, web). Por defecto no"},
         "mode": {"type": "string", "enum": ["read", "edit"], "description": "Con herramientas: read = solo lectura (por defecto), edit = puede editar en las carpetas permitidas"},
         "web": {"type": "boolean", "description": "Permitir búsqueda web"},
         "workdir": {"type": "string", "description": "Carpeta de trabajo (opcional)"},
         "conversation_id": {"type": "string", "description": "Para continuar una conversación anterior"}},
         "required": ["prompt"]}},
    {"name": "list_models",
     "description": "Lista los modelos que G3G3AI puede usar ahora: el modelo local cargado y los proveedores de API activos.",
     "inputSchema": {"type": "object", "properties": {
         "provider": {"type": "string", "description": "Si se indica, lista los modelos de ese proveedor"}}}},
]


def result(rid, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def error(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


async def handle(msg: dict, call_tool) -> dict | None:
    """Procesa un mensaje JSON-RPC. `call_tool(name, args) -> (texto, es_error)`. None = notificación (sin respuesta)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return error(None, -32600, "Petición JSON-RPC no válida")
    method, rid = msg.get("method"), msg.get("id")
    if rid is None:  # notificación (p. ej. notifications/initialized)
        return None
    if method == "initialize":
        from . import __version__
        asked = (msg.get("params") or {}).get("protocolVersion")
        return result(rid, {"protocolVersion": asked or PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                            "serverInfo": {"name": "g3g3ai", "version": __version__},
                            "instructions": "G3G3AI: cliente de IA local del usuario. Usa «ask» para delegarle consultas."})
    if method == "ping":
        return result(rid, {})
    if method == "tools/list":
        return result(rid, {"tools": TOOLS})
    if method == "tools/call":
        p = msg.get("params") or {}
        name, args = p.get("name"), p.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            return error(rid, -32602, f"Herramienta desconocida: {name}")
        try:
            text, is_err = await call_tool(name, args)
        except Exception as e:  # noqa: BLE001
            text, is_err = f"Error interno de G3G3AI: {e}", True
        return result(rid, text_result(text, is_err))
    return error(rid, -32601, f"Método no soportado: {method}")


def parse_model(model: str | None) -> tuple[str | None, str | None]:
    m = (model or "").strip()
    if not m:
        return None, None
    if m == "local":
        return "local", "local"
    if "::" in m:
        pid, mod = m.split("::", 1)
        return pid, mod
    return None, m


def dumps(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
