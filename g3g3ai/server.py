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
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import __version__
from .config import DATA_DIR, Config
from .db import DB
from .files import FileAccessError, Files
from .hub import Hub
from .memory import Memory, MemoryRejected
from .llama import LlamaManager, default_threads, find_llama_server
from . import router, sandbox
from .engine import EngineInstaller
from . import documents as D
from . import devtools, hardware, images, ollama
from .context import HistoryBuilder
from .sync import INTERVAL as SYNC_INTERVAL, Sync, SyncError, new_key as new_sync_key
from .providers import ProviderError, chat_stream, complete, complete_messages, list_models
from .tools import ToolContext, resolve_approval

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


def create_app(cfg: Config | None = None, data_dir: Path | None = None) -> FastAPI:
    cfg = cfg or Config()
    db = DB((data_dir or DATA_DIR) / "g3g3ai.db")
    files = Files(cfg)
    hub = Hub(cfg)
    llama = LlamaManager(cfg)
    engines = {"llama": EngineInstaller(cfg, "llama"), "sd": EngineInstaller(cfg, "sd")}
    memory = Memory(db)
    sync = Sync(cfg, db, memory)
    session_allow: dict[str, set] = {}  # conversación -> herramientas permitidas «siempre»

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        last = cfg["last_model"]
        if cfg["autoload_last_model"] and last and Path(last).is_file():
            await llama.load(last)
        sync.start()
        yield
        sync.stop()
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
        if ((path.startswith("/api/") or path.startswith("/v1/"))
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

    @app.post("/api/chat")
    async def chat(body: dict):
        cid = body.get("conversation_id")
        pid = body.get("provider") or LOCAL_PROVIDER
        model = body.get("model") or "local"
        text = (body.get("message") or "").strip()
        attachments = body.get("attachments") or []
        attach_text, attach_meta = expand_attachments(attachments)
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

        conv = db.get_conversation(cid) if cid else None
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
            if pid == LOCAL_PROVIDER and not llama.ready:
                raise HTTPException(409, "No hay ningún modelo local cargado. Cárgalo en la pestaña Modelos.")
            candidates = [(pid, model, None)]

        if not conv:
            conv = db.create_conversation(provider=pid, model=model, system=body.get("system"))
            cid = conv["id"]
        if text or attach_text:
            meta = ({"attachments": attach_meta, "expanded": f"{attach_text}\n\n{text}".strip() or text}
                    if attach_meta else None)
            db.add_message(cid, "user", text, meta=meta)
            if conv["title"] == "Nueva conversación":
                title = text or (attach_meta[0]["name"] if attach_meta else "Conversación")
                db.update_conversation(cid, title=title[:60])
        db.update_conversation(cid, provider=pid, model=model)
        if "system" in body:
            db.update_conversation(cid, system=body.get("system"))
        conv = db.get_conversation(cid)

        base_system = conv.get("system") if conv.get("system") is not None else cfg["default_system_prompt"]
        opts = {"temperature": body.get("temperature", cfg["temperature"]),
                "max_tokens": body.get("max_tokens", cfg["max_tokens"])}

        def memory_for(chosen_pid: str) -> bool:
            if not cfg["memory_enabled"] or body.get("incognito"):
                return False
            return chosen_pid == LOCAL_PROVIDER or bool(cfg["memory_api"])

        async def image_gen(prompt: str, size=None):
            return await images.generate(cfg, provider_for, prompt, size)

        def make_ctx(chosen_pid: str):
            mem = memory if (memory_for(chosen_pid) and cfg["memory_auto"]) else None
            img = image_gen if cfg["image_provider"] else None
            if not (agent or use_web or mem or img):
                return None
            delegate = local_complete if (agent and chosen_pid != LOCAL_PROVIDER and llama.ready) else None
            return ToolContext(files, cfg, delegate, agent=agent, web=use_web,
                               session_allow=session_allow.setdefault(cid, set()), memory=mem, source=cid,
                               image_gen=img)

        async def gen():
            content, reasoning, trace, stats, route = "", "", [], {}, None
            made: list[str] = []
            out_files: list[str] = []
            yield sse({"type": "start", "conversation_id": cid})
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
            try:
                for i, (cpid, cmodel, why) in enumerate(candidates):
                    p = provider_for(cpid)
                    shown = (llama.status()["model"] or "local") if cpid == LOCAL_PROVIDER else cmodel
                    route = {"provider": cpid, "model": shown, "reason": why}
                    if why:
                        yield sse({"type": "route", **route})
                    ctx = make_ctx(cpid)
                    mem_text = memory.prompt() if memory_for(cpid) else ""
                    system = "\n\n".join(x for x in (base_system, mem_text, ctx.system_hint() if ctx else "") if x)
                    try:
                        history = []
                        async for ev in builder.build(conv, cpid, cmodel, system, opts["max_tokens"] or 2048):
                            if ev["type"] == "_history":
                                history = ev["messages"]
                            else:
                                yield sse(ev)
                        msgs = ([{"role": "system", "content": system}] if system else []) + history
                        async for ev in chat_stream(p, cmodel, msgs, opts, ctx):
                            if ev["type"] == "content":
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
                            yield sse(ev)
                        break
                    except (ProviderError, httpx.HTTPError, RuntimeError) as e:
                        msg = str(e) or type(e).__name__
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
                            "files": out_files or None}
                    stats["message_id"] = db.add_message(cid, "assistant", content, reasoning or None, meta)
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
            raise HTTPException(502, f"No se pudo consultar GitHub: {e}") from e

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
        return {"hardware": hw, "recommendation": hardware.recommend(hw)}

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
