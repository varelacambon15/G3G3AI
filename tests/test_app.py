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
    assert c["write_roots"] == ["/x/trabajo"] and c["config_version"] == 3
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
