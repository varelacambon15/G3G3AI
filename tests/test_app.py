import json
import re
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
    cfg.data.update({"file_roots": [str(home)], "write_roots": [str(home)], "models_dir": str(tmp_path / "models"),
                     "llama_server_path": str(fake), "llama_port": free_port(), "autoload_last_model": False,
                     "localhost_without_token": False})
    cfg.save()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client, cfg, home, tmp_path


def load_model(client, h):
    models = [m for m in client.get("/api/models/local", headers=h).json() if not m["mmproj"]]
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
    assert "hola-g3" in res["result"] and re.search(r"salida( \(aislado\))?: 0", res["result"])

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


# --- Seguridad de carpetas y comandos ------------------------------------------------------
def test_blocked_paths_and_write_roots(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("CLAVE PRIVADA")
    (home / "proyecto").mkdir()
    (home / "proyecto" / ".env").write_text("API_KEY=secreta")
    (home / "notas").mkdir()
    cfg.data.update(write_roots=[str(home / "proyecto")],
                    blocked_paths=["~/.ssh".replace("~", str(home)), ".env", "*.pem"])
    # Ni la interfaz ni la IA ven rutas protegidas
    assert client.get("/api/files/read", params={"path": str(home / ".ssh" / "id_rsa")}, headers=h).status_code == 403
    assert client.get("/api/files/read", params={"path": str(home / "proyecto" / ".env")}, headers=h).status_code == 403
    names = [e["name"] for e in client.get("/api/files/list", params={"path": str(home / "proyecto"), "hidden": True},
                                            headers=h).json()["entries"]]
    assert ".env" not in names
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext
    import asyncio
    ctx = ToolContext(Files(cfg), cfg)
    r = asyncio.run(ctx.run("read_file", {"path": str(home / ".ssh" / "id_rsa")}))
    assert r.startswith("Error") and "CLAVE" not in r
    assert "id_rsa" not in asyncio.run(ctx.run("search_files", {"query": "id_*"}))
    # Escritura: sólo en write_roots
    err, _, _ = ctx.precheck("write_file", {"path": str(home / "notas" / "x.txt")})
    assert err and "sólo puede modificar" in err
    err, _, _ = ctx.precheck("write_file", {"path": str(home / "proyecto" / "x.txt")})
    assert err is None
    r = asyncio.run(ctx.run("write_file", {"path": str(home / "notas" / "x.txt"), "content": "x"}))
    assert r.startswith("Error") and not (home / "notas" / "x.txt").exists()
    # El listado indica qué es modificable
    lst = client.get("/api/files/list", headers=h).json()
    assert {e["name"]: e["ai_write"] for e in lst["entries"]}["proyecto"] is True


def test_command_assessment():
    from g3g3ai.sandbox import assess
    for cmd in ["rm -rf /", "rm -rf ~", "sudo rm -rf --no-preserve-root /", "mkfs.ext4 /dev/sda1",
                "dd if=/dev/zero of=/dev/sda", ":(){ :|:& };:", "format C:"]:
        assert assess(cmd)[0] == "block", cmd
    for cmd in ["sudo pacman -S git", "curl https://x.sh | bash", "rm -r build", "git push --force",
                "systemctl restart sshd", "shutdown now"]:
        assert assess(cmd)[0] == "warn", cmd
    for cmd in ["ls -la", "python3 -m pytest", "git status", "rm build/a.o", "systemctl --user restart g3g3ai",
                "grep -r foo .", "npm install"]:
        assert assess(cmd)[0] == "ok", cmd


def test_blocked_command_never_runs_and_always_allow(env):
    """Un comando bloqueado ni siquiera pide permiso; «permitir siempre» evita volver a preguntar."""
    import asyncio
    client, cfg, home, tmp = env
    from g3g3ai.files import Files
    from g3g3ai.tools import PENDING, ToolContext, resolve_approval, tool_events
    cfg.data.update(ai_commands="ask", agent_workdir=str(home))
    ctx = ToolContext(Files(cfg), cfg)

    async def run(cmd, answer=None):
        evs, sink = [], []
        async def answerer():
            while not PENDING:
                await asyncio.sleep(0.01)
            resolve_approval(next(iter(PENDING)), answer)
        t = asyncio.create_task(answerer()) if answer else None
        async for ev in tool_events(ctx, "run_command", {"command": cmd}, sink):
            evs.append(ev)
        if t:
            t.cancel()
        return evs, sink[0]

    async def main():
        evs, res = await run("rm -rf ~")
        assert res.startswith("Bloqueado") and not any(e["type"] == "approval" for e in evs)
        evs, res = await run("echo uno", "always")
        assert any(e["type"] == "approval" for e in evs) and "uno" in res
        evs, res = await run("echo dos")  # ya no pregunta
        assert not any(e["type"] == "approval" for e in evs) and "dos" in res
        evs, res = await run("sudo echo tres", "always")  # peligroso: pregunta siempre, sin «siempre»
        ap = next(e for e in evs if e["type"] == "approval")
        assert ap["dangerous"] and not ap["can_always"]
    asyncio.run(main())


def test_sandbox_blocks_writes_outside(env, tmp_path):
    from g3g3ai import sandbox
    if not sandbox.bwrap_path():
        pytest.skip("bubblewrap no disponible")
    import asyncio
    client, cfg, home, tmp = env
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext
    (home / "proyecto").mkdir()
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_rsa").write_text("CLAVE")
    cfg.data.update(write_roots=[str(home / "proyecto")], agent_workdir=str(home / "proyecto"),
                    blocked_paths=[str(home / ".ssh")], ai_commands="auto")
    ctx = ToolContext(Files(cfg), cfg)
    assert ctx.sandboxed
    r = asyncio.run(ctx.run("run_command", {"command": f"echo ok > dentro.txt; echo x > {home}/fuera.txt; cat {home}/.ssh/id_rsa"}))
    assert (home / "proyecto" / "dentro.txt").exists()
    assert not (home / "fuera.txt").exists()
    assert "CLAVE" not in r


# --- Web ------------------------------------------------------------------------------
DDG_SAMPLE = """
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fes.wikipedia.org%2Fwiki%2FSteam_Deck&amp;rut=abc">Steam <b>Deck</b> - Wikipedia</a></h2>
  <a class="result__snippet" href="x">La <b>Steam Deck</b> es una consola portátil.</a>
</div>
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title"><a rel="nofollow" class="result__a" href="https://store.steampowered.com/steamdeck">Steam Deck</a></h2>
  <a class="result__snippet" href="x">Tienda oficial &amp; más</a>
</div>"""


def test_web_parsing_and_ssrf_guard():
    import asyncio
    from g3g3ai import web
    res = web.parse_duckduckgo(DDG_SAMPLE, 5)
    assert res[0] == {"title": "Steam Deck - Wikipedia", "url": "https://es.wikipedia.org/wiki/Steam_Deck",
                      "snippet": "La Steam Deck es una consola portátil."}
    assert res[1]["snippet"] == "Tienda oficial & más"
    title, text = web.html_to_text("<html><head><title>Hola</title><script>malo()</script></head>"
                                   "<body><h1>Título</h1><p>Uno</p><ul><li>a</li><li>b</li></ul></body></html>")
    assert title == "Hola" and "malo" not in text and "# Título" in text and "- a" in text
    for url in ["http://127.0.0.1:8800/api/settings", "http://localhost/", "http://192.168.1.1/",
                "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "http://konkr.local/"]:
        try:
            asyncio.run(web.check_public(url))
            raise AssertionError(f"debería bloquear {url}")
        except web.WebError:
            pass


def test_web_tools_in_chat(env, monkeypatch):
    """Con 🌐 Web activado (sin Agente) el modelo sólo recibe herramientas web."""
    client, cfg, home, tmp = env
    h = auth(cfg)
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext
    ctx = ToolContext(Files(cfg), cfg, agent=False, web=True)
    assert ctx.names() == ["web_search", "fetch_url"]
    ctx = ToolContext(Files(cfg), cfg, agent=True, web=False)
    assert "web_search" not in ctx.names() and "read_file" in ctx.names()
    from g3g3ai import web
    async def fake_search(cfg, q, n):
        return [{"title": "T", "url": "https://ejemplo.com", "snippet": "S"}]
    monkeypatch.setattr(web, "search", fake_search)
    import asyncio
    out = asyncio.run(ToolContext(Files(cfg), cfg, agent=False, web=True).run("web_search", {"query": "x"}))
    assert "https://ejemplo.com" in out


def test_config_migration_v2_to_v3(tmp_path):
    import json
    from g3g3ai.config import Config
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"config_version": 2, "token": "t", "agent_workdir": "/x/trabajo", "ai_write": "ask"}))
    c = Config(p)
    assert c["write_roots"] == ["/x/trabajo"] and c["config_version"] == 4
    assert c.provider("ollama")["base_url"] == "http://127.0.0.1:11434/v1"  # v4 añade Ollama
    assert "~/.ssh" in c["blocked_paths"] and ".env" in c["blocked_paths"]
    p.write_text(json.dumps({"config_version": 1, "token": "t", "allow_ai_file_write": True}))
    c = Config(p)
    assert c["ai_write"] == "auto" and any(x["id"] == "deepseek" for x in c["providers"])


