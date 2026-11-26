"""La IA puede consultar y cambiar los ajustes de G3G3AI cuando el usuario se lo pide.

- Solo los ajustes de esta lista; nunca contraseñas ni claves API (esas se ponen en Ajustes a mano).
- Leer es libre. Cambiar siempre pide confirmación mostrando «antes → después»; los ajustes que tocan la seguridad
  (permisos, carpetas, correo, servidores MCP…) piden confirmación sin opción de «permitir siempre».
"""
from __future__ import annotations

import json

# clave: (descripción para la IA y el usuario, ¿afecta a la seguridad?)
SETTINGS: dict[str, tuple[str, bool]] = {
    "default_system_prompt": ("Instrucciones del sistema por defecto (texto)", False),
    "temperature": ("Temperatura de las respuestas (0 = precisa, 1 = creativa)", False),
    "max_tokens": ("Máximo de tokens por respuesta", False),
    "memory_enabled": ("Usar la memoria entre conversaciones (sí/no)", False),
    "memory_auto": ("La IA guarda recuerdos por su cuenta (sí/no)", False),
    "memory_api": ("Enviar la memoria también a modelos por API (sí/no)", False),
    "context_budget": ("Contexto máximo para APIs, en tokens", False),
    "router_mode": ("Modo Auto: smart | local_first | api_first", False),
    "web_provider": ("Buscador web: duckduckgo | brave | tavily", False),
    "agent_max_steps": ("Máximo de pasos con herramientas por respuesta", False),
    "agent_profile": ("Exigencia del agente: auto | small | standard | full", False),
    "agent_temperature": ("Temperatura de los modelos locales con herramientas", False),
    "local_thinking": ("Dejar «pensar» a los modelos locales (sí/no)", False),
    "llama_ctx": ("Contexto del modelo local en tokens (0 = automático)", False),
    "llama_threads": ("Hilos del procesador para el modelo local (0 = automático)", False),
    "llama_gpu_layers": ("Capas del modelo local en la gráfica", False),
    "autoload_last_model": ("Cargar el último modelo local al arrancar (sí/no)", False),
    "image_size": ("Tamaño de las imágenes generadas, p. ej. 1024x1024", False),
    "monthly_budget_usd": ("Aviso de gasto mensual en dólares (0 = sin aviso)", False),
    "model_prices": ("Precios por modelo: líneas «modelo = entrada, salida»", False),
    # seguridad: siempre con confirmación fuerte
    "ai_write": ("La IA puede modificar archivos: off | ask | auto", True),
    "ai_commands": ("La IA puede ejecutar comandos: off | ask | auto", True),
    "commands_trusted": ("Confiar en mis carpetas: ediciones y comandos de desarrollo sin preguntar (sí/no)", True),
    "command_allow": ("Comandos permitidos sin preguntar (lista)", True),
    "write_roots": ("Carpetas que la IA puede modificar (lista)", True),
    "file_roots": ("Carpetas que la IA y la interfaz pueden ver (lista)", True),
    "blocked_paths": ("Rutas protegidas que nadie puede ver (lista)", True),
    "command_sandbox": ("Aislamiento de comandos en Linux: auto | off", True),
    "mail_enabled": ("La IA puede buscar en el correo (sí/no)", True),
    "mail_paths": ("Rutas extra de correo (lista)", True),
    "voice_engine": ("Dictado por voz: auto | local | cloud | browser", False),
    "voice_language": ("Idioma del dictado: auto o código (es, en…)", False),
    "mcp_servers": ("Servidores MCP: líneas «nombre = comando args»", True),
}
CHOICES = {
    "router_mode": {"smart", "local_first", "api_first"}, "web_provider": {"duckduckgo", "brave", "tavily"},
    "agent_profile": {"auto", "small", "standard", "full"}, "ai_write": {"off", "ask", "auto"},
    "ai_commands": {"off", "ask", "auto"}, "command_sandbox": {"auto", "off"},
    "voice_engine": {"auto", "local", "cloud", "browser"},
}
TRUE = {"true", "1", "si", "sí", "yes", "on", "activado", "activar"}
FALSE = {"false", "0", "no", "off", "desactivado", "desactivar"}


def _show(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]" if v else "(vacía)"
    if isinstance(v, bool):
        return "sí" if v else "no"
    s = str(v)
    return s if len(s) <= 120 else s[:117] + "…"


def describe(cfg) -> str:
    lines = ["Ajustes que puedes consultar y cambiar (los marcados con 🔒 afectan a la seguridad):"]
    for k, (desc, sec) in SETTINGS.items():
        lines.append(f"- {k}{' 🔒' if sec else ''}: {_show(cfg[k])} — {desc}")
    lines.append("Las claves API y contraseñas no se pueden ver ni cambiar desde aquí: el usuario las pone en Ajustes.")
    return "\n".join(lines)


def _coerce(key: str, value, current):
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        t = str(value).strip().lower()
        if t in TRUE:
            return True
        if t in FALSE:
            return False
        raise ValueError(f"«{key}» es sí/no")
    if isinstance(current, list):
        if isinstance(value, str):
            value = [x.strip() for x in value.replace(";", "\n").splitlines() if x.strip()]
        if not isinstance(value, list):
            raise ValueError(f"«{key}» es una lista")
        return [str(x) for x in value]
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            f = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"«{key}» debe ser un número")
        return int(f) if f.is_integer() else f
    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"«{key}» debe ser un número")
    v = str(value)
    if key in CHOICES and v not in CHOICES[key]:
        raise ValueError(f"«{key}» debe ser uno de: {', '.join(sorted(CHOICES[key]))}")
    return v


def plan(cfg, changes) -> tuple[dict, list[str], list[str], bool]:
    """(cambios normalizados, errores, líneas «antes → después», ¿toca la seguridad?)."""
    if isinstance(changes, str):
        try:
            changes = json.loads(changes)
        except json.JSONDecodeError:
            return {}, ["«changes» debe ser un objeto {ajuste: valor}"], [], False
    if not isinstance(changes, dict) or not changes:
        return {}, ["indica en «changes» qué ajustes cambiar, p. ej. {\"temperature\": 0.3}"], [], False
    out, errors, diffs, security = {}, [], [], False
    for k, v in changes.items():
        if k not in SETTINGS:
            errors.append(f"«{k}» no se puede cambiar desde el chat" + (" (es una clave o contraseña: ponla en Ajustes)"
                                                                         if "key" in k or "token" in k else ""))
            continue
        try:
            nv = _coerce(k, v, cfg[k])
        except ValueError as e:
            errors.append(str(e))
            continue
        if k == "temperature" and not 0 <= float(nv) <= 2:
            errors.append("la temperatura va de 0 a 2")
            continue
        if nv == cfg[k]:
            continue
        out[k] = nv
        diffs.append(f"{k}: {_show(cfg[k])} → {_show(nv)}")
        security = security or SETTINGS[k][1]
    return out, errors, diffs, security


def apply(cfg, normalized: dict) -> None:
    for k, v in normalized.items():
        cfg.set(k, v)
