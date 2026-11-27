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


def resolve_model(text: str, choices: list[str]) -> str | None:
    """«glm-5.3-flash», «OpenCode Go / glm-5.3-flash», «go::glm-5.3-flash» o «local» → «proveedor::modelo» de choices."""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if low in ("local", "local::local", "modelo local"):
        return "local::local"
    by_low = {c.lower(): c for c in choices}
    if low in by_low:
        return by_low[low]
    tail = low.split("::")[-1].split("/")[-1].strip()
    same = [c for c in choices if c.lower().split("::", 1)[-1] == tail or c.lower().split("::", 1)[-1].split("/")[-1] == tail]
    if len(same) >= 1:
        return same[0]
    near = [c for c in choices if tail and tail in c.lower()]
    return near[0] if len(near) == 1 else None


def proposal(args: dict, choices: list[str]) -> tuple[dict | None, str | None]:
    """Valida la propuesta de equipo de la IA. (propuesta, error para que la IA la corrija)."""
    name = re.sub(r"\s+", " ", str(args.get("name") or "").strip())[:60]
    if not name:
        return None, "Falta el nombre del equipo (name)."
    members, bad = [], []
    for m in (args.get("members") or [])[:MAX_MEMBERS]:
        if not isinstance(m, dict):
            continue
        model = resolve_model(str(m.get("model") or ""), choices)
        if not model:
            bad.append(f"{m.get('name') or '?'} → «{m.get('model')}»")
            continue
        members.append({"id": uuid.uuid4().hex[:8], "name": re.sub(r"\s+", " ", str(m.get("name") or "Miembro").strip())[:40],
                        "role": str(m.get("role") or "").strip()[:600], "model": model,
                        "tools": "read" if str(m.get("tools") or "") in ("read", "lectura", "leer") else "none",
                        "why": str(m.get("why") or "").strip()[:200]})
    if bad:
        return None, ("Estos modelos no están disponibles: " + "; ".join(bad) + ". Usa uno de esta lista (escríbelo tal cual): "
                      + ", ".join(choices[:80]))
    if not members:
        return None, "El equipo necesita al menos un miembro (members)."
    seen = set()
    for m in members:                                   # nombres únicos
        base, i = m["name"], 2
        while m["name"].lower() in seen:
            m["name"] = f"{base} {i}"
            i += 1
        seen.add(m["name"].lower())
    return {"id": uuid.uuid4().hex[:10], "name": name, "purpose": str(args.get("purpose") or "").strip()[:400],
            "director": str(args.get("director") or "").strip()[:300], "members": members}, None


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
