"""Equipo: G3G3AI (el modelo del chat) dirige y delega trabajo en otros modelos con un papel concreto.

Ajuste «team»: {"enabled": bool, "show_claude": bool, "members": [{id, name, role, model, tools}]}
- model: «proveedor::modelo» o «local::local».
- tools: «none» (solo responde) o «read» (puede leer archivos, buscar en la web y consultar el correo, sin modificar nada).
"""
from __future__ import annotations

import re
import uuid

MAX_MEMBERS = 8
TOOLS = ("none", "read")
DEFAULT = {"enabled": False, "show_claude": True, "members": []}


def clean(team) -> dict:
    """Valida y normaliza el equipo que llega de la interfaz."""
    if not isinstance(team, dict):
        raise ValueError("Equipo no válido")
    out = {"enabled": bool(team.get("enabled")), "show_claude": bool(team.get("show_claude", True)), "members": []}
    seen = set()
    for m in (team.get("members") or [])[:MAX_MEMBERS]:
        if not isinstance(m, dict):
            continue
        name = re.sub(r"\s+", " ", str(m.get("name") or "").strip())[:40]
        model = str(m.get("model") or "").strip()[:200]
        if not name or "::" not in model:
            raise ValueError(f"Cada miembro necesita nombre y modelo ({name or 'sin nombre'})")
        if name.lower() in seen:
            raise ValueError(f"Hay dos miembros llamados «{name}»")
        seen.add(name.lower())
        out["members"].append({"id": str(m.get("id") or uuid.uuid4().hex[:8])[:16], "name": name,
                               "role": str(m.get("role") or "").strip()[:600], "model": model,
                               "tools": m.get("tools") if m.get("tools") in TOOLS else "none"})
    return out


def find(team: dict, who: str) -> dict | None:
    w = (who or "").strip().lower()
    for m in team.get("members", []):
        if w in (m["id"].lower(), m["name"].lower()):
            return m
    for m in team.get("members", []):  # aproximado: «el programador» → «Programador»
        if w and (w in m["name"].lower() or m["name"].lower() in w):
            return m
    return None


def roster(team: dict) -> str:
    return "\n".join(f"- {m['name']} ({m['model'].split('::', 1)[-1]}): {m['role'] or 'sin papel definido'}"
                     + (" [puede leer archivos, web y correo]" if m["tools"] == "read" else "")
                     for m in team.get("members", []))


def member_prompt(m: dict) -> str:
    return (f"Eres «{m['name']}», miembro del equipo de G3G3AI. Tu papel: {m['role'] or 'ayudar en lo que se te pida'}.\n"
            "El director del equipo te encarga una tarea concreta. Hazla bien y devuélvele un informe claro, breve y "
            "verificable (datos concretos, rutas, fuentes). Si algo no lo sabes o no lo pudiste comprobar, dilo. "
            "No hables con el usuario: tu respuesta la lee el director.")
