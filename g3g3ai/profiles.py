"""Perfiles de capacidad: el agente se adapta a la potencia del modelo.

- «full»: modelos grandes (Claude Sonnet/Opus, GPT-5/4.1, Gemini Pro, DeepSeek V3/R1, 30B+…). Todas las herramientas
  y el método completo; se les anima a leer varios archivos a la vez.
- «standard»: modelos medianos o rápidos (Haiku, mini/flash, 8–14B). Método completo.
- «small»: modelos locales pequeños (≤7B o desconocidos en local). Menos herramientas a la vez, reglas más cortas,
  un paso por turno y salidas de herramientas más pequeñas: así cometen menos errores con las llamadas.
"""
from __future__ import annotations

import re

FULL = re.compile(r"opus|sonnet|fable|mythos|gpt-?5(?!.*(mini|nano))|gpt-?4\.1(?!.*(mini|nano))|gpt-?4o(?!.*mini)|"
                  r"\bo[134](?!.*mini)|gemini-?[\d.]*-?pro|deepseek[-/ ]?(v3|r1|chat|reasoner)|kimi|glm-?[45]|"
                  r"qwen3?-?(max|plus|coder-?(480|235|30))|llama-?3\.[13]-?(70|405)|grok-?[34]|mistral-?large", re.I)
STANDARD = re.compile(r"haiku|mini|flash|nano|small|medium|gemma-?\d*-?(27|12)b|phi-?4", re.I)
PROFILES = ("small", "standard", "full")


def _params_b(name: str) -> float | None:
    """Tamaño en miles de millones de parámetros, si el nombre lo dice (7b, 14B, 0.5b, 8x7b…)."""
    m = re.search(r"(\d+)x(\d+(?:\.\d+)?)\s*b\b", name, re.I)
    if m:
        return float(m.group(1)) * float(m.group(2)) * 0.5  # MoE: se cuenta ~la mitad como «efectivo»
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*b(?![a-z])", name, re.I)
    return float(m.group(1)) if m else None


def profile_for(provider: str, model: str, local: bool, override: str = "auto") -> str:
    if override in PROFILES:
        return override
    name = model or ""
    size = _params_b(name)
    if size is not None:
        if size >= 30:
            return "full"
        if size >= 9:
            return "standard"
        return "small"
    if FULL.search(name):
        return "full"
    if STANDARD.search(name):
        return "standard"
    return "small" if local else "standard"


# Herramientas que se ofrecen a un modelo pequeño (menos opciones = menos errores al elegir)
SMALL_TOOLS = {"mail_search", "mail_read", "system_info", "list_dir", "read_file", "grep_files", "edit_file", "write_file", "run_command", "web_search", "fetch_url",
               "memory_save"}
RESULT_SCALE = {"small": 0.5, "standard": 1.0, "full": 1.0}

SMALL_AGENT_PROMPT = """\
## Cómo trabajar con herramientas
1. Antes de cambiar algo, míralo: list_dir, grep_files, read_file. No supongas.
2. Haz UNA llamada a herramienta cada vez y espera el resultado.
3. Para editar: read_file primero y luego edit_file con el texto EXACTO que quieres cambiar.
4. Después de cambiar, comprueba el resultado (relee o ejecuta las pruebas).
5. Si hay un error, léelo y arréglalo; no repitas lo mismo.
6. No escribas «ahora hago X»: llama a la herramienta. Termina cuando la tarea esté hecha.
7. Nunca inventes resultados. Si algo falló, dilo.
8. Respuesta final: qué hiciste y qué falta, en pocas frases."""

FULL_EXTRA = (
    "\nTienes margen para trabajar en profundidad: lee varios archivos a la vez cuando sean independientes, "
    "cruza la información antes de concluir y revisa tu propio trabajo antes de dar la tarea por terminada."
)

SUBAGENT_PROMPT = (
    "Eres un ayudante de investigación de G3G3AI. Tu jefe te da una tarea concreta. Sólo puedes LEER (archivos, "
    "búsqueda, web, GitHub): no modifiques nada. Investiga con las herramientas, no supongas, y termina con un "
    "informe breve y verificable: hechos concretos con ruta:línea o enlace, qué encontraste y qué no pudiste "
    "confirmar. Sin relleno ni propuestas de cambios que no te pidieron."
)

SUBAGENT_WRITE_PROMPT = (
    "Eres un ayudante de G3G3AI que trabaja en una COPIA aislada del proyecto: puedes leer, editar y (si hay) ejecutar "
    "comandos con libertad, sin pedir permiso, porque nada de lo que hagas toca los archivos reales. Haz sólo la tarea "
    "que te dan, compruébala (tests o ejecución) y termina con un informe breve: qué cambiaste, qué comprobaste y "
    "qué no pudiste comprobar. Tu trabajo se devolverá como un diff para que lo revisen y lo apliquen."
)

GIT_PROMPT = """\
## Git y GitHub
- Antes de tocar nada mira `git status` y `git branch --show-current`. No trabajes sobre la rama principal: crea una rama con nombre claro.
- Commits pequeños y con mensaje que explique el porqué. No incluyas secretos ni archivos generados.
- `git push` siempre pide permiso al usuario; nunca fuerces un push ni reescribas historia ajena.
- Para ver o gestionar issues, pull requests o CI usa la herramienta `github` (leer es libre; crear o comentar pide permiso).
- Antes de abrir un PR comprueba que los tests pasan y resume los cambios en la descripción. Tras abrirlo, mira `checks` y corrige lo que falle."""
