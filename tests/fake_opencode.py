"""Servidor OpenCode falso para las pruebas: API HTTP con Basic, sesiones y mensajes en memoria.

`start()` arranca uvicorn en un hilo (en un puerto libre) y devuelve su URL; `stop()` lo para.
El prompt añade un mensaje de usuario y, ~0.3 s después, la respuesta del asistente.
"""
from __future__ import annotations

import base64
import socket
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Response

USER = "opencode"
PASSWORD = "clave-de-prueba"

app = FastAPI()
SESSIONS: dict[str, dict] = {}
MESSAGES: dict[str, list] = {}
RUNNING: set[str] = set()
PENDING: list[dict] = []  # peticiones de permiso pendientes
_lock = threading.RLock()  # reentrante: los contadores se generan dentro del mismo bloque
_seq = {"n": 0}
_server = None


def _now() -> float:
    return time.time() * 1000  # OpenCode usa marcas de tiempo en milisegundos


def _next(prefix: str) -> str:
    with _lock:
        _seq["n"] += 1
        return f"{prefix}{_seq['n']}"


def _seed() -> None:
    with _lock:
        SESSIONS.clear()
        MESSAGES.clear()
        RUNNING.clear()
        PENDING.clear()
        sid = "ses_ejemplo"
        SESSIONS[sid] = {"id": sid, "title": "Sesión de ejemplo", "projectID": "prj_fake",
                         "agent": "build", "model": {"id": "fake", "providerID": "fake"},
                         "cost": 0, "tokens": {}, "time": {"created": _now(), "updated": _now()},
                         "location": {"directory": "C:/prueba"}}
        MESSAGES[sid] = []


def _check(authorization: str = Header(default="")) -> None:
    esperado = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    if authorization != esperado:
        raise HTTPException(401, "No autorizado")


def _session(sid: str) -> dict:
    if sid not in SESSIONS:
        raise HTTPException(404, "SessionNotFoundError: sesión no encontrada")
    return SESSIONS[sid]


auth = Depends(_check)


def add_permission(rid: str = "perm1", sid: str = "ses_ejemplo") -> None:
    """Añade una petición de permiso pendiente (la reemplaza si ya existía con ese id)."""
    with _lock:
        PENDING[:] = [p for p in PENDING if p.get("id") != rid]
        PENDING.append({"id": rid, "sessionID": sid, "action": "bash", "resources": ["ls"],
                        "save": [], "metadata": {}, "source": "tool", "message": "Ejecutar ls"})


@app.get("/api/info", dependencies=[auth])
def info():
    return {"version": "0.0.0-fake", "pid": 0, "urls": [], "paths": {"tmp": "/tmp"}}


@app.get("/api/session/active", dependencies=[auth])
def active():
    return {"data": {sid: {"type": "running"} for sid in sorted(RUNNING)}}


@app.get("/api/session", dependencies=[auth])
def list_sessions(limit: int = 50):
    items = sorted(SESSIONS.values(), key=lambda s: s["time"]["updated"], reverse=True)
    return {"data": items[:limit], "cursor": {"previous": None, "next": None}}


@app.post("/api/session", dependencies=[auth])
def create_session(body: dict):
    sid = _next("ses_")
    now = _now()
    loc = (body or {}).get("location") or {}
    SESSIONS[sid] = {"id": sid, "title": (body or {}).get("title"), "projectID": "prj_fake",
                     "agent": "build", "model": {"id": "fake", "providerID": "fake"},
                     "cost": 0, "tokens": {}, "time": {"created": now, "updated": now},
                     "location": {"directory": loc.get("directory") or "C:/prueba"}}
    MESSAGES[sid] = []
    return {"data": SESSIONS[sid]}


@app.get("/api/session/{sid}/message", dependencies=[auth])
def messages(sid: str):
    _session(sid)
    return {"data": list(MESSAGES[sid]), "cursor": {"previous": None, "next": None}}


def _responder(sid: str) -> None:
    with _lock:
        if sid not in SESSIONS:
            return
        MESSAGES[sid].append({"id": _next("msg_a"), "type": "assistant", "agent": "build",
                              "model": {"id": "fake", "providerID": "fake"},
                              "content": [{"type": "text", "text": "Respuesta falsa del asistente."}],
                              "time": {"created": _now(), "completed": _now()}})
        RUNNING.discard(sid)


@app.post("/api/session/{sid}/prompt", dependencies=[auth])
def prompt(sid: str, body: dict):
    _session(sid)
    with _lock:
        MESSAGES[sid].append({"id": _next("msg_u"), "type": "user", "time": {"created": _now()},
                              "text": (body or {}).get("text", "")})
        RUNNING.add(sid)
    threading.Timer(0.3, _responder, args=(sid,)).start()
    return {"data": {"id": MESSAGES[sid][-1]["id"]}}


@app.post("/api/session/{sid}/interrupt", dependencies=[auth])
def interrupt(sid: str):
    _session(sid)
    with _lock:
        RUNNING.discard(sid)
    return {"interrupted": True}


@app.get("/api/permission/request", dependencies=[auth])
def permission_request():
    return {"location": {"directory": "C:/prueba"}, "data": list(PENDING)}


@app.post("/api/session/{sid}/permission/{rid}/reply", dependencies=[auth])
def permission_reply(sid: str, rid: str, body: dict):
    _session(sid)
    if (body or {}).get("decision") not in ("once", "always", "reject"):
        raise HTTPException(400, "Decisión no válida")
    return Response(status_code=204)


@app.delete("/api/session/{sid}", dependencies=[auth])
def delete_session(sid: str):
    _session(sid)
    with _lock:
        SESSIONS.pop(sid, None)
        MESSAGES.pop(sid, None)
        RUNNING.discard(sid)
    return Response(status_code=204)


def start() -> str:
    """Arranca el servidor falso en un hilo (puerto libre) y devuelve su URL."""
    global _server
    import uvicorn
    _seed()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    _server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=_server.run, daemon=True).start()
    for _ in range(200):
        if _server.started:
            break
        time.sleep(0.02)
    return f"http://127.0.0.1:{port}"


def stop() -> None:
    if _server is not None:
        _server.should_exit = True
