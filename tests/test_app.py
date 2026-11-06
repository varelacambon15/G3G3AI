import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("G3G3AI_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("G3G3AI_DATA_DIR", str(tmp_path / "data"))
    for m in [m for m in sys.modules if m.startswith("g3g3ai")]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    from g3g3ai.config import Config
    from g3g3ai.server import create_app

    home = tmp_path / "home"; (home / "docs").mkdir(parents=True)
    (home / "hola.txt").write_text("contenido secreto de prueba")
    (tmp_path / "fuera.txt").write_text("no deberías verme")
    models = tmp_path / "models" / "org__repo"; models.mkdir(parents=True)
    (models / "tiny-Q4_K_M.gguf").write_bytes(b"GGUF" + b"\0" * 100)

    script = Path(__file__).parent / "fake_llama_server.py"
    if sys.platform == "win32":
        fake = tmp_path / "llama-server.bat"
        fake.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    else:
        fake = tmp_path / "llama-server"
        fake.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
        fake.chmod(0o755)

    cfg = Config(tmp_path / "cfg" / "config.json")
    cfg.data.update({"file_roots": [str(home)], "models_dir": str(tmp_path / "models"),
                     "llama_server_path": str(fake), "llama_port": free_port(), "autoload_last_model": False,
                     "localhost_without_token": False})
    cfg.save()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client, cfg, home, tmp_path


def load_model(client, h):
    models = client.get("/api/models/local", headers=h).json()
    client.post("/api/llama/load", headers=h, json={"path": models[0]["path"]})
    for _ in range(50):
        if client.get("/api/llama/status", headers=h).json()["state"] == "ready":
            return
        time.sleep(0.2)
    raise AssertionError("el modelo no cargó")


def auth(cfg):
    return {"Authorization": f"Bearer {cfg['token']}"}


def sse(resp):
    return [json.loads(l[5:]) for l in resp.text.split("\n\n") if l.startswith("data:")]


def test_auth_required(env):
    client, cfg, *_ = env
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/login", json={"token": "mal"}).status_code == 401
    assert client.post("/api/login", json={"token": cfg["token"]}).status_code == 200
    assert client.get("/api/status").status_code == 200  # cookie
    assert client.get("/").status_code == 200


def test_settings_mask_secrets(env):
    client, cfg, *_ = env
    h = auth(cfg)
    s = client.get("/api/settings", headers=h).json()
    op = next(p for p in s["providers"] if p["id"] == "openai")
    op["api_key"] = "sk-123"; op["enabled"] = True
    client.put("/api/settings", headers=h, json=s)
    s2 = client.get("/api/settings", headers=h).json()
    assert next(p for p in s2["providers"] if p["id"] == "openai")["api_key"] == "••••••••"
    assert s2["token"] == "••••••••"
    client.put("/api/settings", headers=h, json=s2)  # reenviar enmascarado no borra la clave
    assert cfg.provider("openai")["api_key"] == "sk-123"
    assert cfg["token"] != "••••••••"


def test_files_sandbox(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    names = [e["name"] for e in client.get("/api/files/list", headers=h).json()["entries"]]
    assert "hola.txt" in names and "docs" in names
    assert client.get("/api/files/read", params={"path": str(home / "hola.txt")}, headers=h).json()["content"].startswith("contenido")
    assert client.get("/api/files/read", params={"path": str(tmp / "fuera.txt")}, headers=h).status_code == 403
    assert client.get("/api/files/read", params={"path": str(home / ".." / "fuera.txt")}, headers=h).status_code == 403
    r = client.post("/api/files/upload", headers=h, data={"dir": str(home / "docs")},
                    files={"file": ("../../evil.txt", b"x")})
    assert r.status_code == 200 and r.json()["path"] == str(home / "docs" / "evil.txt")


def test_local_model_chat_and_tools(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    models = client.get("/api/models/local", headers=h).json()
    assert models[0]["repo"] == "org/repo" and models[0]["quant"] == "Q4_K_M"
    assert client.post("/api/chat", headers=h, json={"message": "hola"}).status_code == 409
    client.post("/api/llama/load", headers=h, json={"path": models[0]["path"]})
    for _ in range(50):
        if client.get("/api/llama/status", headers=h).json()["state"] == "ready":
            break
        time.sleep(0.2)
    assert client.get("/api/llama/status", headers=h).json()["state"] == "ready"

    # Chat simple con adjunto
    r = client.post("/api/chat", headers=h, json={"message": "resume esto", "attachments": [str(home / "hola.txt")]})
    evs = sse(r)
    cid = evs[0]["conversation_id"]
    text = "".join(e["text"] for e in evs if e["type"] == "content")
    assert "resume esto" in text and evs[-1]["type"] == "done" and evs[-1]["tokens_per_second"] == 12.5
    conv = client.get(f"/api/conversations/{cid}", headers=h).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["reasoning"] == "pensando"
    assert "contenido secreto" in conv["messages"][0]["meta"]["expanded"]
    assert conv["title"] == "resume esto"

    # Herramientas: el modelo pide list_dir y luego responde con lo que ve
    r = client.post("/api/chat", headers=h, json={"conversation_id": cid, "message": "lista mis archivos", "use_tools": True})
    evs = sse(r)
    assert any(e["type"] == "tool_call" and e["name"] == "list_dir" for e in evs)
    assert "Veo: hola.txt" in "".join(e["text"] for e in evs if e["type"] == "content")

    # Regenerar: borrar la última respuesta y continuar
    conv = client.get(f"/api/conversations/{cid}", headers=h).json()
    last = conv["messages"][-1]
    client.delete(f"/api/conversations/{cid}/messages/{last['id']}", headers=h)
    evs = sse(client.post("/api/chat", headers=h, json={"conversation_id": cid, "continue": True}))
    assert evs[-1]["type"] == "done"

    # Proxy compatible con OpenAI
    r = client.post("/v1/chat/completions", headers=h, json={"messages": [{"role": "user", "content": "x"}], "stream": True})
    assert r.status_code == 200 and "Eco" in r.text

    assert client.post("/api/llama/unload", headers=h).json()["state"] == "stopped"


def test_hub_split_grouping(env):
    from g3g3ai.hub import SPLIT_RE, quant_of
    assert SPLIT_RE.match("Model-Q8_0-00001-of-00003.gguf").group(1) == "Model-Q8_0"
    assert quant_of("qwen3-4b-IQ4_XS.gguf") == "IQ4_XS"
    assert quant_of("x.Q5_K_M.gguf") == "Q5_K_M"


def test_router_plan():
    from g3g3ai import router
    cfg = {"router_fast": "local::local", "router_strong": "deepseek::deepseek-chat", "router_mode": "smart"}
    both = lambda pid: True  # noqa: E731
    assert router.plan(cfg, "hola, ¿qué tal?", False, False, both)[0][0] == "local"
    assert router.plan(cfg, "corrige este error de Python", False, False, both)[0][0] == "deepseek"
    assert router.plan(cfg, "hola", False, True, both)[0][0] == "deepseek"  # agente
    only_local = lambda pid: pid == "local"  # noqa: E731
    plan = router.plan(cfg, "escribe un script", False, False, only_local)
    assert [c[0] for c in plan] == ["local"] and "no está disponible" in plan[0][2]
    cfg["router_mode"] = "api_first"
    assert [c[0] for c in router.plan(cfg, "hola", False, False, both)] == ["deepseek", "local"]


def test_auto_fallback_to_local(env):
    """Modo Auto: la API (inaccesible) falla antes de responder → responde el modelo local."""
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    s = client.get("/api/settings", headers=h).json()
    for p in s["providers"]:
        if p["id"] == "deepseek":
            p.update(enabled=True, api_key="x", base_url="http://127.0.0.1:9/v1")
    s["router_mode"] = "api_first"
    client.put("/api/settings", headers=h, json=s)
    evs = sse(client.post("/api/chat", headers=h, json={"provider": "auto", "message": "hola"}))
    types = [e["type"] for e in evs]
    assert "route_fallback" in types and types[-1] == "done"
    routes = [e for e in evs if e["type"] == "route"]
    assert routes[0]["provider"] == "deepseek" and routes[-1]["provider"] == "local"
    cid = evs[0]["conversation_id"]
    msg = client.get(f"/api/conversations/{cid}", headers=h).json()["messages"][-1]
    assert msg["meta"]["provider"] == "local" and "Eco" in msg["content"]


def test_agent_command_with_approval(env):
    import threading
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    cfg.data.update(ai_commands="ask", agent_workdir=str(home))
    approved = []

    def approver():
        # Espera a que aparezca la solicitud y la aprueba (como haría el usuario en la interfaz)
        from g3g3ai.tools import PENDING
        for _ in range(100):
            if PENDING:
                aid = next(iter(PENDING))
                approved.append(client.post("/api/chat/approve", headers=h, json={"id": aid, "approved": True}).status_code)
                return
            time.sleep(0.05)

    threading.Thread(target=approver).start()
    evs = sse(client.post("/api/chat", headers=h, json={"message": "ejecuta un comando", "use_tools": True}))
    assert approved == [200]
    assert any(e["type"] == "approval" and e["args"]["command"] == "echo hola-g3" for e in evs)
    res = next(e for e in evs if e["type"] == "tool_result")
    assert "hola-g3" in res["result"] and "salida: 0" in res["result"]

    # Con permisos desactivados la herramienta ni se ofrece
    cfg.data.update(ai_commands="off")
    evs = sse(client.post("/api/chat", headers=h, json={"message": "ejecuta otra vez", "use_tools": True}))
    assert not any(e["type"] == "approval" for e in evs)


def test_edit_file_tool(env):
    client, cfg, home, tmp = env
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext
    import asyncio
    (home / "a.py").write_text("x = 1\ny = 2\n")
    ctx = ToolContext(Files(cfg), cfg)
    r = asyncio.run(ctx.run("edit_file", {"path": str(home / "a.py"), "old_text": "y = 2", "new_text": "y = 3"}))
    assert r.startswith("Editado") and (home / "a.py").read_text() == "x = 1\ny = 3\n"
    r = asyncio.run(ctx.run("edit_file", {"path": str(home / "a.py"), "old_text": "nada", "new_text": ""}))
    assert r.startswith("Error")
    r = asyncio.run(ctx.run("read_file", {"path": str(home / "a.py"), "start_line": 2}))
    assert "2: y = 3" in r and "1: x" not in r
    r = asyncio.run(ctx.run("read_file", {"path": str(tmp / "fuera.txt")}))
    assert r.startswith("Error")
