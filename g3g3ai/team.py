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


MAX_TEAMS = 30


def clean_saved(t) -> dict:
    """Un equipo guardado (con nombre): mismos miembros que el general, sin interruptor de activado."""
    if not isinstance(t, dict):
        raise ValueError("Equipo no válido")
    name = re.sub(r"\s+", " ", str(t.get("name") or "").strip())[:60]
    if not name:
        raise ValueError("Ponle un nombre al equipo")
    base = clean({**t, "enabled": True})
    return {"id": re.sub(r"[^a-z0-9]", "", str(t.get("id") or "").lower())[:16] or uuid.uuid4().hex[:10],
            "name": name, "members": base["members"]}


def for_project(cfg_team: dict | None, saved: list | None, project: dict | None) -> dict | None:
    """Equipo que trabaja en una conversación: el que tenga asignado su proyecto, ninguno si el proyecto lo
    indica («none») o, si no, el equipo general cuando está activo."""
    tid = (project or {}).get("team_id") or ""
    if tid == "none":
        return None
    if tid:
        t = next((x for x in saved or [] if x.get("id") == tid), None)
        if t and t.get("members"):
            return {"enabled": True, "name": t["name"], "members": t["members"]}
    g = cfg_team or {}
    return g if g.get("enabled") and g.get("members") else None


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
