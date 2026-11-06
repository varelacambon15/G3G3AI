"""Servidor web de G3G3AI: API + interfaz, accesible desde la red local."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import __version__
from .config import DATA_DIR, Config
from .db import DB
from .files import FileAccessError, Files
from .hub import Hub
from .llama import LlamaManager, default_threads, find_llama_server
from .providers import ProviderError, chat_stream, list_models

STATIC = Path(__file__).parent / "static"
COOKIE = "g3g3ai_token"
LOCAL_PROVIDER = "local"


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


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    db = DB(DATA_DIR / "g3g3ai.db")
    files = Files(cfg)
    hub = Hub(cfg)
    llama = LlamaManager(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        last = cfg["last_model"]
        if cfg["autoload_last_model"] and last and Path(last).is_file():
            await llama.load(last)
        yield
        await llama.unload()

    app = FastAPI(title="G3G3AI", version=__version__, lifespan=lifespan)
    app.state.cfg, app.state.db, app.state.llama, app.state.hub = cfg, db, llama, hub

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
        if (path.startswith("/api/") or path.startswith("/v1/")) and path != "/api/login":
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
        }

    @app.get("/api/settings")
    async def get_settings():
        return cfg.public()

    @app.put("/api/settings")
    async def put_settings(body: dict):
        cfg.update_public(body)
        return cfg.public()

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
        out = [{"id": LOCAL_PROVIDER, "name": "Local (llama.cpp)", "type": "local", "enabled": True}]
        for p in cfg.public()["providers"]:
            out.append({k: p.get(k) for k in ("id", "name", "type", "enabled")})
        return out

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

    @app.patch("/api/conversations/{cid}")
    async def patch_conversation(cid: str, body: dict):
        db.update_conversation(cid, **body)
        return db.get_conversation(cid)

    @app.delete("/api/conversations/{cid}")
    async def delete_conversation(cid: str):
        db.delete_conversation(cid)
        return {"ok": True}

    @app.delete("/api/conversations/{cid}/messages/{mid}")
    async def truncate_conversation(cid: str, mid: int):
        db.delete_messages_from(cid, mid)
        return db.get_conversation(cid)

    # --- Chat ---------------------------------------------------------------------
    def expand_attachments(paths: list[str]) -> tuple[str, list[dict]]:
        parts, meta = [], []
        for p in paths:
            try:
                f = files.read_text(p, 60_000)
            except FileAccessError as e:
                raise HTTPException(400, str(e)) from e
            note = "\n[... truncado ...]" if f["truncated"] else ""
            parts.append(f"Archivo adjunto `{f['path']}`:\n```\n{f['content']}{note}\n```")
            meta.append({"name": f["name"], "path": f["path"]})
        return "\n\n".join(parts), meta

    @app.post("/api/chat")
    async def chat(body: dict):
        cid = body.get("conversation_id")
        pid = body.get("provider") or LOCAL_PROVIDER
        model = body.get("model") or "local"
        text = (body.get("message") or "").strip()
        attach_text, attach_meta = expand_attachments(body.get("attachments") or [])
        if not text and not attach_text and not body.get("continue"):
            raise HTTPException(400, "Mensaje vacío")
        p = provider_for(pid)
        if pid == LOCAL_PROVIDER and llama.state != "ready":
            raise HTTPException(409, "No hay ningún modelo local cargado. Cárgalo en la pestaña Modelos.")

        conv = db.get_conversation(cid) if cid else None
        if not conv:
            conv = db.create_conversation(provider=pid, model=model, system=body.get("system"))
            cid = conv["id"]
        if text or attach_text:
            meta = {"attachments": attach_meta, "expanded": f"{attach_text}\n\n{text}".strip()} if attach_meta else None
            db.add_message(cid, "user", text, meta=meta)
            if conv["title"] == "Nueva conversación":
                title = text or (attach_meta[0]["name"] if attach_meta else "Conversación")
                db.update_conversation(cid, title=title[:60])
        db.update_conversation(cid, provider=pid, model=model)
        if "system" in body:
            db.update_conversation(cid, system=body.get("system"))
        conv = db.get_conversation(cid)

        system = conv.get("system") if conv.get("system") is not None else cfg["default_system_prompt"]
        use_tools = bool(body.get("use_tools"))
        if use_tools:
            roots = ", ".join(str(r) for r in files.roots)
            system = (system or "") + (
                f"\n\nTienes herramientas para acceder a los archivos del dispositivo (carpetas permitidas: {roots}). "
                "Úsalas cuando el usuario pregunte por sus archivos."
            )
        history = [{"role": "system", "content": system}] if system else []
        for m in conv["messages"]:
            if m["role"] in ("user", "assistant"):
                content = (m["meta"] or {}).get("expanded") or m["content"]
                history.append({"role": m["role"], "content": content})
        opts = {"temperature": body.get("temperature", cfg["temperature"]),
                "max_tokens": body.get("max_tokens", cfg["max_tokens"])}

        async def gen():
            content, reasoning, trace, stats = "", "", [], {}
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': cid})}\n\n"
            try:
                async for ev in chat_stream(p, model, history, opts, files, use_tools, cfg["allow_ai_file_write"]):
                    if ev["type"] == "content":
                        content += ev["text"]
                    elif ev["type"] == "reasoning":
                        reasoning += ev["text"]
                    elif ev["type"] in ("tool_call", "tool_result"):
                        trace.append(ev)
                    elif ev["type"] == "stats":
                        stats.update({k: v for k, v in ev.items() if v is not None and k != "type"})
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            except (ProviderError, httpx.HTTPError) as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e) or type(e).__name__}, ensure_ascii=False)}\n\n"
            finally:
                if content or reasoning or trace:
                    meta = {"provider": pid, "model": model, "stats": stats, "tools": trace or None}
                    mid = db.add_message(cid, "assistant", content, reasoning or None, meta)
                    stats["message_id"] = mid
            yield f"data: {json.dumps({'type': 'done', **stats})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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

    @app.post("/api/llama/unload")
    async def llama_unload():
        return await llama.unload()

    # --- Hugging Face -------------------------------------------------------------------
    @app.get("/api/hub/search")
    async def hub_search(q: str):
        try:
            return await hub.search(q)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"No se pudo contactar con Hugging Face: {e}") from e

    @app.get("/api/hub/files")
    async def hub_files(repo: str):
        try:
            return await hub.files(repo)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Error de Hugging Face: {e}") from e

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
