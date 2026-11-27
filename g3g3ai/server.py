"""Servidor web de G3G3AI: API + interfaz, accesible desde la red local."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import platform
import re
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import __version__
from .config import MASK, DATA_DIR, Config
from .db import DB
from .files import FileAccessError, Files
from .hub import Hub
from .memory import Memory, MemoryRejected
from .llama import LlamaManager, default_threads, find_llama_server
from . import router, sandbox
from . import backup, catalog, costs, mcp_server, profiles, subagent, team
from .mail import MailIndex, thunderbird_profiles, mail_sources
from .mcp import MCPManager
from .tasks import Scheduler, TaskError, TaskStore, next_run
from .profiles import profile_for
from .undo import UndoJournal
from .engine import EngineInstaller
from . import documents as D
from . import devtools, extras, hardware, images, ollama, projects, web
from .context import HistoryBuilder
from .sync import INTERVAL as SYNC_INTERVAL, Sync, SyncError, new_key as new_sync_key
from . import providers as providers_mod
from .providers import ProviderError, chat_stream, complete, complete_messages, list_models
from .tools import ToolContext, resolve_approval, tool_events

STATIC = Path(__file__).parent / "static"
COOKIE = "g3g3ai_token"
LOCAL_PROVIDER = "local"
AUTO_PROVIDER = "auto"


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# --- Utilidades del sistema ----------------------------------------------------------
def meminfo() -> dict:
    info = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    except OSError:
        return {}
    return {"total": info.get("MemTotal", 0), "available": info.get("MemAvailable", 0),
            "swap_total": info.get("SwapTotal", 0)}


def lan_addresses() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(res[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


async def with_keepalive(agen, every: float = 15.0):
    """Reenvía los eventos de `agen`; si pasan `every` segundos sin ninguno, produce None (latido)."""
    it = agen.__aiter__()
    nxt = asyncio.ensure_future(it.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({nxt}, timeout=every)
            if not done:
                yield None
                continue
            try:
                ev = nxt.result()
            except StopAsyncIteration:
                return
            yield ev
            nxt = asyncio.ensure_future(it.__anext__())
    finally:
        nxt.cancel()
        await it.aclose() if hasattr(it, "aclose") else None


ARTIFACT_NOTE = (
    "Si te piden una página web, una visualización, un gráfico o un diagrama, entrégalo en un único bloque de código "
    "completo y autocontenido (```html con CSS y JS dentro, ```svg o ```mermaid): el usuario lo ve funcionando en un panel "
    "al lado del chat. Para cambiarlo, vuelve a escribir el bloque entero.")
APP_FEATURES = (
    "## Qué ofrece G3G3AI (si te preguntan si algo existe o cómo se hace, contesta con esto; nunca digas que no existe "
    "una función de esta lista)\n"
    "- Tareas programadas: sección «Tareas» (hora, días de la semana, encargo); tú también puedes crearlas con scheduled_tasks.\n"
    "- Permisos en el propio chat: el selector Manual / Semi-auto / Auto junto al cuadro de texto.\n"
    "- Archivos en el chat: con attach_file adjuntas cualquier archivo existente (abrir / mostrar en la carpeta / descargar); "
    "create_document crea Word, Excel, PowerPoint o PDF.\n"
    "- Proyectos (instrucciones y documentos compartidos), Code, Equipo de IAs, Modelos locales, búsqueda en las "
    "conversaciones, exportar una conversación (Markdown/Word/PDF), dictado por voz, Ctrl+K, copia cifrada en OneDrive/Google Drive.\n"
    "- Los PDF escaneados y las imágenes se leen con OCR en el propio equipo.")
NO_AGENT_NOTE = (
    "## Herramientas del equipo desactivadas\n"
    "El modo Agente está desactivado en este chat: no puedes leer archivos, ejecutar comandos ni ver el hardware del "
    "usuario. Si lo que pide lo necesita (hardware, archivos, correo, comandos, carpetas), díselo en una frase y dile que "
    "active «🛠 Agente» en el menú ⚙ junto al cuadro de texto; no le pidas que te pegue la salida de comandos que el agente "
    "podría obtener solo. Lo que SÍ puedes hacer siempre: crear documentos Word, Excel, PowerPoint o PDF con create_document "
    "(si te piden «un Excel», «un Word», «un PDF», créalo; nunca digas que no puedes ni ofrezcas CSV para copiar).")


def create_app(cfg: Config | None = None, data_dir: Path | None = None) -> FastAPI:
    cfg = cfg or Config()
    db = DB((data_dir or DATA_DIR) / "g3g3ai.db")
    files = Files(cfg)
    hub = Hub(cfg)
    llama = LlamaManager(cfg)
    engines = {"llama": EngineInstaller(cfg, "llama"), "sd": EngineInstaller(cfg, "sd")}
    memory = Memory(db)
    sync = Sync(cfg, db, memory)
    from .cloudsync import CloudError, CloudSync
    cloud = CloudSync(cfg, sync)
    mcp_mgr = MCPManager(cfg)
    task_store = TaskStore(db)
    mail_index = MailIndex(cfg)
    session_allow: dict[str, set] = {}  # conversación -> herramientas permitidas «siempre»
    session_state: dict[str, dict] = {}  # conversación -> {"read": archivos leídos, "todos": plan de la tarea}

    def state_for(cid: str, conv: dict | None = None) -> dict:
        if cid not in session_state:
            todos = []
            for m in reversed((conv or {}).get("messages", [])):  # recupera el plan si el servidor se reinició
                if (m.get("meta") or {}).get("todos"):
                    todos = m["meta"]["todos"]
                    break
            session_state[cid] = {"read": {}, "todos": todos}
        return session_state[cid]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        last = cfg["last_model"]
        if cfg["autoload_last_model"] and last and Path(last).is_file():
            await llama.load(last)
        sync.start()
        cloud.start()
        scheduler.start()
        if cfg["mail_enabled"]:
            mail_index.start()          # pone al día el índice del correo en segundo plano
        yield
        scheduler.stop()
        mail_index._stop = True
        sync.stop()
        cloud.stop()
        await mcp_mgr.stop()
        await llama.unload()

    async def chat_internal(body: dict) -> tuple[str | None, str, str | None, dict]:
        """Llama al propio /api/chat (con todo: herramientas, memoria, uso…) y devuelve (conversación, texto, error, done)."""
        cid, text, err, done = None, "", None, {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://interno", timeout=3600) as c:
            async with c.stream("POST", "/api/chat", json=body, headers={"Authorization": f"Bearer {cfg['token']}"}) as r:
                if r.status_code >= 400:
                    detail = (await r.aread()).decode("utf-8", "replace")
                    try:
                        detail = json.loads(detail).get("detail", detail)
                    except ValueError:
                        pass
                    return None, "", str(detail), {}
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:])
                    if ev["type"] == "start":
                        cid = ev["conversation_id"]
                    elif ev["type"] == "content":
                        text += ev["text"]
                    elif ev["type"] == "error":
                        err = ev["message"]
                    elif ev["type"] == "done":
                        done = ev
        return cid, text, err, done

    async def mcp_call(name: str, args: dict) -> tuple[str, bool]:
        if name == "list_models":
            if args.get("provider"):
                try:
                    ms = await list_models(provider_for(str(args["provider"])))
                except (ProviderError, httpx.HTTPError, HTTPException) as e:
                    return f"No se pudo listar: {getattr(e, 'detail', e)}", True
                return "\n".join(f"{args['provider']}::{m}" for m in ms) or "(sin modelos)", False
            lines = [f"local — {'cargado: ' + (llama.status()['model'] or '') if llama.ready else 'no hay modelo local cargado'}"]
            for p in cfg["providers"]:
                if p.get("enabled") and (p.get("api_key") or str(p.get("base_url", "")).startswith("http://")):
                    lines.append(f"{p['id']} — {p['name']} (usa list_models con provider={p['id']} para ver sus modelos)")
            dm = cfg["mcp_default_model"]
            lines.append(f"Modelo por defecto para «ask»: {dm or ('local' if llama.ready else 'ninguno: indica model')}")
            return "\n".join(lines), False
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return "Falta «prompt».", True
        pid, model = mcp_server.parse_model(args.get("model") or cfg["mcp_default_model"])
        if pid is None and model:
            return "Indica el modelo como «proveedor::modelo» (o «local»); mira list_models.", True
        if pid is None:
            if not llama.ready:
                return ("No hay modelo por defecto ni modelo local cargado. Indica «model» (ver list_models) o elige uno en "
                        "G3G3AI → Ajustes → Correo e integraciones → «Modelo para Claude».", True)
            pid, model = LOCAL_PROVIDER, "local"
        tools = bool(args.get("use_tools"))
        body = {"message": prompt, "provider": pid, "model": model, "use_tools": tools, "use_web": bool(args.get("web")),
                "mode": "edits" if args.get("mode") == "edit" else "plan", "unattended": True}
        if args.get("conversation_id"):
            body["conversation_id"] = str(args["conversation_id"])
        if args.get("workdir"):
            body["workdir"] = str(args["workdir"])
        cid, text, err, done = await chat_internal(body)
        if cid and not args.get("conversation_id"):
            db.update_conversation(cid, title=("Claude: " + " ".join(prompt.split()))[:60])
        if err and not text.strip():
            return f"G3G3AI no pudo responder: {err}", True
        shown = llama.status()["model"] if pid == LOCAL_PROVIDER else model
        return f"{text.strip()}\n\n[conversation_id: {cid} · modelo: {shown}]", False

    async def run_task(task: dict) -> tuple[str, str | None]:
        """Ejecuta una tarea programada llamando al propio /api/chat en modo sin supervisión."""
        pid, model = task["provider"] or LOCAL_PROVIDER, task["model"] or "local"
        if pid == LOCAL_PROVIDER and not llama.ready and llama.state != "loading" and not pick_local_model():
            return "No se ejecutó: no hay ningún modelo local descargado.", None   # si lo hay, /api/chat lo carga solo
        if pid != LOCAL_PROVIDER and not provider_available(pid):
            return f"No se ejecutó: el proveedor «{pid}» no está disponible o no tiene clave.", None
        body = {"message": task["prompt"], "provider": pid, "model": model, "use_tools": True, "use_web": True,
                "mode": task["mode"], "unattended": True, "task_level": task.get("level"),
                "system": (cfg["default_system_prompt"] or "") + "\n\nTrabajas en SEGUNDO PLANO, sin supervisión: nadie puede "
                          "aprobar acciones. Si algo se deniega, sigue sin ello. Termina con un informe breve de lo que hiciste y encontraste."}
        if task.get("workdir"):
            body["workdir"] = task["workdir"]
        cid, text, error = None, "", None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://tarea", timeout=3600) as c:
            async with c.stream("POST", "/api/chat", json=body, headers={"Authorization": f"Bearer {cfg['token']}"}) as r:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:])
                    if ev["type"] == "start":
                        cid = ev["conversation_id"]
                    elif ev["type"] == "content":
                        text += ev["text"]
                    elif ev["type"] == "error":
                        error = ev["message"]
        if cid:
            db.update_conversation(cid, title=f"🕒 {task['name']} · {time.strftime('%d/%m %H:%M')}"[:60])
        if error and not text.strip():
            return f"Falló: {error}", cid
        return ("Terminada: " + " ".join(text.split())[:240]) if text.strip() else "Terminada (sin texto).", cid

    scheduler = Scheduler(task_store, run_task)

    app = FastAPI(title="G3G3AI", version=__version__, lifespan=lifespan)
    app.state.mcp = mcp_mgr
    app.state.cfg, app.state.db, app.state.llama, app.state.hub = cfg, db, llama, hub
    app.state.task_store = task_store

    # --- Autenticación --------------------------------------------------------------
    def authorized(request: Request) -> bool:
        client = request.client.host if request.client else ""
        if cfg["localhost_without_token"] and client in ("127.0.0.1", "::1"):
            return True
        token = request.cookies.get(COOKIE) or request.query_params.get("token") or ""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        return bool(token) and secrets.compare_digest(token, cfg["token"])

    @app.middleware("http")
    async def auth_mw(request: Request, call_next):
        path = request.url.path
        if ((path.startswith("/api/") or path.startswith("/v1/") or path == "/mcp")
                and path not in ("/api/login", "/api/sync/exchange")):  # la sincronización va cifrada con su clave
            if not authorized(request):
                return JSONResponse({"detail": "No autorizado"}, status_code=401)
        response = await call_next(request)
        # Permite entrar con ?token=... (p.ej. desde un QR) y lo recuerda en una cookie.
        qt = request.query_params.get("token")
        if path == "/" and qt and secrets.compare_digest(qt, cfg["token"]):
            response.set_cookie(COOKIE, qt, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
        return response

    @app.post("/api/login")
    async def login(body: dict):
        token = str(body.get("token", ""))
        if not secrets.compare_digest(token, cfg["token"]):
            raise HTTPException(401, "Contraseña incorrecta")
        r = JSONResponse({"ok": True})
        r.set_cookie(COOKIE, token, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
        return r

    @app.post("/api/logout")
    async def logout():
        r = JSONResponse({"ok": True})
        r.delete_cookie(COOKIE)
        return r

    # --- Estado / ajustes -------------------------------------------------------------
    @app.get("/api/status")
    async def status(request: Request):
        is_local = request.client and request.client.host in ("127.0.0.1", "::1")
        port = cfg["port"]
        return {
            "version": __version__,
            "extras": extras.summary(),
            "ocr": ocr_ok(),
            "llama": llama.status(),
            "memory": meminfo(),
            "cpu_count": os.cpu_count(),
            "default_threads": default_threads(),
            "hostname": socket.gethostname(),
            "urls": [f"http://{ip}:{port}" for ip in lan_addresses()],
            # El token completo sólo se muestra en el propio dispositivo.
            "token": cfg["token"] if is_local else None,
            "disk_free": shutil.disk_usage(hub.models_dir).free,
            "downloads_active": sum(1 for d in hub.downloads.values() if d["status"] == "downloading"),
            "platform": f"{platform.system()} {platform.machine()}",
            "sandbox": {"available": sandbox.bwrap_path() is not None, "active": sandbox.available(cfg),
                        "supported": sys.platform.startswith("linux")},
            "is_local": bool(is_local),
            "router": {"fast": cfg["router_fast"], "strong": cfg["router_strong"], "mode": cfg["router_mode"],
                       "fast_ok": provider_available(router.split(cfg["router_fast"])[0]),
                       "strong_ok": provider_available(router.split(cfg["router_strong"])[0])},
        }

    @app.post("/api/shutdown")
    async def shutdown(request: Request):
        if not (request.client and request.client.host in ("127.0.0.1", "::1")):
            raise HTTPException(403, "Sólo se puede apagar desde el propio equipo")
        stop = getattr(app.state, "request_exit", None)
        if not stop:
            raise HTTPException(501, "No disponible en este modo")
        await llama.unload()
        stop()
        return {"ok": True}

    @app.get("/api/settings")
    async def get_settings():
        return cfg.public()

    @app.put("/api/settings")
    async def put_settings(body: dict):
        cfg.update_public(body)
        return cfg.public()

    _ocr = {}

    def ocr_ok() -> bool:
        if "ok" not in _ocr:
            from . import ocr
            _ocr["ok"] = ocr.available()
        return _ocr["ok"]

    @app.get("/api/ocr/selftest")
    async def ocr_selftest():
        """Dibuja un texto y lo lee con el OCR (comprueba que los modelos van dentro del ejecutable)."""
        from PIL import Image, ImageDraw, ImageFont

        from . import ocr
        if not ocr.available():
            return {"ok": False, "text": "", "error": "OCR no instalado"}
        img = Image.new("RGB", (900, 200), "white")
        ImageDraw.Draw(img).text((40, 60), "Horas extras 12,5 Núñez 2026", font=ImageFont.load_default(size=48), fill="black")
        try:
            text = await asyncio.to_thread(ocr.image_text, img)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "text": "", "error": str(e)}
        return {"ok": "2026" in text and "12,5" in text, "text": text}

    # --- Proveedores ---------------------------------------------------------------
    def provider_for(pid: str) -> dict:
        if pid == LOCAL_PROVIDER:
            return {"id": LOCAL_PROVIDER, "type": "openai", "base_url": llama.base_url + "/v1", "api_key": ""}
        p = cfg.provider(pid)
        if not p:
            raise HTTPException(404, f"Proveedor desconocido: {pid}")
        return p

    @app.get("/api/providers")
    async def providers():
        out = [{"id": AUTO_PROVIDER, "name": "Auto (local ↔ API)", "type": "auto", "enabled": True},
               {"id": LOCAL_PROVIDER, "name": "Local (llama.cpp)", "type": "local", "enabled": True}]
        for p in cfg.public()["providers"]:
            out.append({k: p.get(k) for k in ("id", "name", "type", "enabled")})
        return out

    @app.get("/api/providers/catalog")
    async def providers_catalog():
        have = {p.get("id"): p for p in cfg["providers"]}
        return [{**c, "added": c["id"] in have, "configured": bool((have.get(c["id"]) or {}).get("api_key"))
                 or (c["id"] in have and not c["needs_key"])} for c in catalog.as_list()]

    def _provider_from_body(body: dict) -> dict:
        cur = cfg.provider(str(body.get("id") or "")) or {}
        key = body.get("api_key")
        if key in (None, MASK):
            key = cur.get("api_key", "")
        p = {"id": body.get("id") or "", "name": body.get("name") or cur.get("name") or "Proveedor",
             "type": body.get("type") or cur.get("type") or "openai",
             "base_url": (body.get("base_url") or cur.get("base_url") or "").strip().rstrip("/"), "api_key": (key or "").strip()}
        if not p["base_url"].startswith(("http://", "https://")):
            raise HTTPException(400, "La URL base debe empezar por http:// o https://")
        return p

    @app.post("/api/providers/test")
    async def providers_test(body: dict):
        """Comprueba una configuración (aún sin guardar) pidiendo la lista de modelos."""
        p = _provider_from_body(body)
        try:
            models = await list_models(p)
        except (ProviderError, httpx.HTTPError) as e:
            msg = str(e)
            hint = (" (la clave no es válida o no tiene permiso)" if "401" in msg or "403" in msg else
                    " (¿la URL base es correcta?)" if "404" in msg else "")
            return {"ok": False, "error": msg[:300] + hint}
        return {"ok": True, "count": len(models), "sample": models[:8]}

    @app.post("/api/providers/add")
    async def providers_add(body: dict):
        """Añade (o actualiza) un proveedor del catálogo o personalizado, activado y listo para usar."""
        pre = catalog.preset(str(body.get("preset") or "")) or {}
        merged = {**{k: pre.get(k) for k in ("id", "name", "type", "base_url")}, **{k: v for k, v in body.items() if v not in (None, "")}}
        if not merged.get("id"):
            merged["id"] = re.sub(r"[^a-z0-9]+", "-", str(merged.get("name") or "proveedor").lower()).strip("-")[:24] \
                + "-" + secrets.token_hex(2)
        p = _provider_from_body(merged)
        if pre.get("needs_key") and not p["api_key"]:
            raise HTTPException(400, "Falta la clave API")
        provs = list(cfg["providers"])
        cur = next((x for x in provs if x.get("id") == p["id"]), None)
        if cur:
            cur.update({**p, "enabled": True})
        else:
            provs.append({**p, "enabled": True})
        cfg.data["settings_updated"] = time.time()
        cfg.set("providers", provs)
        return {"ok": True, "id": p["id"]}

    @app.get("/api/providers/export")
    async def providers_export():
        """Proveedores API con sus claves, para el «Chat directo» de la app de Android (requiere la contraseña)."""
        return {"providers": [p for p in cfg["providers"] if p.get("enabled") and p.get("api_key")],
                "system": cfg["default_system_prompt"], "temperature": cfg["temperature"],
                "max_tokens": cfg["max_tokens"]}

    @app.get("/api/providers/{pid}/models")
    async def provider_models(pid: str):
        if pid == LOCAL_PROVIDER:
            st = llama.status()
            return [st["model"]] if st["model"] else []
        try:
            return await list_models(provider_for(pid))
        except (ProviderError, httpx.HTTPError) as e:
            raise HTTPException(502, str(e)) from e

    # --- Conversaciones ------------------------------------------------------------
    @app.get("/api/conversations")
    async def conversations():
        return db.list_conversations()

    @app.post("/api/conversations")
    async def new_conversation(body: dict | None = None):
        body = body or {}
        return db.create_conversation(provider=body.get("provider"), model=body.get("model"),
                                      system=body.get("system"))

    @app.get("/api/conversations/{cid}")
    async def get_conversation(cid: str):
        c = db.get_conversation(cid)
        if not c:
            raise HTTPException(404, "No existe")
        return c

    # --- Proyectos ----------------------------------------------------------------------
    def _check_files(paths) -> list[str]:
        out = []
        for p in paths or []:
            out.append(str(fa(files.resolve, p)))          # sólo carpetas visibles (y nunca las protegidas)
        return list(dict.fromkeys(out))

    @app.get("/api/projects")
    async def projects_list():
        return db.list_projects()

    @app.post("/api/projects")
    async def projects_create(body: dict):
        name = (body.get("name") or "").strip()[:80]
        if not name:
            raise HTTPException(400, "Ponle un nombre al proyecto")
        return db.create_project(name, body.get("instructions") or "", _check_files(body.get("files")))

    @app.get("/api/projects/{pid}")
    async def projects_get(pid: str):
        p = db.get_project(pid)
        if not p:
            raise HTTPException(404, "No existe el proyecto")
        p["conversations"] = [c for c in db.list_conversations() if c.get("project_id") == pid]
        return p

    @app.patch("/api/projects/{pid}")
    async def projects_patch(pid: str, body: dict):
        if not db.get_project(pid):
            raise HTTPException(404, "No existe el proyecto")
        fields = {k: body[k] for k in ("name", "instructions") if k in body}
        if "files" in body:
            fields["files"] = _check_files(body["files"])
        return db.update_project(pid, **fields)

    @app.delete("/api/projects/{pid}")
    async def projects_delete(pid: str):
        db.delete_project(pid)
        return {"ok": True}

    @app.get("/api/search")
    async def search_conversations(q: str = ""):
        return await asyncio.to_thread(db.search, q)

    @app.get("/api/conversations/{cid}/export")
    async def export_conversation(cid: str, fmt: str = "md", tools: bool = False):
        from urllib.parse import quote

        from . import office
        c = db.get_conversation(cid)
        if not c:
            raise HTTPException(404, "No existe")
        try:
            data = await asyncio.to_thread(office.export_conversation, c, fmt, tools)
        except office.OfficeError as e:
            raise HTTPException(400, str(e)) from e
        name = office.export_filename(c, fmt)
        return Response(data, media_type=office.EXPORT_FORMATS[fmt][0],
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    @app.patch("/api/conversations/{cid}")
    async def patch_conversation(cid: str, body: dict):
        db.update_conversation(cid, **body)
        return db.get_conversation(cid)

    @app.delete("/api/conversations/{cid}")
    async def delete_conversation(cid: str):
        db.delete_conversation(cid)
        UndoJournal(cid).clear()
        session_state.pop(cid, None)
        session_allow.pop(cid, None)
        return {"ok": True}

    # --- Copia en la nube (carpeta de OneDrive / Google Drive) ---------------------------------------
    @app.get("/api/cloud")
    async def cloud_status():
        return await asyncio.to_thread(cloud.status)

    @app.post("/api/cloud/setup")
    async def cloud_setup(body: dict):
        try:
            r = await asyncio.to_thread(cloud.setup, str(body.get("dir") or ""), str(body.get("password") or ""),
                                        bool(body.get("conversations", True)))
        except (CloudError, OSError) as e:
            raise HTTPException(400, str(e)) from e
        return {**r, **(await asyncio.to_thread(cloud.status))}

    @app.post("/api/cloud/now")
    async def cloud_now():
        if not cloud.enabled:
            raise HTTPException(409, "La copia en la nube no está activada")
        try:
            r = await cloud.now(force=True)
        except (CloudError, OSError) as e:
            raise HTTPException(400, str(e)) from e
        return {**r, **(await asyncio.to_thread(cloud.status))}

    @app.post("/api/cloud/disable")
    async def cloud_disable():
        cloud.disable()
        return await asyncio.to_thread(cloud.status)

    @app.post("/api/backup/export")
    async def backup_export(body: dict):
        try:
            data = await asyncio.to_thread(backup.export_bytes, sync, cfg, str(body.get("password") or ""),
                                           bool(body.get("conversations")))
        except backup.BackupError as e:
            raise HTTPException(400, str(e))
        name = time.strftime("g3g3ai-%Y%m%d.g3bak")
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/backup/import")
    async def backup_import(body: dict):
        import base64 as b64
        try:
            raw = b64.b64decode(str(body.get("data") or ""), validate=False)
            return await asyncio.to_thread(backup.import_bytes, sync, raw, str(body.get("password") or ""))
        except backup.BackupError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/tasks")
    async def tasks_list():
        return {"tasks": [{**t, "running": t["id"] in scheduler.running} for t in task_store.list()]}

    @app.post("/api/tasks")
    async def tasks_create(body: dict):
        try:
            return task_store.create(str(body.get("name", "")), str(body.get("prompt", "")), body.get("schedule"),
                                     body.get("provider"), body.get("model"), body.get("workdir"), body.get("mode", "plan"),
                                     body.get("level"))
        except TaskError as e:
            raise HTTPException(400, str(e))

    @app.patch("/api/tasks/{tid}")
    async def tasks_update(tid: str, body: dict):
        try:
            t = task_store.update(tid, **{k: v for k, v in body.items() if k in
                                          ("name", "prompt", "schedule", "provider", "model", "workdir", "mode", "enabled", "level")})
        except TaskError as e:
            raise HTTPException(400, str(e))
        if not t:
            raise HTTPException(404, "Tarea no encontrada")
        return t

    @app.delete("/api/tasks/{tid}")
    async def tasks_delete(tid: str):
        task_store.delete(tid)
        return {"ok": True}

    @app.post("/api/tasks/{tid}/run")
    async def tasks_run(tid: str):
        t = task_store.get(tid)
        if not t:
            raise HTTPException(404, "Tarea no encontrada")
        if tid in scheduler.running:
            raise HTTPException(409, "Ya se está ejecutando")
        asyncio.create_task(scheduler.run_now(t))
        return {"ok": True}

    @app.get("/api/mail/status")
    async def mail_status():
        profs = await asyncio.to_thread(thunderbird_profiles)
        srcs = await asyncio.to_thread(mail_sources, cfg)
        return {"enabled": bool(cfg["mail_enabled"]), "profiles": [str(p) for p in profs[:3]],
                "sources": [str(s) for s in srcs], **mail_index.stats()}

    @app.post("/api/mail/index")
    async def mail_reindex(body: dict | None = None):
        if not cfg["mail_enabled"]:
            raise HTTPException(409, "Activa primero «La IA puede buscar en mi correo»")
        started = mail_index.start(rebuild=bool((body or {}).get("rebuild")))
        return {"started": started, **mail_index.stats()}

    @app.post("/mcp")
    async def mcp_http(request: Request):
        """Servidor MCP (HTTP «streamable», respuestas JSON) para Claude Code y otros clientes."""
        try:
            msg = json.loads(await request.body())
        except ValueError:
            return JSONResponse(mcp_server.error(None, -32700, "JSON no válido"), status_code=400)
        if isinstance(msg, list):
            out = [r for r in [await mcp_server.handle(m, mcp_call) for m in msg] if r is not None]
            return JSONResponse(out) if out else Response(status_code=202)
        resp = await mcp_server.handle(msg, mcp_call)
        return Response(status_code=202) if resp is None else JSONResponse(resp)

    @app.get("/mcp")
    async def mcp_http_get():
        return Response(status_code=405, headers={"Allow": "POST"})

    @app.delete("/mcp")
    async def mcp_http_delete():
        return Response(status_code=204)   # fin de sesión del cliente: no hay estado que borrar

    def _has_provider() -> bool:
        return any(p.get("enabled") and p.get("api_key") for p in cfg["providers"])

    @app.get("/api/team")
    async def team_get():
        return {**team.DEFAULT, **(cfg["team"] or {})}

    @app.put("/api/team")
    async def team_put(body: dict):
        try:
            t = team.clean(body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        cfg.data["settings_updated"] = time.time()
        cfg.set("team", t)
        return t

    @app.get("/api/onboarding")
    async def onboarding():
        profs = await asyncio.to_thread(thunderbird_profiles)
        docs = Path.home() / "Documents"
        suggested = (docs if docs.is_dir() else Path.home()) / "G3G3AI"
        rec = None
        try:
            if "hw" not in hw_cache:
                hw_cache["hw"] = await asyncio.to_thread(hardware.detect)
            r = hardware.recommend(hw_cache["hw"])
            rec = {"tier": r["main"]["tier"], "searches": r["main"]["searches"], "ram_gb": r["summary"]["ram_gb"],
                   "gpu": r["summary"]["gpu"]}
        except Exception:  # noqa: BLE001
            pass
        return {"needed": not cfg["onboarded"] and not _has_provider() and not llama.ready,
                "has_provider": _has_provider(), "has_local": llama.ready, "thunderbird": bool(profs),
                "mail_enabled": bool(cfg["mail_enabled"]), "suggested_folder": str(suggested),
                "write_roots": [str(p) for p in cfg["write_roots"] or []], "recommendation": rec}

    @app.post("/api/onboarding/folder")
    async def onboarding_folder(body: dict):
        raw = str(body.get("path") or "").strip()
        p = Path(os.path.expandvars(os.path.expanduser(raw))) if raw else None
        if not p or not p.is_absolute():
            raise HTTPException(400, "Indica la ruta completa de la carpeta")
        p = p.resolve()
        if p == Path.home().resolve() or p.parent == p or len(p.parts) <= 2 and sys.platform == "win32":
            raise HTTPException(400, "Elige una carpeta concreta, no la carpeta personal entera ni la raíz del disco")
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(400, f"No se pudo crear: {e}")
        for k in ("file_roots", "write_roots"):
            cur = list(cfg[k] or [])
            if str(p) not in cur:
                cfg.set(k, cur + [str(p)])
        if not cfg["agent_workdir"]:
            cfg.set("agent_workdir", str(p))
        return {"ok": True, "path": str(p)}

    @app.post("/api/onboarding/done")
    async def onboarding_done():
        cfg.set("onboarded", True)
        return {"ok": True}

    @app.get("/api/diagnostics")
    async def diagnostics(local_in_use: bool = False):
        """«Comprobar todo»: prueba de verdad cada pieza y dice en claro qué falla y cómo arreglarlo."""
        checks: list[dict] = []
        # ajustes que la IA puede cambiar (app_settings) para arreglar cada comprobación
        related = {"local": ["llama_ctx", "llama_gpu_layers", "llama_threads", "autoload_last_model"],
                   "web": ["web_provider"], "folders": ["write_roots", "file_roots"],
                   "commands": ["commands_trusted", "ai_commands", "command_allow"], "mail": ["mail_enabled", "mail_paths"],
                   "disk": [], "providers": []}

        def add(cid, title, status, detail, fix="", action=None, order=0):
            checks.append({"id": cid, "title": title, "status": status, "detail": detail, "fix": fix, "action": action,
                           "order": order, "settings": related.get(cid, ["mcp_servers"] if cid.startswith("mcp-") else [])})

        async def timed(coro, secs):
            try:
                return await asyncio.wait_for(coro, secs)
            except Exception as e:  # noqa: BLE001
                return e

        def why(e) -> str:
            m = str(getattr(e, "detail", "") or e) or type(e).__name__
            if isinstance(e, asyncio.TimeoutError):
                return "no respondió a tiempo"
            if "401" in m or "403" in m and "proxy" not in m:
                return m[:160] + " → la clave no es válida o no tiene permiso"
            if "404" in m:
                return m[:160] + " → revisa la URL base"
            return m[:200]

        add("app", "G3G3AI", "ok", f"Versión {__version__} en {platform.system()} {platform.machine()}", order=0)

        # --- Modelo local
        async def local_check():
            binary = find_llama_server(cfg["llama_server_path"])
            if llama.ready and local_in_use:
                add("local", "Modelo local", "ok", f"{llama.status()['model']} (es el que está respondiendo ahora)", order=1)
            elif llama.ready:
                t0 = time.time()
                r = await timed(complete(provider_for(LOCAL_PROVIDER), "local", "Responde solo con la palabra: listo",
                                         max_tokens=8), 120)
                if isinstance(r, Exception):
                    add("local", "Modelo local", "error", f"{llama.status()['model']} no respondió: {why(r)}",
                        "Descárgalo de memoria y vuelve a cargarlo en Modelos; si sigue, prueba con un modelo más pequeño.", "models", 1)
                else:
                    add("local", "Modelo local", "ok", f"{llama.status()['model']} responde ({time.time() - t0:.1f} s)",
                        "En Modelos, «Probar con el agente» comprueba además si sabe usar herramientas.", "models", 1)
            elif not binary:
                add("local", "Modelo local", "warn", "No está instalado el motor de modelos locales (llama.cpp). "
                    "La edición completa de G3G3AI ya lo incluye.",
                    "Modelos → instalar el motor. O usa solo proveedores en la nube.", "models", 1)
            elif llama.status().get("error"):
                add("local", "Modelo local", "error", "El último modelo no pudo cargarse: " + str(llama.status()["error"])[:200],
                    "Prueba otro modelo o menos contexto en Modelos.", "models", 1)
            else:
                add("local", "Modelo local", "info", "Hay motor, pero ningún modelo cargado.",
                    "Modelos → carga uno (el recomendado para tu equipo aparece arriba), o usa un proveedor.", "models", 1)

        # --- Proveedores
        async def providers_check():
            active = [p for p in cfg["providers"] if p.get("enabled") and (p.get("api_key") or
                                                                        str(p.get("base_url", "")).startswith("http://"))]
            if not active:
                add("providers", "Proveedores de IA", "warn" if not llama.ready else "info",
                    "No tienes ningún proveedor en la nube activo.",
                    "Ajustes → Proveedores → Añadir (OpenCode Go, OpenRouter, DeepSeek, Claude…).", "providers", 2)
                return

            async def one(p):
                r = await timed(list_models(p), 20)
                if isinstance(r, Exception):
                    add(f"prov-{p['id']}", p["name"], "error", "No conecta: " + why(r),
                        "Revisa la clave y la URL en Ajustes → Proveedores («Probar conexión»).", "providers", 2)
                else:
                    add(f"prov-{p['id']}", p["name"], "ok", f"Conectado: {len(r)} modelos disponibles", order=2)
            await asyncio.gather(*(one(p) for p in active))

        # --- Web
        async def web_check():
            r = await timed(web.search(cfg, "Wikipedia", 2), 15)
            if isinstance(r, Exception) or not r:
                add("web", "Búsqueda web", "warn", f"No funciona con {cfg['web_provider']}: " + (why(r) if isinstance(r, Exception) else "sin resultados"),
                    "Ajustes → General: cambia de buscador (Brave o Tavily son más fiables, con clave gratuita).", "general", 6)
            else:
                add("web", "Búsqueda web", "ok", f"Funciona ({cfg['web_provider']})", order=6)

        # --- Servidores MCP externos
        async def mcp_check():
            if not cfg["mcp_servers"]:
                return
            await timed(mcp_mgr.refresh(force=True), 45)
            for s in mcp_mgr.status():
                if s["ok"]:
                    add(f"mcp-{s['name']}", f"MCP · {s['name']}", "ok", f"{len(s['tools'])} herramientas", order=7)
                else:
                    add(f"mcp-{s['name']}", f"MCP · {s['name']}", "error", s.get("error") or "no arranca",
                        "Revisa la línea del servidor en Ajustes → Correo e integraciones.", "mail", 7)

        # --- Conexión con Claude Code (el propio /mcp)
        async def claude_check():
            async def probe():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://interno", timeout=10) as c:
                    r = await c.post("/mcp", headers={"Authorization": f"Bearer {cfg['token']}"},
                                     json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                    return r.json()["result"]["serverInfo"]["name"]
            r = await timed(probe(), 15)
            cmd = f"claude mcp add --transport http g3g3ai http://127.0.0.1:{cfg['port']}/mcp"
            if isinstance(r, Exception):
                add("claude", "Conexión con Claude Code", "error", "El servidor MCP no responde: " + why(r), order=8)
            else:
                add("claude", "Conexión con Claude Code", "ok", "Listo para usarse como subagente.",
                    "Si aún no lo has hecho, ejecuta una vez: " + cmd, "copy:" + cmd, 8)

        await asyncio.gather(local_check(), providers_check(), web_check(), mcp_check(), claude_check())

        # --- Carpetas y permisos (sin red)
        missing_w = [str(p) for p in cfg["write_roots"] or [] if not Path(os.path.expanduser(str(p))).is_dir()]
        if not cfg["write_roots"]:
            add("folders", "Carpetas de trabajo", "warn", "La IA no puede crear ni modificar archivos en ninguna carpeta.",
                "Ajustes → Agente y permisos → «Carpetas que la IA puede modificar».", "agent", 3)
        elif missing_w:
            add("folders", "Carpetas de trabajo", "warn", "No existen: " + ", ".join(missing_w),
                "Créalas o quítalas en Ajustes → Agente y permisos.", "agent", 3)
        else:
            add("folders", "Carpetas de trabajo", "ok", "La IA puede trabajar en: " + ", ".join(str(p) for p in cfg["write_roots"]), order=3)
        cmd_mode = cfg["ai_commands"] or "off"
        if cmd_mode == "off":
            add("commands", "Comandos", "info", "La IA no puede ejecutar comandos (desactivado).",
                "Actívalo en Ajustes → Agente y permisos si quieres que ejecute scripts o pruebas.", "agent", 4)
        elif not sandbox.available(cfg) and not cfg["commands_trusted"]:
            add("commands", "Comandos", "info", "Te pedirá permiso para cada comando (en este sistema no hay aislamiento).",
                "Si te resulta pesado, activa «Confiar en mis carpetas» (python, pytest, git de lectura… sin preguntar).", "agent", 4)
        else:
            add("commands", "Comandos", "ok", "Aislados" if sandbox.available(cfg) else "Comandos de desarrollo habituales sin preguntar", order=4)

        # --- Correo
        if not cfg["mail_enabled"]:
            profs = await asyncio.to_thread(thunderbird_profiles)
            add("mail", "Correo", "skip", "Desactivado" + (" (Thunderbird detectado)" if profs else ""),
                "Actívalo en Ajustes → Correo e integraciones si quieres que la IA busque en tu correo.", "mail", 5)
        else:
            st = mail_index.stats()
            srcs = await asyncio.to_thread(mail_sources, cfg)
            if not srcs:
                add("mail", "Correo", "error", "No encuentro el correo: ni perfil de Thunderbird ni rutas extra.",
                    "Añade la carpeta del correo en Ajustes → Correo e integraciones.", "mail", 5)
            elif st["error"]:
                add("mail", "Correo", "error", "Error al indexar: " + st["error"], "Pulsa «Reconstruir» en Ajustes → Correo.", "mail", 5)
            elif st["running"]:
                add("mail", "Correo", "info", f"Indexando… {st['files_done']}/{st['files_total']} buzones, {st['messages']} mensajes", order=5)
            elif not st["messages"]:
                add("mail", "Correo", "warn", "El índice está vacío.", "Ajustes → Correo → «Actualizar índice».", "mail", 5)
            else:
                add("mail", "Correo", "ok", f"{st['messages']} mensajes indexados", order=5)

        ex = extras.summary()
        if ex["dir"]:
            have = [n for k, n in (("llama_cpu", "motor local (CPU)"), ("llama_vulkan", "motor local (gráfica)"), ("sd", "imágenes"),
                                   ("python", "Python"), ("git", "Git")) if ex[k]]
            add("extras", "Edición completa", "ok", "Incluye: " + ", ".join(have), order=9)
        # --- Disco y equipo
        try:
            free = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else Path.home()).free / 1024 ** 3
            add("disk", "Espacio en disco", "warn" if free < 5 else "ok", f"{free:.0f} GB libres",
                "Libera espacio: los modelos locales ocupan entre 2 y 20 GB." if free < 5 else "", order=9)
        except OSError:
            pass
        try:
            if "hw" not in hw_cache:
                hw_cache["hw"] = await asyncio.to_thread(hardware.detect)
            rec = hardware.recommend(hw_cache["hw"])
            add("hardware", "Tu equipo", "info", f"{rec['summary']['cpu']} · {rec['summary']['ram_gb']} GB RAM · "
                f"modelo local recomendado: {rec['main']['tier']}", order=10)
        except Exception:  # noqa: BLE001
            pass
        checks.sort(key=lambda c: (c["order"], c["title"]))
        summary = {k: sum(1 for c in checks if c["status"] == k) for k in ("ok", "warn", "error", "info", "skip")}
        return {"checks": checks, "summary": summary}

    @app.get("/api/mcp")
    async def mcp_status(refresh: bool = True):
        if refresh:
            await mcp_mgr.refresh(force=True)
        else:
            mcp_mgr._sync_servers()
        return {"servers": mcp_mgr.status()}

    @app.get("/api/usage")
    async def usage(days: int = 0):
        """Tokens y coste estimado: este mes por defecto, o los últimos `days` días."""
        since = time.time() - days * 86400 if days else None
        return await asyncio.to_thread(costs.summary, db, cfg, since)

    @app.get("/api/conversations/{cid}/context")
    async def conversation_context(cid: str, provider: str = LOCAL_PROVIDER):
        conv = db.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Conversación no encontrada")
        return builder.usage(conv, provider, int(cfg["max_tokens"] or 2048))

    @app.post("/api/conversations/{cid}/compact")
    async def conversation_compact(cid: str, body: dict):
        """/compact: resume la conversación ahora (conserva sólo el último intercambio) y deja el resumen guardado."""
        conv = db.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Conversación no encontrada")
        pid, model = body.get("provider") or LOCAL_PROVIDER, body.get("model") or "local"
        before = builder.usage(conv, pid, int(cfg["max_tokens"] or 2048))["used"]
        try:
            async for _ in builder.build(conv, pid, model, "", int(cfg["max_tokens"] or 2048), force=True):
                pass
        except (ProviderError, httpx.HTTPError, RuntimeError) as e:
            raise HTTPException(502, f"No se pudo resumir: {e}")
        conv = db.get_conversation(cid)
        return {"before": before, **builder.usage(conv, pid, int(cfg["max_tokens"] or 2048))}

    @app.get("/api/conversations/{cid}/checkpoints")
    async def conversation_checkpoints(cid: str):
        return {"checkpoints": [{"id": c["id"], "files": [f["path"] for f in c["files"]]}
                                for c in UndoJournal(cid).checkpoints()]}

    @app.post("/api/conversations/{cid}/restore")
    async def conversation_restore(cid: str, body: dict):
        """Vuelve los archivos a como estaban antes del mensaje `id`; con truncate también borra ese mensaje y los siguientes."""
        try:
            mid = int(body.get("id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Falta «id» del mensaje")
        res = await asyncio.to_thread(UndoJournal(cid).restore_to, mid)
        session_state.get(cid, {}).get("read", {}).clear()
        if body.get("truncate"):
            db.delete_messages_from(cid, mid)
        return res

    @app.get("/api/conversations/{cid}/changes")
    async def conversation_changes(cid: str):
        """Archivos que la IA ha modificado o creado en esta conversación (se pueden deshacer)."""
        return {"files": UndoJournal(cid).changes()}

    @app.get("/api/conversations/{cid}/changes/diff")
    async def conversation_change_diff(cid: str, path: str):
        return {"diff": await asyncio.to_thread(UndoJournal(cid).diff, path)}

    @app.post("/api/conversations/{cid}/undo_file")
    async def conversation_undo_file(cid: str, body: dict):
        res = await asyncio.to_thread(UndoJournal(cid).undo_one, body.get("path", ""))
        session_state.get(cid, {}).get("read", {}).pop(body.get("path", ""), None)
        return res

    @app.post("/api/conversations/{cid}/undo")
    async def conversation_undo(cid: str):
        res = await asyncio.to_thread(UndoJournal(cid).undo_all)
        session_state.get(cid, {}).get("read", {}).clear()  # los archivos han cambiado: hay que releerlos
        return res

    @app.post("/api/conversations/{cid}/fork")
    async def fork_conversation(cid: str, body: dict):
        """Editar o regenerar sin perder lo anterior: el final se guarda como rama alternativa."""
        db.archive_from(cid, int(body["message_id"]))
        session_state.pop(cid, None)
        return db.get_conversation(cid)

    @app.post("/api/conversations/{cid}/branch")
    async def switch_conversation_branch(cid: str, body: dict):
        db.switch_branch(cid, int(body["position"]), -1 if int(body.get("step", 1)) < 0 else 1)
        session_state.pop(cid, None)
        return db.get_conversation(cid)

    @app.delete("/api/conversations/{cid}/messages/{mid}")
    async def truncate_conversation(cid: str, mid: int):
        db.delete_messages_from(cid, mid)
        return db.get_conversation(cid)

    # --- Chat ---------------------------------------------------------------------
    def expand_attachments(paths: list[str]) -> tuple[str, list[dict]]:
        """Texto de los adjuntos + metadatos. Imágenes y PDF escaneados se envían aparte (context.py)."""
        parts, meta = [], []
        for p in paths:
            try:
                path = files.resolve(p)
                if not path.is_file():
                    raise FileAccessError(f"No es un archivo: {path}")
                kind = D.kind_of(path)
                if kind == "image":
                    meta.append({"name": path.name, "path": str(path), "kind": "image"})
                    continue
                if kind == "document":
                    text = D.extract_text(path)
                    if not text.strip() and path.suffix.lower() == ".pdf":
                        meta.append({"name": path.name, "path": str(path), "kind": "pdf_scan"})
                        continue
                    parts.append(f"Documento adjunto `{path}`:\n```\n{text}\n```")
                    meta.append({"name": path.name, "path": str(path), "kind": "document"})
                    continue
                f = files.read_text(str(path), 60_000)
            except (FileAccessError, D.DocumentError) as e:
                raise HTTPException(400, str(e)) from e
            note = "\n[... truncado ...]" if f["truncated"] else ""
            parts.append(f"Archivo adjunto `{f['path']}`:\n```\n{f['content']}{note}\n```")
            meta.append({"name": f["name"], "path": f["path"], "kind": "text"})
        return "\n\n".join(parts), meta

    def provider_available(pid: str) -> bool:
        if pid == LOCAL_PROVIDER:
            return llama.ready
        p = cfg.provider(pid)
        if not p or not p.get("enabled"):
            return False
        return bool(p.get("api_key")) or p.get("base_url", "").startswith("http://")

    async def local_complete(prompt: str) -> str:
        p = provider_for(LOCAL_PROVIDER)
        try:
            return await complete(p, "local", prompt, max_tokens=cfg["max_tokens"])
        except (ProviderError, httpx.HTTPError) as e:
            return f"Error del modelo local: {e}"

    builder = HistoryBuilder(db, cfg, llama, provider_for, provider_available, complete_messages)

    IMAGE_GGUF = re.compile(r"(^|[-_.])(sd|sdxl|flux|stable-diffusion|z-image|qwen-image|wan)([-_.\d]|$)", re.I)

    def pick_local_model() -> str | None:
        """Modelo local a cargar sin preguntar: el último usado o, si no, el descargado más reciente (no de imágenes)."""
        last = cfg["last_model"]
        if last and Path(last).is_file():
            return last
        cands = [m for m in hub.local_models() if not m["mmproj"] and not IMAGE_GGUF.search(m["name"])]
        cands.sort(key=lambda m: Path(m["path"]).stat().st_mtime, reverse=True)
        return cands[0]["path"] if cands else None

    async def ensure_local_loaded(path: str | None):
        """Carga el modelo local (si hace falta) informando del avance; devuelve un error o None."""
        if not llama.ready and llama.state != "loading" and path:
            await llama.load(path)
        name = Path(llama.model_path or path or "").name.removesuffix(".gguf") or "el modelo local"
        t0 = time.time()
        while llama.state == "loading":
            yield {"type": "status", "text": f"⏳ Cargando {name}… {int(time.time() - t0)} s (sólo la primera vez)"}
            await asyncio.sleep(1)
        if not llama.ready:
            yield {"type": "error", "message": f"No se pudo cargar {name}: {(llama.error or 'error desconocido')[:400]}"}

    @app.post("/api/chat")
    async def chat(body: dict):
        autoload = None
        cid = body.get("conversation_id")
        pid = body.get("provider") or LOCAL_PROVIDER
        model = body.get("model") or "local"
        text = (body.get("message") or "").strip()
        attachments = body.get("attachments") or []
        attach_text, attach_meta = await asyncio.to_thread(expand_attachments, attachments)   # el OCR puede tardar
        if not text and not attach_text and not body.get("continue"):
            raise HTTPException(400, "Mensaje vacío")
        agent = bool(body.get("use_tools"))
        direct_image = None
        m_img = re.match(r"^/(imagen|img|image)\s+(.+)", text, re.S | re.I)
        if m_img:
            if not cfg["image_provider"]:
                raise HTTPException(409, "La generación de imágenes está desactivada. Configúrala en Ajustes → Imágenes.")
            direct_image = m_img.group(2).strip()
        use_web = bool(body.get("use_web"))
        perm_mode = body.get("mode") if body.get("mode") in ("normal", "plan", "edits") else "normal"

        conv = db.get_conversation(cid) if cid else None
        last_user_id = next((m["id"] for m in reversed((conv or {}).get("messages", [])) if m["role"] == "user"), None)
        # Último mensaje del usuario (para decidir la ruta al regenerar)
        last_user = text or next((m["content"] for m in reversed((conv or {}).get("messages", []))
                                  if m["role"] == "user"), "")
        if direct_image is not None:
            candidates = []
        elif pid == AUTO_PROVIDER:
            candidates = router.plan(cfg, last_user, bool(attachments), agent or use_web, provider_available)
            if not candidates:
                raise HTTPException(409, "Modo Auto: no hay ningún modelo disponible. Carga un modelo local "
                                         "o configura un proveedor API (Ajustes → Modo Auto).")
        else:
            provider_for(pid)
            if pid == LOCAL_PROVIDER and not llama.ready and llama.state != "loading":
                autoload = pick_local_model()
                if not autoload:
                    raise HTTPException(409, "No tienes ningún modelo local descargado. En «Modelos» puedes descargar "
                                             "el recomendado para tu equipo con un clic, o elige un modelo por API.")
            candidates = [(pid, model, None)]

        turn_mid = None
        if not conv:
            proj_id = body.get("project_id") if body.get("project_id") and db.get_project(body["project_id"]) else None
            conv = db.create_conversation(provider=pid, model=model, system=body.get("system"), project_id=proj_id)
            cid = conv["id"]
        if text or attach_text:
            meta = ({"attachments": attach_meta, "expanded": f"{attach_text}\n\n{text}".strip() or text}
                    if attach_meta else None)
            turn_mid = db.add_message(cid, "user", text, meta=meta)
            if conv["title"] == "Nueva conversación":
                title = text or (attach_meta[0]["name"] if attach_meta else "Conversación")
                db.update_conversation(cid, title=title[:60])
        db.update_conversation(cid, provider=pid, model=model)
        if "system" in body:
            db.update_conversation(cid, system=body.get("system"))
        if "workdir" in body:
            db.update_conversation(cid, workdir=(body.get("workdir") or None))
        conv = db.get_conversation(cid)

        unattended = bool(body.get("unattended"))
        project = db.get_project(conv["project_id"]) if conv.get("project_id") else None
        base_system = conv.get("system") if conv.get("system") is not None else cfg["default_system_prompt"]
        opts = {"temperature": body.get("temperature", cfg["temperature"]),
                "max_tokens": body.get("max_tokens", cfg["max_tokens"])}

        def memory_for(chosen_pid: str) -> bool:
            if not cfg["memory_enabled"] or body.get("incognito"):
                return False
            return chosen_pid == LOCAL_PROVIDER or bool(cfg["memory_api"])

        async def image_gen(prompt: str, size=None):
            return await images.generate(cfg, provider_for, prompt, size)

        def make_ctx(chosen_pid: str, chosen_model: str = ""):
            mem = memory if (memory_for(chosen_pid) and cfg["memory_auto"]) else None
            img = image_gen if cfg["image_provider"] else None
            docs = (cfg["ai_write"] or "off") != "off" and bool(files.write_roots)   # crear Word/Excel/PDF siempre
            if not (agent or use_web or mem or img or docs or not unattended):
                return None
            delegate = local_complete if (agent and chosen_pid != LOCAL_PROVIDER and llama.ready) else None
            tc = ToolContext(files, cfg, delegate, agent=agent, web=use_web,
                             session_allow=session_allow.setdefault(cid, set()), memory=mem, source=cid,
                             image_gen=img, state=state_for(cid, conv), perm_mode=perm_mode,
                             workdir=conv.get("workdir") or None, checkpoint=turn_mid or last_user_id)
            tc.mcp = mcp_mgr if (agent and mcp_mgr.map) else None
            tc.mail = mail_index if cfg["mail_enabled"] else None
            tc.tasks = task_store
            tc.cloud = chosen_pid != LOCAL_PROVIDER
            tc.compact_specs = chosen_pid == LOCAL_PROVIDER
            recent = [m["content"] or "" for m in (conv.get("messages") or []) if m["role"] == "user"][-3:]
            tc.focus = " ".join(recent + [text or ""])[-4000:]
            tc.unattended = unattended
            tc.task_level = body.get("task_level") if unattended else None
            tc.profile = profile_for(chosen_pid, (llama.status()["model"] or "") if chosen_pid == LOCAL_PROVIDER else chosen_model,
                                     chosen_pid == LOCAL_PROVIDER,
                                     cfg["agent_profile"] or "auto")
            if agent:
                async def run_subagent(task: str, write: bool = False, _pid=chosen_pid, _model=chosen_model, _tc=tc) -> str:
                    copy = None
                    try:
                        if write:
                            src = _tc.workdir()
                            try:
                                copy, manifest = await asyncio.to_thread(subagent.make_copy, src)
                            except subagent.SubagentError as e:
                                return f"Error: {e}"
                            sub = ToolContext(subagent.ScopedFiles(cfg, copy), cfg, None, agent=True, web=False, memory=None,
                                              source=None, state={}, perm_mode="normal", workdir=str(copy))
                            sub.auto_all = True
                            system = profiles.SUBAGENT_WRITE_PROMPT + "\n\n" + sub.system_hint()
                        else:
                            sub = ToolContext(files, cfg, None, agent=True, web=use_web, memory=None, source=None, state={},
                                              perm_mode="plan", workdir=conv.get("workdir") or None)
                            system = profiles.SUBAGENT_PROMPT + "\n\n" + sub.system_hint()
                        sub.profile, sub.result_limit = _tc.profile, _tc.result_limit
                        msgs = [{"role": "system", "content": system}, {"role": "user", "content": task}]
                        text = ""
                        async for ev in chat_stream(provider_for(_pid), _model, msgs, opts, sub):
                            if ev["type"] == "content":
                                text += ev["text"]
                            elif ev["type"] == "retract" and text.endswith(ev["text"]):
                                text = text[: len(text) - len(ev["text"])]
                        report = text.strip()[-8000:] or "(el ayudante no devolvió nada)"
                        if not write:
                            return report
                        patch = await asyncio.to_thread(subagent.collect_patch, src, copy, manifest)
                        if not patch["changes"]:
                            return f"El ayudante no cambió ningún archivo.\n\n{report}"
                        pid_ = subagent.new_patch_id()
                        _tc.state.setdefault("patches", {})[pid_] = {"root": str(src), "changes": patch["changes"],
                                                                      "diff": patch["diff"]}
                        extra = f"\n(No se compararon por no ser texto: {', '.join(patch['skipped'])})" if patch["skipped"] else ""
                        return (f"Informe del ayudante:\n{report}\n\nPropuesta {pid_} — {len(patch['changes'])} archivo(s):\n"
                                f"{patch['diff'][:12000]}{extra}\n\nPara aplicarla usa apply_patch con id=\"{pid_}\".")
                    finally:
                        if copy is not None:
                            await asyncio.to_thread(shutil.rmtree, copy, True)
                tc.subagent = run_subagent
            tc.diagnostics = lambda _pid=chosen_pid: diagnostics(local_in_use=_pid == LOCAL_PROVIDER)
            team_cfg = cfg["team"] or {}
            if team_cfg.get("enabled") and team_cfg.get("members"):
                tc.team = team_cfg

                async def run_member(m: dict, task: str) -> str:
                    mpid, mmodel = m["model"].split("::", 1)
                    if mpid == LOCAL_PROVIDER and not llama.ready:
                        return f"{m['name']} no puede trabajar: su modelo es el local y no hay ninguno cargado."
                    if mpid != LOCAL_PROVIDER and not provider_available(mpid):
                        return f"{m['name']} no puede trabajar: el proveedor «{mpid}» no está activo o no tiene clave."
                    sub = None
                    if m["tools"] == "read":
                        sub = ToolContext(files, cfg, None, agent=True, web=True, memory=None, source=None, state={},
                                          perm_mode="plan", workdir=conv.get("workdir") or None)
                        sub.mail = mail_index if cfg["mail_enabled"] else None
                        sub.unattended = True
                        sub.profile = profile_for(mpid, mmodel, mpid == LOCAL_PROVIDER, cfg["agent_profile"] or "auto")
                        sub.compact_specs = mpid == LOCAL_PROVIDER
                    system = team.member_prompt(m) + ("\n\n" + sub.system_hint() if sub else "")
                    mopts = dict(opts)
                    if mpid == LOCAL_PROVIDER:
                        mopts.update({"n_ctx": int((llama.params or {}).get("ctx") or 8192), "thinking": bool(cfg["local_thinking"])})
                    text = ""
                    try:
                        async for ev in chat_stream(provider_for(mpid), mmodel, [{"role": "system", "content": system},
                                                                                 {"role": "user", "content": task}], mopts, sub):
                            if ev["type"] == "content":
                                text += ev["text"]
                            elif ev["type"] == "retract" and text.endswith(ev["text"]):
                                text = text[: len(text) - len(ev["text"])]
                    except (ProviderError, httpx.HTTPError, RuntimeError) as e:
                        return f"{m['name']} falló: {e}"
                    return f"Informe de {m['name']} ({mmodel}):\n{text.strip()[-10000:] or '(no devolvió nada)'}"
                tc.team_runner = run_member
            if chosen_pid == LOCAL_PROVIDER:  # ~1/4 del contexto (en tokens ≈ 4 caracteres) como máximo por resultado
                n_ctx = int((llama.params or {}).get("ctx") or 8192)
                tc.result_limit = max(3000, n_ctx)
            return tc

        async def gen():
            content, reasoning, trace, stats, route = "", "", [], {}, None
            t_start, gen_log = time.time(), []     # registro de la respuesta (botón «Detalles»): qué pasó y cuándo

            def log_note(text: str):
                if len(gen_log) < 200:
                    gen_log.append({"t": round(time.time() - t_start, 1), "text": str(text)[:300]})
            made: list[str] = []
            out_files: list[str] = []
            todos: list = []
            finish = None
            used_in = used_out = 0
            providers_mod.SESSION.set(cid)      # cabecera de sesión de OpenCode Go (también en títulos y resúmenes)
            yield sse({"type": "start", "conversation_id": cid})
            if pid == LOCAL_PROVIDER and not llama.ready:   # se escribió sin modelo cargado: se carga solo
                failed = False
                async for ev in ensure_local_loaded(autoload):
                    failed = failed or ev["type"] == "error"
                    yield sse(ev)
                if failed:
                    yield sse({"type": "done"})
                    return
            if direct_image is not None:  # «/imagen …»: sin pasar por el modelo de texto
                yield sse({"type": "status", "text": "🎨 Generando imagen…"})
                try:
                    path = await image_gen(direct_image)
                    made.append(str(path))
                    yield sse({"type": "image", "path": str(path)})
                    content = "Imagen generada."
                except images.ImageError as e:
                    content = f"No se pudo generar la imagen: {e}"
                yield sse({"type": "content", "text": content})
                meta = {"provider": "imagen", "model": cfg["image_model"] or cfg["image_provider"], "images": made}
                stats["message_id"] = db.add_message(cid, "assistant", content, None, meta)
                yield sse({"type": "done", **stats})
                return
            if agent and cfg["mcp_servers"]:
                try:
                    await asyncio.wait_for(mcp_mgr.refresh(), 45)
                except asyncio.TimeoutError:
                    pass
            try:
                for i, (cpid, cmodel, why) in enumerate(candidates):
                    p = provider_for(cpid)
                    shown = (llama.status()["model"] or "local") if cpid == LOCAL_PROVIDER else cmodel
                    route = {"provider": cpid, "model": shown, "reason": why}
                    log_note(f"Modelo: {shown} ({'local' if cpid == LOCAL_PROVIDER else cpid})" + (f" — {why}" if why else ""))
                    if why:
                        yield sse({"type": "route", **route})
                    ctx = make_ctx(cpid, cmodel)
                    mem_text = memory.prompt() if memory_for(cpid) else ""
                    no_agent = "" if (ctx and ctx.agent) else NO_AGENT_NOTE
                    proj_text = ""
                    if project:
                        # Presupuesto: ~30 % del contexto en los modelos locales; 80 000 caracteres en las APIs
                        n_ctx = int((llama.params or {}).get("ctx") or 8192)
                        budget = int(n_ctx * 0.3 * 3) if cpid == LOCAL_PROVIDER else 80_000
                        proj_text = await asyncio.to_thread(projects.context, project, files, budget)
                    system = "\n\n".join(x for x in (base_system, ARTIFACT_NOTE, APP_FEATURES, proj_text, mem_text, ctx.system_hint() if ctx else "", no_agent) if x)
                    try:
                        history = []
                        async for ev in builder.build(conv, cpid, cmodel, system, opts["max_tokens"] or 2048):
                            if ev["type"] == "_history":
                                history = ev["messages"]
                            else:
                                yield sse(ev)
                        if (cpid == LOCAL_PROVIDER and use_web and ctx and "web_search" in ctx.names() and text
                                and not body.get("continue") and len(text) > 10 and history and history[-1]["role"] == "user"):
                            # Los modelos locales pequeños a menudo no buscan aunque la búsqueda esté activada (o piden
                            # al usuario qué buscar): se busca ya con la pregunta y se les dan los resultados.
                            sink: list[str] = []
                            async for ev in tool_events(ctx, "web_search", {"query": text[:200]}, sink):
                                if ev["type"] in ("tool_call", "tool_result"):
                                    trace.append(ev)
                                yield sse(ev)
                            if sink and sink[0].strip():
                                note = ("\n\n[Búsqueda web hecha automáticamente con esta pregunta. Respóndela con estos "
                                        "resultados y cita las fuentes; si no bastan, busca otra cosa o abre una página con "
                                        "fetch_url:\n" + sink[0][:6000] + "]")
                                last = history[-1]
                                if isinstance(last["content"], str):
                                    last["content"] += note
                                else:
                                    last["content"] = list(last["content"]) + [{"type": "text", "text": note}]
                        msgs = ([{"role": "system", "content": system}] if system else []) + history
                        run_opts = opts
                        if cpid == LOCAL_PROVIDER:  # ajustes propios de los modelos locales
                            run_opts = {**opts, "n_ctx": int((llama.params or {}).get("ctx") or 8192),
                                        "thinking": bool(cfg["local_thinking"])}
                            if ctx is not None and "temperature" not in body:
                                run_opts["temperature"] = min(float(opts.get("temperature") or 0.7),
                                                              float(cfg["agent_temperature"] or 0.3))
                        async for ev in with_keepalive(chat_stream(p, cmodel, msgs, run_opts, ctx)):
                            if ev is None:  # latido: evita que proxies/túneles cierren una conexión en silencio
                                yield ": ping\n\n"
                                continue
                            if ev["type"] == "usage":
                                used_in += ev["input"] or 0
                                used_out += ev["output"] or 0
                                continue
                            if ev["type"] == "finish":
                                finish = ev["reason"]
                            elif ev["type"] == "retract":  # el modelo había escrito una llamada como texto
                                if content.endswith(ev["text"]):
                                    content = content[: len(content) - len(ev["text"])]
                            elif ev["type"] == "todos":
                                todos = ev["items"]
                            elif ev["type"] == "content":
                                content += ev["text"]
                            elif ev["type"] == "reasoning":
                                reasoning += ev["text"]
                            elif ev["type"] in ("tool_call", "tool_result"):
                                trace.append(ev)
                            elif ev["type"] == "image":
                                made.append(ev["path"])
                            elif ev["type"] == "file":
                                out_files.append(ev["path"])
                            elif ev["type"] == "stats":
                                stats.update({k: v for k, v in ev.items() if v is not None and k != "type"})
                            if ev["type"] == "status":
                                log_note(ev["text"])
                            elif ev["type"] == "tool_call":
                                log_note("Herramienta: " + str(ev.get("name")))
                            elif ev["type"] == "tool_result" and str(ev.get("result", "")).startswith(("Error", "Denegado", "El usuario")):
                                log_note(f"{ev.get('name')} → {str(ev.get('result'))[:160]}")
                            elif ev["type"] == "retract":
                                log_note("Se retiró texto del modelo (llamada escrita como texto o respuesta descontrolada)")
                            elif ev["type"] == "approval":
                                log_note("Pide permiso: " + str(ev.get("name")))
                            yield sse(ev)
                        log_note("Respuesta terminada" + (f" ({finish})" if finish and finish != "stop" else ""))
                        break
                    except (ProviderError, httpx.HTTPError, RuntimeError) as e:
                        msg = str(e) or type(e).__name__
                        log_note("Error: " + msg)
                        if content or trace or i == len(candidates) - 1:
                            yield sse({"type": "error", "message": msg})
                            break
                        yield sse({"type": "route_fallback", "message": f"{shown}: {msg}"})
            finally:
                if content or reasoning or trace or made:
                    meta = {"provider": route["provider"] if route else pid,
                            "model": route["model"] if route else model,
                            "route": route.get("reason") if route else None,
                            "stats": stats, "tools": trace or None, "images": made or None,
                            "files": out_files or None, "todos": todos or None, "mode": perm_mode,
                            "finish": finish, "log": gen_log or None, "elapsed": round(time.time() - t_start, 1),
                            "usage": ({"in": used_in, "out": used_out,
                                       "cost": costs.cost_of(cfg, route["provider"] if route else pid,
                                                             route["model"] if route else model, used_in, used_out)}
                                      if (used_in or used_out) else None)}
                    # el modelo a veces imita el registro automático del historial: no se guarda como texto suyo
                    content = re.sub(r"\s*<registro_de_herramientas>.*?(?:</registro_de_herramientas>|$)", "", content, flags=re.S).rstrip()
                    stats["message_id"] = db.add_message(cid, "assistant", content, reasoning or None, meta)
            if cfg["monthly_budget_usd"]:
                s = await asyncio.to_thread(costs.summary, db, cfg)
                if s["budget_pct"] is not None and s["budget_pct"] >= 80:
                    yield sse({"type": "budget", "pct": s["budget_pct"], "cost": round(s["total"]["cost"], 2),
                               "limit": s["budget"]})
            yield sse({"type": "done", **stats})

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # --- Memoria -------------------------------------------------------------------
    def mem_call(fn, *a):
        try:
            return fn(*a)
        except MemoryRejected as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/memory")
    async def memory_list():
        return memory.list()

    @app.post("/api/memory")
    async def memory_add(body: dict):
        return mem_call(memory.add, body.get("content", ""), "manual")

    @app.put("/api/memory/{mid}")
    async def memory_update(mid: int, body: dict):
        return mem_call(memory.update, mid, body.get("content", ""))

    @app.delete("/api/memory/{mid}")
    async def memory_delete(mid: int):
        return {"ok": memory.delete(mid)}

    @app.delete("/api/memory")
    async def memory_clear():
        memory.clear()
        return {"ok": True}

    # --- Sincronización entre equipos -----------------------------------------------------------
    @app.post("/api/sync/exchange")
    async def sync_exchange(request: Request):
        try:
            data = await asyncio.to_thread(sync.handle, await request.body())
        except SyncError as e:
            raise HTTPException(403, str(e)) from e
        return Response(content=data, media_type="application/octet-stream")

    @app.get("/api/sync/status")
    async def sync_status():
        return {"device_id": cfg["device_id"], "has_key": bool(cfg["sync_key"]),
                "peers": [{k: p.get(k) for k in ("url", "name", "last_sent")} for p in cfg["sync_peers"] or []],
                "status": sync.status, "interval": SYNC_INTERVAL}

    @app.get("/api/sync/key")
    async def sync_key():
        return {"key": cfg["sync_key"]}

    @app.post("/api/sync/new-key")
    async def sync_new_key():
        key = new_sync_key()
        cfg.set("sync_key", key)
        return {"key": key}

    @app.post("/api/sync/now")
    async def sync_now():
        return await sync.sync_all()

    @app.post("/api/chat/approve")
    async def approve(body: dict):
        answer = body.get("answer") or ("yes" if body.get("approved") else "no")
        if not resolve_approval(str(body.get("id")), answer):
            raise HTTPException(404, "Esta solicitud ya no está pendiente")
        return {"ok": True}

    # --- Motor llama.cpp precompilado -------------------------------------------------
    def engine_of(kind: str) -> EngineInstaller:
        if kind not in engines:
            raise HTTPException(404, "Motor desconocido")
        return engines[kind]

    @app.get("/api/engine/assets")
    async def engine_assets(kind: str = "llama"):
        try:
            return await engine_of(kind).assets()
        except httpx.HTTPError as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            why = ("GitHub ha limitado las consultas desde tu conexión; vuelve a intentarlo en unos minutos"
                   if code in (403, 429) else "no hay conexión con GitHub")
            raise HTTPException(502, f"No se pudo comprobar qué versión descargar: {why}.") from e

    @app.post("/api/engine/install")
    async def engine_install(body: dict):
        return engine_of(body.get("kind", "llama")).start(body["url"], body["name"])

    @app.get("/api/engine/status")
    async def engine_status(kind: str = "llama"):
        return engine_of(kind).state

    # --- Hardware y recomendación --------------------------------------------------------------
    hw_cache: dict = {}

    @app.get("/api/hardware")
    async def hardware_info(refresh: bool = False):
        if refresh or "hw" not in hw_cache:
            hw_cache["hw"] = await asyncio.to_thread(hardware.detect)
        hw = hw_cache["hw"]
        rec = hardware.recommend(hw)
        local = [m for m in hub.local_models() if not m["mmproj"]]
        for pk in rec.get("picks", []):      # ¿ya está descargado?
            pk["path"] = next((m["path"] for m in local if m["repo"] == pk["repo"]), None)
        return {"hardware": hw, "recommendation": rec}

    QUANT_PREF = ["Q4_K_M", "Q4_K_S", "IQ4_XS", "Q4_0", "Q5_K_M", "Q3_K_M"]

    @app.post("/api/models/quick")
    async def models_quick(body: dict):
        """«Descargar y usar»: elige el archivo Q4_K_M (y el proyector de visión si hace falta) y lo descarga."""
        repo = body.get("repo", "")
        if repo not in {p[1] for p in hardware.PICKS.values()} and not body.get("any"):
            raise HTTPException(400, "Modelo no reconocido")
        try:
            groups = await hub.files(repo)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"No se pudo consultar Hugging Face: {e}") from e
        models = [g for g in groups if not g["mmproj"]]
        main = next((g for q in QUANT_PREF for g in models if (g["quant"] or "").upper() == q), None) or (models[0] if models else None)
        if not main:
            raise HTTPException(404, "Ese repositorio no tiene modelos GGUF")
        files = list(main["files"])
        if body.get("vision"):
            proj = sorted([g for g in groups if g["mmproj"]], key=lambda g: ("f16" not in g["name"].lower(), g["size"]))
            if proj:
                files += proj[0]["files"]
        dest = hub.models_dir / repo.replace("/", "__") / Path(main["files"][0]).name
        if all((hub.models_dir / repo.replace("/", "__") / Path(f).name).exists() for f in files):
            return {"id": None, "status": "done", "dest": str(dest)}
        d = hub.start(repo, files)
        d["dest"] = str(dest)
        return d

    @app.post("/api/hardware/apply")
    async def hardware_apply():
        if "hw" not in hw_cache:
            hw_cache["hw"] = await asyncio.to_thread(hardware.detect)
        rec = hardware.recommend(hw_cache["hw"])
        cfg.update_public(rec["settings"])
        return {"applied": rec["settings"]}

    # --- Ollama ---------------------------------------------------------------------------------
    olm = ollama.OllamaManager(cfg)

    @app.get("/api/ollama")
    async def ollama_info():
        st = await ollama.status(cfg)
        if "hw" not in hw_cache:
            hw_cache["hw"] = await asyncio.to_thread(hardware.detect)
        tier = hardware.recommend(hw_cache["hw"])["main"]["tier"]
        prov = cfg.provider("ollama") or {}
        return {**st, "job": olm.job, "suggestions": ollama.suggestions_for(tier), "tier": tier,
                "provider_enabled": bool(prov.get("enabled"))}

    @app.post("/api/ollama/install")
    async def ollama_install():
        return olm.install()

    @app.post("/api/ollama/start")
    async def ollama_start():
        try:
            return olm.start()
        except (RuntimeError, OSError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/ollama/pull")
    async def ollama_pull(body: dict):
        name = str(body.get("name", "")).strip()
        if not re.fullmatch(r"[\w.\-/:]+", name):
            raise HTTPException(400, "Nombre de modelo no válido (p.ej. qwen3:4b)")
        return olm.pull(name)

    @app.delete("/api/ollama/models")
    async def ollama_delete(name: str):
        try:
            await olm.delete(name)
        except (RuntimeError, httpx.HTTPError) as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    @app.post("/api/ollama/enable")
    async def ollama_enable(body: dict):
        """Activa (o desactiva) el proveedor «Ollama (local)» en el selector de modelos."""
        provs = cfg["providers"]
        prov = next((p for p in provs if p.get("id") == "ollama"), None)
        if prov is None:
            prov = dict(id="ollama", name="Ollama (local)", type="openai", api_key="")
            provs.insert(0, prov)
        prov["base_url"] = ollama.base_url(cfg) + "/v1"
        prov["enabled"] = bool(body.get("enabled", True))
        cfg.update_public({"providers": provs})
        return {"enabled": prov["enabled"]}

    # --- Herramientas de programación ------------------------------------------------------------
    devinst = devtools.DevEnvInstaller(cfg)

    @app.get("/api/devtools")
    async def devtools_info(refresh: bool = False):
        info = await asyncio.to_thread(devtools.detect, cfg, refresh)
        return {"tools": info, "installable": list(devtools.WINGET) if sys.platform == "win32" else [],
                "devenv": str(devtools.DEVENV), "state": devinst.state}

    @app.post("/api/devtools/install")
    async def devtools_install(body: dict):
        return devinst.start(str(body.get("what", "")))

    # --- Imágenes -----------------------------------------------------------------------
    @app.get("/api/images/status")
    async def images_status():
        return {"provider": cfg["image_provider"], "model": cfg["image_model"],
                "sd_binary": images.find_sd(cfg), "sd_model": cfg["sd_model"],
                "dir": str(images.output_dir(cfg))}

    @app.post("/api/images/generate")
    async def images_generate(body: dict):
        try:
            path = await images.generate(cfg, provider_for, body.get("prompt", ""), body.get("size"))
        except images.ImageError as e:
            raise HTTPException(400, str(e)) from e
        return {"path": str(path)}

    # --- Modelos locales / llama.cpp ---------------------------------------------------
    @app.get("/api/models/local")
    async def local_models():
        return hub.local_models()

    @app.delete("/api/models/local")
    async def delete_local(path: str):
        if llama.model_path and Path(llama.model_path).resolve() == Path(path).resolve():
            await llama.unload()
        try:
            hub.delete_local(path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    @app.get("/api/llama/status")
    async def llama_status():
        return llama.status()

    @app.get("/api/llama/logs")
    async def llama_logs():
        return {"lines": list(llama.logs)}

    @app.post("/api/llama/load")
    async def llama_load(body: dict):
        return await llama.load(body["path"], body.get("ctx"), body.get("threads"),
                                body.get("gpu_layers"), body.get("extra_args"))

    @app.post("/api/llama/selftest")
    async def llama_selftest():
        """Comprueba cómo trabaja el modelo local cargado con el agente: ¿llama herramientas?, ¿a qué velocidad?"""
        if not llama.ready:
            raise HTTPException(409, "Carga primero un modelo local")
        ctx = ToolContext(files, cfg, None, agent=True, perm_mode="plan")
        ctx.profile = profile_for(LOCAL_PROVIDER, llama.status()["model"] or "", True, cfg["agent_profile"] or "auto")
        ctx.compact_specs = True
        system = ctx.system_hint()
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": "Prueba de herramientas: llama a list_dir sin ruta y dime cuántos elementos hay."}]
        opts = {"temperature": float(cfg["agent_temperature"] or 0.3), "max_tokens": 600,
                "n_ctx": int((llama.params or {}).get("ctx") or 8192), "thinking": bool(cfg["local_thinking"])}
        called = rescued = False
        tps = ptps = None
        err = None
        t0 = time.time()
        try:
            async def run():
                nonlocal called, rescued, tps, ptps
                async for ev in chat_stream(provider_for(LOCAL_PROVIDER), "local", msgs, opts, ctx):
                    if ev["type"] == "tool_call":
                        called = True
                    elif ev["type"] == "retract":
                        rescued = True
                    elif ev["type"] == "stats":
                        tps = ev.get("tokens_per_second") or tps
            await asyncio.wait_for(run(), 240)
        except asyncio.TimeoutError:
            err = "El modelo tardó más de 4 minutos en responder."
        except (ProviderError, httpx.HTTPError, RuntimeError) as e:
            err = str(e)
        secs = round(time.time() - t0, 1)
        if err:
            verdict, msg = "error", err
        elif called and not rescued:
            verdict, msg = "ok", "Llama a las herramientas correctamente: puede trabajar como agente."
        elif called:
            verdict, msg = "text", ("Escribe las llamadas como texto en vez de usar el formato de herramientas; G3G3AI las rescata "
                                    "y funciona, pero con menos fiabilidad. Un modelo con plantilla de herramientas va mejor.")
        else:
            verdict, msg = "none", ("No llamó a ninguna herramienta: sirve para charlar, pero no para el modo agente. "
                                    "Prueba uno con soporte de herramientas (p. ej. Qwen2.5/Qwen3, Llama 3.1+, Mistral).")
        if tps and tps < 5 and verdict != "error":
            msg += f" Va lento ({tps:.1f} tok/s): prueba un modelo más pequeño, la cuantización Q4_K_M o activa la gráfica."
        return {"verdict": verdict, "message": msg, "seconds": secs, "tokens_per_second": tps,
                "profile": ctx.profile, "context": opts["n_ctx"], "tools_sent": len(ctx.names()),
                "system_tokens_est": int(len(system) / 3.5)}

    @app.post("/api/llama/unload")
    async def llama_unload():
        return await llama.unload()

    # --- Hugging Face -------------------------------------------------------------------
    @app.get("/api/hub/search")
    async def hub_search(q: str, sort: str = "downloads"):
        try:
            return await hub.search(q, sort)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"No se pudo contactar con Hugging Face: {e}") from e

    @app.get("/api/hub/files")
    async def hub_files(repo: str):
        try:
            return await hub.files(repo)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Error de Hugging Face: {e}") from e

    # --- Dictado por voz ----------------------------------------------------------------
    @app.get("/api/voice")
    async def voice_status():
        from . import voice
        return await asyncio.to_thread(voice.status, cfg)

    @app.post("/api/voice/setup")
    async def voice_setup(body: dict | None = None):
        """Descarga el modelo de voz elegido (o el recomendado) con el gestor de descargas de modelos."""
        from . import voice
        name = (body or {}).get("model") or cfg["voice_model"] or voice.DEFAULT_MODEL
        if name not in voice.MODELS:
            raise HTTPException(400, "Modelo de voz desconocido")
        cfg.set("voice_model", name)
        return hub.start(voice.WHISPER_REPO, [name])

    @app.post("/api/voice/transcribe")
    async def voice_transcribe(request: Request):
        from . import voice
        wav = await request.body()
        if len(wav) > 50_000_000:
            raise HTTPException(413, "Grabación demasiado larga")
        try:
            return await voice.transcribe(cfg, wav)
        except voice.VoiceError as e:
            raise HTTPException(409, str(e)) from e
        except httpx.HTTPError as e:
            raise HTTPException(502, f"No se pudo contactar con el servicio de transcripción: {e}") from e

    @app.post("/api/hub/download")
    async def hub_download(body: dict):
        return hub.start(body["repo"], body["files"])

    @app.get("/api/hub/downloads")
    async def hub_downloads():
        return list(hub.downloads.values())

    @app.delete("/api/hub/downloads/{did}")
    async def hub_cancel(did: str):
        hub.cancel(did)
        return {"ok": True}

    # --- Archivos ---------------------------------------------------------------------
    def fa(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except FileAccessError as e:
            raise HTTPException(403, str(e)) from e

    @app.get("/api/files/roots")
    async def file_roots():
        return [str(r) for r in files.roots]

    @app.get("/api/files/list")
    async def file_list(path: str = "", hidden: bool = False):
        return fa(files.list_dir, path, hidden)

    @app.get("/api/files/read")
    async def file_read(path: str):
        return fa(files.read_text, path)

    @app.get("/api/files/search")
    async def file_search(q: str, path: str = ""):
        return await asyncio.to_thread(fa, files.search, q, path)

    @app.get("/api/files/download")
    async def file_download(path: str, inline: bool = False):
        p = fa(files.resolve, path)
        if not p.is_file():
            raise HTTPException(404, "No es un archivo")
        return FileResponse(p, filename=p.name, content_disposition_type="inline" if inline else "attachment")

    @app.post("/api/files/open")
    async def file_open(request: Request, body: dict):
        """Abre un archivo con su programa (Excel, Word, visor de PDF…) o muestra su carpeta. Sólo desde este mismo
        equipo: desde el móvil no tendría sentido abrir algo en la pantalla del PC."""
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(403, "Sólo se puede abrir desde el propio equipo; desde aquí, descárgalo.")
        p = fa(files.resolve, body.get("path"))
        if not p.exists():
            raise HTTPException(404, "Ese archivo ya no existe")
        reveal = bool(body.get("reveal"))
        import subprocess
        try:
            if sys.platform == "win32":
                if reveal:
                    subprocess.Popen(["explorer", "/select,", str(p)])
                else:
                    os.startfile(str(p))  # noqa: S606  (abre con el programa asociado)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(p)] if reveal else ["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p.parent if reveal else p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            raise HTTPException(500, f"No se pudo abrir: {e}") from e
        return {"ok": True}

    @app.post("/api/files/upload")
    async def file_upload(dir: str = Form(""), file: UploadFile = File(...)):
        target = fa(files.safe_child, dir, file.filename or "archivo")
        with open(target, "wb") as out:
            while chunk := await file.read(1 << 20):
                out.write(chunk)
        return {"path": str(target), "name": target.name, "size": target.stat().st_size}

    @app.post("/api/files/write")
    async def file_write(body: dict):
        return fa(files.write_text, body["path"], body.get("content", ""))

    @app.post("/api/files/mkdir")
    async def file_mkdir(body: dict):
        p = fa(files.resolve, body["path"])
        p.mkdir(parents=True, exist_ok=True)
        return {"path": str(p)}

    # --- API compatible con OpenAI (para usar el modelo local desde otras apps) -----------------
    proxy_client = httpx.AsyncClient(timeout=httpx.Timeout(30, read=600))

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
    async def openai_proxy(path: str, request: Request):
        if llama.state != "ready":
            return JSONResponse({"error": {"message": "No hay modelo local cargado"}}, status_code=503)
        req = proxy_client.build_request(
            request.method, f"{llama.base_url}/v1/{path}", content=await request.body(),
            headers={"content-type": request.headers.get("content-type", "application/json")},
            params=request.query_params,
        )
        r = await proxy_client.send(req, stream=True)
        return StreamingResponse(r.aiter_raw(), status_code=r.status_code,
                                 media_type=r.headers.get("content-type"), background=BackgroundTask(r.aclose))

    # --- Interfaz ---------------------------------------------------------------------
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/manifest.webmanifest")
    async def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js")
    async def sw():
        return FileResponse(STATIC / "sw.js", media_type="application/javascript")

    app.state.find_llama = find_llama_server
    return app
