"""Modo Auto: decide en cada mensaje si responde el modelo local (rápido/gratis) o uno por API (potente).

Estrategias:
  smart        local para charla y preguntas cortas; API para código, análisis, documentos largos y agente.
  local_first  siempre local; la API sólo si el local no está disponible o falla.
  api_first    siempre API; el local sólo si la API no está disponible o falla.
En todos los casos, si el elegido falla antes de responder, se reintenta con el otro.
"""
from __future__ import annotations

import re

HEAVY = re.compile(
    r"(c[oó]digo|program|script|funci[oó]n|clase\b|compil|error|traceback|excepci[oó]n|depur|debug|bug|"
    r"refactor|optimiz|algoritm|sql|regex|arquitect|analiz|an[aá]lisis|investig|compara|plan\b|planific|"
    r"demuestra|matem|ecuaci|calcula|razona|paso a paso|informe|redacta|ensayo|python|javascript|rust|c\+\+|"
    r"bash|docker|linux|instala|configura)",
    re.I,
)
LONG_INPUT = 1200  # caracteres


def split(spec: str) -> tuple[str, str]:
    pid, _, model = (spec or "").partition("::")
    return pid, model or pid


def plan(cfg, text: str, has_attachments: bool, agent: bool, available) -> list[tuple[str, str, str]]:
    """Devuelve candidatos [(provider, model, motivo)] en orden de preferencia."""
    fast, strong = split(cfg["router_fast"]), split(cfg["router_strong"])
    fast_ok, strong_ok = available(fast[0]), available(strong[0])
    mode = cfg["router_mode"] or "smart"

    if mode == "local_first":
        prefer_strong, reason = False, "local primero"
    elif mode == "api_first":
        prefer_strong, reason = True, "API primero"
    elif agent:
        prefer_strong, reason = True, "modo agente → modelo potente"
    elif has_attachments or len(text) > LONG_INPUT:
        prefer_strong, reason = True, "entrada larga → modelo potente"
    elif HEAVY.search(text):
        prefer_strong, reason = True, "tarea compleja → modelo potente"
    else:
        prefer_strong, reason = False, "pregunta sencilla → modelo local"

    order = [(strong, reason), (fast, "respaldo local")] if prefer_strong else \
            [(fast, reason), (strong, "respaldo API")]
    out = []
    for (pid, model), why in order:
        ok = strong_ok if (pid, model) == strong else fast_ok
        if ok and pid and (pid, model) not in [(c[0], c[1]) for c in out]:
            if not out and why.startswith("respaldo"):
                why = "el preferido no está disponible"
            out.append((pid, model, why))
    return out