def test_memory_between_conversations(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    # 1) La IA guarda un recuerdo (se ve en el chat como herramienta)
    evs = sse(client.post("/api/chat", headers=h, json={"message": "recuerda que le gusta el café solo"}))
    assert any(e["type"] == "tool_call" and e["name"] == "memory_save" for e in evs)
    mems = client.get("/api/memory", headers=h).json()
    assert [m["content"] for m in mems] == ["Al usuario le gusta el café solo"]
    # 2) Otra conversación nueva lo recibe como contexto
    evs = sse(client.post("/api/chat", headers=h, json={"message": "qué sabes de mí"}))
    text = "".join(e["text"] for e in evs if e["type"] == "content")
    assert "café solo" in text
    # 3) Modo incógnito y memoria desactivada: no se envía
    evs = sse(client.post("/api/chat", headers=h, json={"message": "qué sabes de mí", "incognito": True}))
    assert "café" not in "".join(e["text"] for e in evs if e["type"] == "content")
    # 4) Gestión manual + filtro de secretos
    r = client.post("/api/memory", headers=h, json={"content": "Su contraseña: hunter2"})
    assert r.status_code == 400
    r = client.post("/api/memory", headers=h, json={"content": "Tiene una Konkr Pocket Fit"})
    mid = r.json()["id"]
    client.put(f"/api/memory/{mid}", headers=h, json={"content": "Tiene una Konkr Pocket Fit y un portátil"})
    assert any("portátil" in m["content"] for m in client.get("/api/memory", headers=h).json())
    client.delete(f"/api/memory/{mid}", headers=h)
    client.delete("/api/memory", headers=h)
    assert client.get("/api/memory", headers=h).json() == []


# --- Documentos, imágenes y resumen de conversaciones -------------------------------------------
def _make_docs(d):
    import zipfile
    from PIL import Image
    with zipfile.ZipFile(d / "informe.docx", "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>Ventas del trimestre: 1234 euros</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(d / "datos.xlsx", "w") as z:
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"><si><t>Producto</t></si><si><t>Konkr</t></si></sst>')
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}"><sheets><sheet name="Hoja1"/></sheets></workbook>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>'
                   '<row><c t="s"><v>0</v></c><c><v>7</v></c></row><row><c t="s"><v>1</v></c><c><v>42</v></c></row>'
                   '</sheetData></worksheet>')
    with zipfile.ZipFile(d / "charla.pptx", "w") as z:
        z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="p" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                   '<a:p><a:r><a:t>Diapositiva sobre IA local</a:t></a:r></a:p></p:sld>')
    Image.new("RGB", (3000, 2000), (200, 30, 30)).save(d / "foto.jpg")
    Image.new("RGB", (600, 800), "white").save(d / "escaneado.pdf")  # PDF sin texto (imagen)


def test_document_extraction(tmp_path):
    from g3g3ai import documents as D
    _make_docs(tmp_path)
    assert "1234 euros" in D.extract_text(tmp_path / "informe.docx")
    x = D.extract_text(tmp_path / "datos.xlsx")
    assert "Hoja1" in x and "Konkr | 42" in x
    assert "IA local" in D.extract_text(tmp_path / "charla.pptx")
    assert D.extract_text(tmp_path / "escaneado.pdf").strip() == ""
    assert len(D.pdf_page_images(tmp_path / "escaneado.pdf")) == 1
    media, b64 = D.image_data_url(tmp_path / "foto.jpg")
    import base64, io
    from PIL import Image
    assert media == "image/jpeg" and max(Image.open(io.BytesIO(base64.b64decode(b64))).size) <= 1568


def test_attachments_vision_and_description(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    _make_docs(home)
    models = tmp / "models" / "org__repo"
    (models / "mmproj-model-f16.gguf").write_bytes(b"GGUF")  # proyector de visión junto al modelo
    load_model(client, h)
    st = client.get("/api/llama/status", headers=h).json()
    assert st["vision"] and "--mmproj" in " ".join(client.get("/api/llama/logs", headers=h).json()["lines"])
    # Documento de Word: va como texto
    evs = sse(client.post("/api/chat", headers=h, json={"message": "resume", "attachments": [str(home / "informe.docx")]}))
    assert evs[-1]["type"] == "done"
    cid = evs[0]["conversation_id"]
    conv = client.get(f"/api/conversations/{cid}", headers=h).json()
    assert "1234 euros" in conv["messages"][0]["meta"]["expanded"]
    # Foto con un modelo con visión: llega como imagen
    evs = sse(client.post("/api/chat", headers=h, json={"message": "qué ves", "attachments": [str(home / "foto.jpg")]}))
    assert "VEO 1 IMAGEN" in "".join(e["text"] for e in evs if e["type"] == "content")
    # Foto con un modelo SIN visión (tipo DeepSeek): la describe el local y llega como texto
    port = cfg["llama_port"]
    s = client.get("/api/settings", headers=h).json()
    s["providers"].append({"id": "sinvision", "name": "Sin visión", "type": "openai", "enabled": True,
                           "base_url": f"http://127.0.0.1:{port}/v1", "api_key": "x", "vision": False})
    client.put("/api/settings", headers=h, json=s)
    evs = sse(client.post("/api/chat", headers=h, json={"message": "y esta", "provider": "sinvision", "model": "m",
                                                         "attachments": [str(home / "escaneado.pdf")]}))
    assert any(e["type"] == "status" and "Describiendo" in e["text"] for e in evs)
    cid2 = evs[0]["conversation_id"]
    msg = client.get(f"/api/conversations/{cid2}", headers=h).json()["messages"][0]
    assert msg["meta"]["attachments"][0]["kind"] == "pdf_scan"
    assert "VEO 1 IMAGEN" in next(iter(msg["meta"]["descriptions"].values()))["text"]
    # Segunda vez: usa la descripción guardada (no vuelve a describir)
    evs = sse(client.post("/api/chat", headers=h, json={"conversation_id": cid2, "message": "más",
                                                         "provider": "sinvision", "model": "m"}))
    assert not any(e["type"] == "status" for e in evs)


def test_long_conversation_is_summarized(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    port = cfg["llama_port"]
    s = client.get("/api/settings", headers=h).json()
    s["providers"].append({"id": "api", "name": "API", "type": "openai", "enabled": True,
                           "base_url": f"http://127.0.0.1:{port}/v1", "api_key": "x"})
    s["context_budget"] = 400
    client.put("/api/settings", headers=h, json=s)
    cid, compacted = None, []
    for i in range(8):
        evs = sse(client.post("/api/chat", headers=h, json={"conversation_id": cid, "provider": "api", "model": "m",
                                                             "message": f"mensaje {i} " + "relleno " * 60}))
        cid = evs[0]["conversation_id"]
        compacted += [e for e in evs if e["type"] == "compacted"]
    assert compacted
    conv = client.get(f"/api/conversations/{cid}", headers=h).json()
    assert conv["summary"] and conv["summary_upto"]
    # Regenerar algo anterior al resumen lo descarta
    first = conv["messages"][0]["id"]
    conv = client.delete(f"/api/conversations/{cid}/messages/{first}", headers=h).json()
    assert conv["summary"] is None


# --- Generación de imágenes ----------------------------------------------------------------
def _fake_exe(tmp, name, script):
    if sys.platform == "win32":
        f = tmp / f"{name}.bat"
        f.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    else:
        f = tmp / name
        f.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
        f.chmod(0o755)
    return f


def test_image_generation_api_tool_and_command(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    port = cfg["llama_port"]
    s = client.get("/api/settings", headers=h).json()
    s["providers"] += [
        {"id": "imgapi", "name": "Img", "type": "openai", "enabled": True, "base_url": f"http://127.0.0.1:{port}/v1", "api_key": "x"},
        {"id": "openrouter-x", "name": "OR", "type": "openai", "enabled": True, "base_url": f"http://127.0.0.1:{port}/v1", "api_key": "x"},
    ]
    s.update(image_provider="imgapi", image_model="gpt-image-1", image_dir=str(home / "imgs"))
    client.put("/api/settings", headers=h, json=s)
    # 1) Directo por API (/images/generations)
    r = client.post("/api/images/generate", headers=h, json={"prompt": "un gato"})
    assert r.status_code == 200 and Path(r.json()["path"]).read_bytes().startswith(b"\x89PNG")
    # 2) La IA usa la herramienta generate_image y la imagen queda en el mensaje
    evs = sse(client.post("/api/chat", headers=h, json={"message": "dibuja un gato"}))
    imgs = [e for e in evs if e["type"] == "image"]
    assert imgs and Path(imgs[0]["path"]).exists()
    cid = evs[0]["conversation_id"]
    msg = client.get(f"/api/conversations/{cid}", headers=h).json()["messages"][-1]
    assert msg["meta"]["images"] == [imgs[0]["path"]]
    # 3) Comando /imagen (sin modelo de texto) en modo chat (estilo OpenRouter)
    cfg.data.update(image_provider="openrouter-x", image_mode="chat")
    evs = sse(client.post("/api/chat", headers=h, json={"message": "/imagen un perro astronauta"}))
    assert any(e["type"] == "image" for e in evs)
    # Se puede ver desde la interfaz
    path = next(e for e in evs if e["type"] == "image")["path"]
    assert client.get("/api/files/download", params={"path": path, "inline": True}, headers=h).status_code == 200


def test_image_generation_local_sd(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    fake = _fake_exe(tmp, "sd", Path(__file__).parent / "fake_sd.py")
    model = tmp / "models" / "sd-turbo-q8_0.gguf"
    model.write_bytes(b"GGUF")
    cfg.data.update(image_provider="local", sd_path=str(fake), sd_model=str(model), image_dir=str(home / "imgs"),
                    sd_max_side=512)
    r = client.post("/api/images/generate", headers=h, json={"prompt": "paisaje", "size": "1024x768"})
    assert r.status_code == 200, r.text
    assert Path(r.json()["path"]).exists()
    cfg.data.update(sd_model="")
    r = client.post("/api/images/generate", headers=h, json={"prompt": "x"})
    assert r.status_code == 400 and "modelo" in r.json()["detail"]


# --- Sincronización entre equipos --------------------------------------------------------
def test_sync_between_two_devices(tmp_path):
    """Dos G3G3AI (p.ej. Konkr y PC) con la misma clave se intercambian conversaciones, memoria y APIs."""
    import threading
    import uvicorn
    from fastapi.testclient import TestClient
    from g3g3ai.config import Config
    from g3g3ai.server import create_app

    def device(name):
        d = tmp_path / name
        cfg = Config(d / "config.json")
        cfg.data.update(localhost_without_token=False, autoload_last_model=False, file_roots=[str(d)],
                        write_roots=[str(d)], models_dir=str(d / "models"), llama_port=free_port())
        cfg.save()
        return cfg, create_app(cfg, data_dir=d)

    cfg_pc, app_pc = device("pc")
    cfg_konkr, app_konkr = device("konkr")
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app_konkr, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        with TestClient(app_pc) as pc, TestClient(app_konkr) as konkr:
            hp, hk = auth(cfg_pc), auth(cfg_konkr)
            # En el PC: una API configurada, un recuerdo y una conversación
            s = pc.get("/api/settings", headers=hp).json()
            next(p for p in s["providers"] if p["id"] == "deepseek").update(enabled=True, api_key="sk-deepseek-secreta")
            pc.put("/api/settings", headers=hp, json=s)
            pc.post("/api/memory", headers=hp, json={"content": "Usa una Konkr Pocket Fit"})
            conv = app_pc.state.db.create_conversation(title="Plan del proyecto")
            app_pc.state.db.add_message(conv["id"], "user", "hola desde el PC")
            # Clave: se genera en el PC y se pega en la Konkr
            key = pc.post("/api/sync/new-key", headers=hp).json()["key"]
            assert len(key.replace("-", "")) == 24
            sk = konkr.get("/api/settings", headers=hk).json()
            sk["sync_key"] = key
            konkr.put("/api/settings", headers=hk, json=sk)
            sp = pc.get("/api/settings", headers=hp).json()
            sp["sync_peers"] = [{"url": f"http://127.0.0.1:{port}"}]
            pc.put("/api/settings", headers=hp, json=sp)
            st = pc.post("/api/sync/now", headers=hp).json()
            assert st[f"http://127.0.0.1:{port}"]["ok"], st
            # En la Konkr aparece todo, incluida la clave API
            assert cfg_konkr.provider("deepseek")["api_key"] == "sk-deepseek-secreta"
            assert cfg_konkr.provider("deepseek")["enabled"] is True
            assert [m["content"] for m in konkr.get("/api/memory", headers=hk).json()] == ["Usa una Konkr Pocket Fit"]
            convs = konkr.get("/api/conversations", headers=hk).json()
            assert [c["title"] for c in convs] == ["Plan del proyecto"]
            msgs = konkr.get(f"/api/conversations/{conv['id']}", headers=hk).json()["messages"]
            assert msgs[0]["content"] == "hola desde el PC"
            # Lo propio de cada equipo no se sincroniza
            assert cfg_konkr["file_roots"] != cfg_pc["file_roots"] and cfg_konkr["token"] != cfg_pc["token"]
            # Cambios en la Konkr vuelven al PC: mensaje nuevo y borrado de un recuerdo
            time.sleep(0.01)
            app_konkr.state.db.add_message(conv["id"], "assistant", "respuesta desde la Konkr")
            mid = konkr.get("/api/memory", headers=hk).json()[0]["id"]
            konkr.delete(f"/api/memory/{mid}", headers=hk)
            pc.post("/api/sync/now", headers=hp)
            msgs = pc.get(f"/api/conversations/{conv['id']}", headers=hp).json()["messages"]
            assert [m["content"] for m in msgs] == ["hola desde el PC", "respuesta desde la Konkr"]
            assert pc.get("/api/memory", headers=hp).json() == []
            # Borrar la conversación en el PC la borra en la Konkr
            pc.delete(f"/api/conversations/{conv['id']}", headers=hp)
            pc.post("/api/sync/now", headers=hp)
            assert konkr.get("/api/conversations", headers=hk).json() == []
            # Con otra clave no se puede sincronizar
            sk = konkr.get("/api/settings", headers=hk).json()
            sk["sync_key"] = "OTRA-CLAVE-DIST-INTA-1234-5678"
            konkr.put("/api/settings", headers=hk, json=sk)
            st = pc.post("/api/sync/now", headers=hp).json()
            assert not st[f"http://127.0.0.1:{port}"]["ok"] and "clave" in st[f"http://127.0.0.1:{port}"]["message"]
            # Y sin clave nadie puede leer nada (la petición va cifrada)
            assert konkr.post("/api/sync/exchange", content=b"basura").status_code == 403
    finally:
        server.should_exit = True
        th.join(5)


# --- Excel avanzado y creación de documentos -------------------------------------------------
def test_excel_variants_and_document_creation(env):
    import asyncio
    import openpyxl
    client, cfg, home, tmp = env
    from g3g3ai import documents as D
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext, tool_events
    wb = openpyxl.Workbook()
    wb.active.append(["A", "B", "Suma"])
    wb.active.append([2, 3, "=A2+B2"])
    wb.save(home / "libro.xlsm")
    text = D.extract_text(home / "libro.xlsm")
    assert "C2: =A2+B2" in text
    xlwt = pytest.importorskip("xlwt")
    book = xlwt.Workbook()
    sh = book.add_sheet("Antiguo")
    sh.write(0, 0, "Precio"); sh.write(1, 0, 12.5); sh.write(2, 0, 3)
    book.save(str(home / "viejo.xls"))
    assert "Antiguo" in D.extract_text(home / "viejo.xls") and "12.5" in D.extract_text(home / "viejo.xls")

    cfg.data.update(ai_write="auto")
    ctx = ToolContext(Files(cfg), cfg)
    assert "create_document" in ctx.names()

    async def run(path, content):
        evs, sink = [], []
        async for ev in tool_events(ctx, "create_document", {"path": path, "content": content}, sink):
            evs.append(ev)
        return evs, sink[0]

    evs, res = asyncio.run(run(str(home / "informe.docx"), "# Título\n\nTexto con **negrita**.\n\n| a | b |\n|---|---|\n| 1 | 2 |"))
    assert "Documento creado" in res and any(e["type"] == "file" for e in evs)
    assert "negrita" in D.extract_text(home / "informe.docx")
    spec = '{"sheets": [{"name": "Datos", "rows": [["x", "y"], [1, "=A2*2"]]}]}'
    evs, res = asyncio.run(run(str(home / "datos.xlsx"), spec))
    assert openpyxl.load_workbook(home / "datos.xlsx")["Datos"]["B2"].value == "=A2*2"
    evs, res = asyncio.run(run(str(home / "charla.pptx"), '{"slides": [{"title": "Hola", "bullets": ["uno"]}]}'))
    assert "Hola" in D.extract_text(home / "charla.pptx")
    evs, res = asyncio.run(run(str(home / "nota.pdf"), "# PDF\n\nCanción y ñandú"))
    assert (home / "nota.pdf").read_bytes().startswith(b"%PDF")
    evs, res = asyncio.run(run(str(home / "x.odt"), "hola"))
    assert res.startswith("Error")
    evs, res = asyncio.run(run(str(tmp / "fuera.docx"), "hola"))  # fuera de las carpetas modificables
    assert res.startswith("Error") and not (tmp / "fuera.docx").exists()


# --- Juegos de Steam --------------------------------------------------------------------
def _fake_steam(base):
    root = base / "Steam"
    (root / "steamapps" / "common" / "Elden Ring" / "Game").mkdir(parents=True)
    (root / "steamapps" / "common" / "Proton 9.0").mkdir(parents=True)
    (root / "steamapps" / "common" / "Elden Ring" / "Game" / "settings.ini").write_text("[video]\nfullscreen=1\n")
    (root / "steamapps" / "appmanifest_1245620.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"1245620"\n\t"name"\t\t"ELDEN RING"\n\t"StateFlags"\t\t"4"\n'
        '\t"installdir"\t\t"Elden Ring"\n\t"SizeOnDisk"\t\t"52000000000"\n}\n')
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{root}"\n\t}}\n}}\n')
    pfx = root / "steamapps" / "compatdata" / "1245620"
    cfgdir = pfx / "pfx" / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming" / "EldenRing"
    cfgdir.mkdir(parents=True)
    (cfgdir / "GraphicsConfig.xml").write_text("<Config><Quality>High</Quality></Config>")
    (pfx / "version").write_text("GE-Proton9-20")
    (root / "config").mkdir()
    (root / "config" / "config.vdf").write_text(
        '"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
        '\t\t\t\t"ConnectCache"\n\t\t\t\t{\n\t\t\t\t\t"abc"\t\t"TOKEN-SECRETO-DE-SESION"\n\t\t\t\t}\n'
        '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t\t"1245620"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"GE-Proton9-20"\n'
        '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
    lc = root / "userdata" / "123" / "config"
    lc.mkdir(parents=True)
    (lc / "localconfig.vdf").write_text(
        '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n'
        '\t\t\t\t{\n\t\t\t\t\t"1245620"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"PROTON_LOG=1 %command%"\n'
        '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
    return root


def test_steam_game_diagnostics_and_safe_edits(env, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Proton y los prefijos de Wine sólo existen en Linux/SteamOS")
    import asyncio
    client, cfg, home, tmp = env
    from g3g3ai import sandbox, steam
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext, tool_events
    root = _fake_steam(tmp)
    monkeypatch.setattr(steam, "HOME", home)
    (home / "steam-1245620.log").write_text("info: ok\nerr:module:import_dll Library d3d12.dll not found\nmás info\n")
    cfg.data.update(steam_dir=str(root), ai_write="auto", ai_commands="ask")
    assert steam.parse_vdf('"a" { "B" "1" "c" { "d" "x\\\\y" } }') == {"a": {"b": "1", "c": {"d": "x\\y"}}}
    games = steam.list_games(cfg)
    assert [(g["name"], g["compat_tool"]) for g in games] == [("ELDEN RING", "GE-Proton9-20")]
    ctx = ToolContext(Files(cfg), cfg)
    assert {"steam_games", "game_diagnostics"} <= set(ctx.names())
    out = asyncio.run(ctx.run("game_diagnostics", {"game": "elden"}))
    assert "GE-Proton9-20" in out and "PROTON_LOG=1 %command%" in out
    assert "d3d12.dll not found" in out and "GraphicsConfig.xml" in out and "settings.ini" in out
    assert "TOKEN-SECRETO" not in out  # de config.vdf sólo se lee la sección de Proton
    # La IA puede leer y modificar archivos del juego (fuera de sus carpetas normales) siempre con permiso + copia
    ini = root / "steamapps" / "common" / "Elden Ring" / "Game" / "settings.ini"
    err, strong, _ = ctx.precheck("edit_file", {"path": str(ini)})
    assert err is None and strong and "juego" in strong[0]

    async def edit():
        from g3g3ai.tools import PENDING, resolve_approval
        async def approve():
            while not PENDING:
                await asyncio.sleep(0.01)
            resolve_approval(next(iter(PENDING)), "yes")
        t = asyncio.create_task(approve())
        evs, sink = [], []
        async for ev in tool_events(ctx, "edit_file", {"path": str(ini), "old_text": "fullscreen=1",
                                                       "new_text": "fullscreen=0"}, sink):
            evs.append(ev)
        t.cancel()
        return evs, sink[0]
    evs, res = asyncio.run(edit())
    assert any(e["type"] == "approval" and e["dangerous"] for e in evs)  # siempre pregunta, aunque esté en Automático
    assert res.startswith("Editado") and "fullscreen=0" in ini.read_text()
    assert "fullscreen=1" in (ini.parent / "settings.ini.g3g3ai-original").read_text()
    # Desactivado: los juegos vuelven a ser intocables
    cfg.data.update(ai_game_write=False)
    err, _, _ = ToolContext(Files(cfg), cfg).precheck("edit_file", {"path": str(ini)})
    assert err and "Error" in err
    # Comandos fuera del aislamiento: siempre preguntan, con aviso
    monkeypatch.setattr(sandbox, "available", lambda cfg: True)
    _, strong, _ = ToolContext(Files(cfg), cfg).precheck("run_command", {"command": "flatpak install --user x", "unsandboxed": True})
    assert any("FUERA del aislamiento" in w for w in strong)



def test_build_exe_tool(env):
    import asyncio
    client, cfg, home, tmp = env
    from g3g3ai.files import Files
    from g3g3ai.tools import ToolContext, tool_events
    fake = _fake_exe(tmp, "python-dev", Path(__file__).parent / "fake_python.py")
    cfg.data.update(devenv_python=str(fake), ai_commands="auto", agent_workdir=str(home))
    ctx = ToolContext(Files(cfg), cfg, session_allow={"build_exe"})
    assert "build_exe" in ctx.names()
    assert "build_exe" in ctx.system_hint() and "PyInstaller" in ctx.system_hint()
    (home / "app.py").write_text("print('hola')\n")
    (home / "roto.py").write_text("syntax error (\n")

    async def build(args):
        evs, sink = [], []
        async for ev in tool_events(ctx, "build_exe", args, sink):
            evs.append(ev)
        return evs, sink[0]

    evs, res = asyncio.run(build({"script": str(home / "app.py"), "name": "Mi App"}))
    assert res.startswith("Ejecutable creado") and any(e["type"] == "file" for e in evs)
    exe = next(e["path"] for e in evs if e["type"] == "file")
    assert Path(exe).parent == home / "dist" and Path(exe).name.startswith("Mi_App")
    evs, res = asyncio.run(build({"script": str(home / "roto.py")}))
    assert res.startswith("Error") and "SyntaxError" in res
    # Instalar paquetes de internet siempre pide permiso, aunque se haya permitido «siempre»
    _, strong, _ = ctx.precheck("build_exe", {"script": str(home / "app.py"), "packages": ["requests"]})
    assert strong and "paquetes" in strong[0]
    err, _, _ = ctx.precheck("build_exe", {"script": str(tmp / "fuera.py")})
    assert err
    # Sin entorno de compilación la herramienta no se ofrece
    cfg.data.update(devenv_python=str(tmp / "no-existe"))
    assert "build_exe" not in ToolContext(Files(cfg), cfg).names()


def test_providers_export_requires_auth(env):
    client, cfg, home, tmp = env
    assert client.get("/api/providers/export").status_code == 401
    h = auth(cfg)
    s = client.get("/api/settings", headers=h).json()
    next(p for p in s["providers"] if p["id"] == "deepseek").update(enabled=True, api_key="sk-ds")
    client.put("/api/settings", headers=h, json=s)
    out = client.get("/api/providers/export", headers=h).json()
    assert [(p["id"], p["api_key"]) for p in out["providers"]] == [("deepseek", "sk-ds")]


def test_anthropic_request_shape(monkeypatch):
    """Claude actual rechaza temperature y necesita margen de max_tokens para razonar."""
    import asyncio, json
    import httpx
    from g3g3ai import providers
    sent = {}

    class FakeStream:
        def __init__(self, body): sent.update(body)
        async def __aenter__(self):
            lines = ['data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
                     'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hola"}}',
                     'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}']
            class R:
                status_code = 200
                async def aiter_lines(self):
                    for l in lines:
                        yield l
            return R()
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, m, url, json=None, headers=None: FakeStream(json))
    p = {"type": "anthropic", "base_url": "https://api.anthropic.com", "api_key": "x"}

    async def run():
        return [ev async for ev in providers.chat_stream(p, "claude-haiku-5-5", [{"role": "user", "content": "hola"}],
                                                          {"temperature": 0.7, "max_tokens": 2048})]
    evs = asyncio.run(run())
    assert "temperature" not in sent and sent["max_tokens"] >= 16000
    assert any(e["type"] == "content" and e["text"] == "hola" for e in evs)


def test_chat_does_not_stop_silently(env):
    """Respuestas cortadas por longitud se reanudan solas; si el modelo anuncia un paso y se para, se le pide que siga."""
    client, cfg, home, tmp = env
    h = auth(cfg)
    load_model(client, h)
    evs = sse(client.post("/api/chat", headers=h, json={"message": "escribe un texto largo"}))
    text = "".join(e["text"] for e in evs if e["type"] == "content")
    assert text == "primera parte, segunda parte."
    assert any(e["type"] == "status" and "longitud" in e["text"] for e in evs)
    evs = sse(client.post("/api/chat", headers=h, json={"message": "anuncia y para", "use_tools": True}))
    text = "".join(e["text"] for e in evs if e["type"] == "content")
    assert "Ahora leo el archivo principal." in text and text.endswith("Listo, ya lo he revisado.")
    assert any(e["type"] == "status" and "anunció" in e["text"] for e in evs)


def test_announces_action():
    from g3g3ai.providers import announces_action
    assert announces_action("Ya tengo el flujo. Leo las partes que voy a editar: el selector y el HTML.")
    assert announces_action("He leído providers.py. Ahora busco el resto de app.js")
    assert not announces_action("Listo, he cambiado el selector y he probado que funciona.")
    assert not announces_action("¿Quieres que lea también el HTML?")


def test_hardware_recommendations(env):
    """Recomendaciones para los equipos del usuario y endpoints."""
    from g3g3ai import hardware as H
    G = H.GB
    konkr = {"arch": "arm64", "ram": int(7.3 * G), "steamos": True, "cpu": {"cores": 8, "flags": ["asimddp", "i8mm"]},
             "gpus": [{"name": "Qualcomm Adreno", "vendor": "qualcomm", "dedicated": False, "vram": 0}]}
    laptop = {"arch": "x64", "ram": 24 * G, "cpu": {"name": "i5-11300H", "cores": 4, "flags": ["avx2", "avx512f"]},
              "gpus": [{"name": "Intel Iris Xe", "vendor": "intel", "dedicated": False, "vram": 0}]}
    xeon = {"arch": "x64", "ram": 8 * G, "cpu": {"name": "Xeon", "cores": 8, "flags": ["avx"]},
            "gpus": [{"name": "AMD Radeon RX 580", "vendor": "amd", "dedicated": True, "vram": 4 * G}]}
    r = H.recommend(konkr)
    assert r["main"]["tier"] == "3–4B" and r["main"]["where"] == "cpu" and r["settings"]["llama_gpu_layers"] == 0
    r = H.recommend(laptop)
    assert r["main"]["tier"].startswith("MoE") and r["engine"] == "cpu" and r["settings"]["llama_threads"] == 4
    assert any("AVX-512" in n for n in r["notes"])
    r = H.recommend(xeon)
    assert r["main"]["where"] == "gpu" and r["engine"] == "vulkan" and r["settings"]["llama_gpu_layers"] == 99
    assert "q8_0" in r["settings"]["llama_extra_args"] and any("AVX2" in n for n in r["notes"])
    assert H._gpu_kind("AMD Radeon(TM) Graphics") == ("amd", False)
    assert H._gpu_kind("NVIDIA GeForce RTX 3060") == ("nvidia", True)
    # Endpoints: detecta este equipo y aplica los ajustes recomendados
    client, cfg, home, tmp = env
    h = auth(cfg)
    d = client.get("/api/hardware", headers=h).json()
    assert d["hardware"]["ram"] > 0 and d["recommendation"]["settings"]["llama_threads"] >= 1
    applied = client.post("/api/hardware/apply", headers=h).json()["applied"]
    assert cfg["llama_threads"] == applied["llama_threads"] and cfg["llama_ctx"] == applied["llama_ctx"]


def _fake_ollama():
    """Servidor Ollama simulado en un hilo: version, tags, pull (con progreso), delete y la API OpenAI."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    models = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/version":
                return self._json({"version": "0.9.9"})
            if self.path == "/api/tags":
                return self._json({"models": [{"name": n, "size": 2_500_000_000,
                                               "details": {"parameter_size": "4B", "quantization_level": "Q4_K_M"}} for n in models]})
            if self.path == "/v1/models":
                return self._json({"data": [{"id": n} for n in models]})
            self._json({}, 404)

        def _body(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

        def do_POST(self):
            req = self._body()
            if self.path == "/api/pull":
                self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
                for line in ({"status": "pulling manifest"}, {"status": "downloading", "total": 100, "completed": 50},
                             {"status": "downloading", "total": 100, "completed": 100}, {"status": "success"}):
                    self.wfile.write((json.dumps(line) + "\n").encode())
                models.append(req["model"])
                return
            if self.path == "/v1/chat/completions":
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"hola desde ollama"},"finish_reason":"stop"}]}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")
                return
            self._json({}, 404)

        def do_DELETE(self):
            req = self._body()
            if req.get("model") in models:
                models.remove(req["model"])
                return self._json({})
            self._json({"error": "not found"}, 404)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, models


def test_ollama_integration(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    cfg.data.update(ollama_url=f"http://127.0.0.1:{free_port()}")  # nada escuchando
    d = client.get("/api/ollama", headers=h).json()
    assert d["running"] is False and d["suggestions"]["models"]
    srv, models = _fake_ollama()
    try:
        cfg.data.update(ollama_url=f"http://127.0.0.1:{srv.server_address[1]}")
        d = client.get("/api/ollama", headers=h).json()
        assert d["running"] and d["installed"] and d["version"] == "0.9.9" and d["models"] == []
        client.post("/api/ollama/pull", headers=h, json={"name": "qwen3:4b"})
        for _ in range(50):
            d = client.get("/api/ollama", headers=h).json()
            if d["job"]["status"] != "running":
                break
            time.sleep(0.05)
        assert d["job"]["status"] == "done" and d["job"]["completed"] == 100
        assert [m["name"] for m in d["models"]] == ["qwen3:4b"] and d["models"][0]["params"] == "4B"
        assert client.post("/api/ollama/pull", headers=h, json={"name": "mal nombre; rm"}).status_code == 400
        # Usarlo en el chat como proveedor
        assert client.post("/api/ollama/enable", headers=h, json={"enabled": True}).json()["enabled"]
        assert client.get("/api/providers/ollama/models", headers=h).json() == ["qwen3:4b"]
        evs = sse(client.post("/api/chat", headers=h, json={"provider": "ollama", "model": "qwen3:4b", "message": "hola"}))
        assert "hola desde ollama" in "".join(e["text"] for e in evs if e["type"] == "content")
        assert client.delete("/api/ollama/models", params={"name": "qwen3:4b"}, headers=h).status_code == 200
        assert client.get("/api/ollama", headers=h).json()["models"] == []
    finally:
        srv.shutdown()


FAKE_HF = [
    {"id": "unsloth/Qwen3-30B-A3B-GGUF", "downloads": 900000, "likes": 800, "lastModified": "2026-10-01T00:00:00Z",
     "tags": ["gguf", "text-generation"], "pipeline_tag": "text-generation"},
    {"id": "bartowski/Qwen2.5-VL-7B-Instruct-GGUF", "downloads": 50000, "likes": 90, "lastModified": "2026-05-01T00:00:00Z",
     "tags": ["gguf"], "pipeline_tag": "image-text-to-text"},
    {"id": "org/repo", "downloads": 10, "likes": 1, "tags": ["gguf"]},
]


def test_hub_search_enriched(env, monkeypatch):
    client, cfg, home, tmp = env
    h = auth(cfg)
    from g3g3ai import hub as hubmod
    seen = {}

    async def fake_list(self, query, sort, limit):
        seen.update(query=query, sort=sort)
        return FAKE_HF
    monkeypatch.setattr(hubmod.Hub, "_list_models", fake_list)
    res = client.get("/api/hub/search", params={"q": "qwen", "sort": "trending"}, headers=h).json()
    assert seen == {"query": "qwen", "sort": "trending"}
    moe, vl, local = res
    assert moe["moe"] and moe["params"] == 30 and moe["active"] == 3 and moe["est_gb"] > 15
    assert "vision" in vl["caps"] and vl["params"] == 7 and vl["url"].endswith("Qwen2.5-VL-7B-Instruct-GGUF")
    assert local["downloaded"] is True and moe["downloaded"] is False  # org/repo ya está en la carpeta de modelos
    from g3g3ai.hub import quant_info
    assert quant_info("Q4_K_M")[1] == 3 and quant_info("Q8_0")[1] > quant_info("Q3_K_S")[1]
    assert client.get("/api/hardware", headers=h).json()["recommendation"]["summary"]["budget_gb"] > 0


def test_model_favorites_and_hidden_are_saved_and_synced(env):
    client, cfg, home, tmp = env
    h = auth(cfg)
    before = cfg["settings_updated"] or 0
    r = client.put("/api/settings", headers=h, json={"model_favorites": ["openrouter::anthropic/claude-haiku-5.5"],
                                                      "model_hidden": ["openrouter::otro/modelo"]}).json()
    assert r["model_favorites"] == ["openrouter::anthropic/claude-haiku-5.5"] and r["model_hidden"] == ["openrouter::otro/modelo"]
    assert cfg["settings_updated"] > before  # cuenta como cambio de ajustes comunes: viaja con la sincronización
    from g3g3ai.sync import SYNC_KEYS
    assert {"model_favorites", "model_hidden"} <= set(SYNC_KEYS)
