"""Prueba de la interfaz en un navegador real (Playwright): recorre las vistas, envía un mensaje y usa Code.

Se omite si Playwright o el navegador no están instalados (pip install playwright && playwright install chromium).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("G3G3AI_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("G3G3AI_DATA_DIR", str(tmp_path / "data"))
    for m in [m for m in sys.modules if m.startswith("g3g3ai")]:
        del sys.modules[m]
    import uvicorn
    from g3g3ai.config import Config
    from g3g3ai.server import create_app

    home = tmp_path / "home"; home.mkdir()
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
                     "onboarded": True})
    cfg.save()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(cfg), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", cfg
    server.should_exit = True
    t.join(timeout=10)


def launch(p, **kw):
    try:
        return p.chromium.launch(**kw)
    except Exception:  # noqa: BLE001  (sin el navegador de esta versión de Playwright)
        exe = os.environ.get("G3G3AI_CHROMIUM") or "/opt/pw-browsers/chromium"
        if os.path.exists(exe):
            return p.chromium.launch(executable_path=exe, **kw)
        pytest.skip("No hay navegador de Playwright instalado")


def test_ui_end_to_end(live):
    base, cfg = live
    errors: list[str] = []
    with playwright_sync.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base}/?token={cfg['token']}")
        page.wait_for_selector("#input")

        # 1) Todas las vistas se abren; el panel de Code sólo se ve en Code
        for view, marker in (("chat", "#messages"), ("code", "#code-panel"), ("models", "#view-models"),
                             ("tasks", "#task-form"), ("files", "#view-files"), ("settings", "#settings-form")):
            page.click(f"[data-view={view}]")
            page.wait_for_selector(marker, state="visible", timeout=5000)
            assert page.is_visible("#code-panel") == (view == "code"), view
        # Ajustes por pestañas: cada sección muestra sólo lo suyo
        page.click("#settings-tabs [data-stab=data]")
        page.wait_for_selector("#usage-box >> text=Este mes", timeout=5000)     # Uso y coste
        assert page.is_visible("#bk-export")                                      # Copia de seguridad
        assert not page.is_visible("#mail-box")
        page.click("#settings-tabs [data-stab=mail]")
        page.wait_for_selector("#mail-box >> text=La IA puede buscar en mi correo", timeout=5000)   # Correo
        assert not page.is_visible("#usage-box")
        page.click("#settings-tabs [data-stab=general]")
        assert page.is_visible("#settings-form [name=temperature]") and not page.is_visible("#settings-form [name=port]")
        # Buscador de ajustes: encuentra opciones de cualquier pestaña (también avanzadas), sin acentos
        page.fill("#settings-search", "puerto")
        assert page.is_visible("#settings-form [name=port]") and not page.is_visible("#settings-form [name=temperature]")
        page.fill("#settings-search", "temperatura")
        assert page.is_visible("#settings-form [name=temperature]") and page.is_visible("#settings-form [name=agent_temperature]")
        page.fill("#settings-search", "correo")
        assert page.is_visible("#mail-box") and not page.is_visible("#usage-box")
        page.fill("#settings-search", "copia de seguridad")
        assert page.is_visible("#bk-export")
        page.fill("#settings-search", "zzqqxx")
        assert page.is_visible("#settings-noresults")
        page.press("#settings-search", "Escape")
        assert page.input_value("#settings-search") == "" and page.is_visible("#settings-form [name=temperature]")
        # Los ajustes se guardan solos al cambiarlos
        page.fill("#settings-form [name=temperature]", "0.42")
        page.dispatch_event("#settings-form [name=temperature]", "change")
        page.wait_for_selector("#save-state[data-state=saved]", timeout=5000)
        assert page.evaluate("async () => (await (await fetch('/api/settings')).json()).temperature") == 0.42

        # 2) Cargar el modelo falso y mantener una conversación (con corte por longitud y continuación automática)
        page.evaluate("""async () => {
            const ms = await (await fetch('/api/models/local')).json();
            await fetch('/api/llama/load', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                            body: JSON.stringify({path: ms.find(m => !m.mmproj).path})});
        }""")
        for _ in range(60):
            if page.evaluate("async () => (await (await fetch('/api/llama/status')).json()).state") == "ready":
                break
            time.sleep(0.25)
        page.reload()
        page.wait_for_selector("#model-select option", state="attached")
        page.click("[data-view=chat]")
        page.fill("#input", "escribe un texto largo")
        page.click("#send-btn")
        page.wait_for_function("document.querySelector('#send-btn').dataset.state === 'idle'", timeout=15000)
        page.wait_for_selector(".msg.assistant .bubble >> text=primera parte, segunda parte.", timeout=5000)
        page.wait_for_selector("#ctx-meter:not(.hidden)", timeout=5000)           # medidor de contexto

        # 2a) Exportar la conversación
        page.click("#top-export")
        with page.expect_download() as dl:
            page.click(".export-opt[data-fmt=md]")
        assert dl.value.suggested_filename.endswith(".md")
        assert "## Tú" in Path(dl.value.path()).read_text(encoding="utf-8")

        # 2c) Buscar dentro de las conversaciones: encuentra texto de la respuesta y abre el mensaje resaltado
        page.click("#new-chat")
        page.fill("#conv-search", "segunda parte")
        page.wait_for_selector("#conv-list .search-hit mark")
        page.click("#conv-list .search-hit")
        page.wait_for_selector("#messages .msg.assistant mark")
        page.fill("#conv-search", "")
        page.dispatch_event("#conv-search", "input")

        # 2d) Proyectos: crear, poner instrucciones y conversar dentro (la IA las recibe)
        page.click("[data-view=projects]")
        page.wait_for_selector("text=Crear el primero")
        page.once("dialog", lambda d: d.accept("Nóminas"))
        page.click("text=Crear el primero")
        page.wait_for_selector(".proj-name")
        page.fill(".proj-cols textarea", "Instrucción secreta PROJ-77")
        page.dispatch_event(".proj-cols textarea", "change")
        page.wait_for_selector("#toast >> text=Guardado")
        page.click(".proj-head .primary")
        page.wait_for_selector("#project-chip >> text=Nóminas")
        page.fill("#input", "eco del sistema")
        page.click("#send-btn")
        page.wait_for_selector(".msg.assistant .bubble >> text=PROJ-77", timeout=10000)
        page.click("#project-chip")
        page.wait_for_selector(".proj-conv >> text=eco del sistema")
        page.click("[data-view=chat]")

        # 2e) Piezas: la página y el diagrama salen como tarjetas y el último se abre al lado
        page.click("#new-chat")
        page.fill("#input", "haz una pagina")
        page.click("#send-btn")
        page.wait_for_selector(".art-card >> text=Calculadora de horas", timeout=10000)
        page.wait_for_selector("#artifact:not(.hidden) #artifact-title >> text=Diagrama de flujo", timeout=10000)
        assert page.inner_text("#artifact-vn") == "2 / 2"
        page.wait_for_function("document.querySelector('#artifact-frame').srcdoc.includes('<svg')", timeout=10000)
        page.click("#artifact-prev")
        page.wait_for_selector("#artifact-title >> text=Calculadora de horas")
        assert "Fila 17" in page.eval_on_selector("#artifact-frame", "f => f.srcdoc")
        page.click("#artifact-close")

        # 2f) Un error queda en la conversación con su causa (no sólo en un aviso que desaparece)
        page.click("#new-chat")
        page.fill("#input", "error a mitad")
        page.click("#send-btn")
        page.wait_for_selector("#chat-error >> text=upstream exploded", timeout=10000)
        assert page.is_visible("#chat-error >> text=Reintentar")

        # 2g) Paleta de comandos Ctrl+K: buscar y saltar
        page.keyboard.press("Control+k")
        page.wait_for_selector("#palette input")
        page.keyboard.type("ir a modelos")
        page.keyboard.press("Enter")
        page.wait_for_selector("#view-models.active")
        page.keyboard.press("Control+k")
        page.keyboard.type("segunda parte")
        page.wait_for_selector("#palette >> text=En los mensajes")
        page.keyboard.press("Escape")
        page.click("[data-view=chat]")

        # 2h) «Compartir con G3G3AI» desde Android: texto y archivos al cuadro, sin enviar
        page.evaluate("""() => window.g3Share({text: 'Mira esto', files: [{name: 'nota.txt', mime: 'text/plain', data: btoa('hola')}]})""")
        page.wait_for_selector("#attachments >> text=nota.txt", timeout=5000)
        assert page.input_value("#input") == "Mira esto"
        page.evaluate("() => { S.attachments = []; renderAttachments(); }")
        page.fill("#input", "")

        # 2b) Selector de modelos con buscador
        page.click("#model-btn")
        page.wait_for_selector("#model-picker .mp-row")
        page.fill("#model-picker input", "zzzz-no-existe")
        page.wait_for_selector("#model-picker >> text=Ningún modelo coincide")
        page.fill("#model-picker input", "local")
        page.wait_for_selector("#model-picker .mp-row.hi")
        page.keyboard.press("Enter")
        assert not page.is_visible("#model-picker")
        assert page.input_value("#model-select") == "local::local"
        page.keyboard.press("Control+Shift+M")
        page.wait_for_selector("#model-picker")
        page.keyboard.press("Escape")
        assert not page.is_visible("#model-picker")

        # 3) Code: proyecto, comandos con / y atajos
        page.click("[data-view=code]")
        page.fill("#code-dir", str(Path(cfg["write_roots"][0]) / "proyecto"))
        page.click("#code-dir-set")
        page.click("#code-dir-pick")                                   # elegir carpeta navegando
        page.wait_for_selector("#picker-use-dir:visible")
        page.click("#picker-use-dir")
        assert page.input_value("#code-dir") != ""
        page.fill("#input", "/help")
        page.click("#send-btn")
        page.wait_for_selector("#toast >> text=/compact", timeout=3000)
        page.click("#input")
        page.keyboard.press("Shift+Tab")
        assert page.eval_on_selector("#mode-select", "e => e.value") == "edits"
        for tab, text in (("term", "Los comandos"), ("plan", "plan"), ("changes", "cambios")):
            page.click(f"[data-ctab={tab}]")
            assert text in page.inner_text(f"#ctab-{tab}")

        # 4) Tareas programadas: crear una desde el formulario y verla en la lista
        page.click("[data-view=tasks]")
        page.fill("#task-form [name=name]", "Prueba UI")
        page.fill("#task-form [name=prompt]", "Resume el estado del proyecto")
        page.select_option("#task-form [name=kind]", "interval")
        page.fill("#task-form [name=when]", "30")
        page.click("#task-form button.primary")
        page.wait_for_selector("#task-list >> text=Prueba UI", timeout=5000)
        page.wait_for_selector("#task-list >> text=cada 30 min", timeout=5000)
        page.fill("#task-form [name=name]", "Laborables")
        page.fill("#task-form [name=prompt]", "Revisa el correo")
        page.select_option("#task-form [name=kind]", "daily")
        page.click(".day-chip[title=sábado]"); page.click(".day-chip[title=domingo]")
        page.click("#task-form button.primary")
        page.wait_for_selector("#task-list >> text=de lunes a viernes", timeout=5000)

        # 5) La app sigue viva
        page.click("[data-view=chat]")
        assert page.is_visible("#input")
        browser.close()
    assert errors == [], errors


def test_first_run_wizard_and_check_everything(live):
    base, cfg = live
    cfg.set("onboarded", False)
    errors: list[str] = []
    with playwright_sync.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_context(viewport={"width": 1100, "height": 800}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base}/?token={cfg['token']}")
        # Sin nada configurado, el asistente se abre solo
        page.wait_for_selector("#wizard[open] >> text=¿Con qué IA quieres trabajar?", timeout=8000)
        assert page.is_visible("#wizard >> text=En la nube") and page.is_visible("#wizard >> text=En este equipo")
        page.click("#wizard .wiz-nav .primary")                                   # → carpetas
        page.wait_for_selector("#wizard >> text=¿Dónde puede trabajar?")
        folder = str(Path(cfg["write_roots"][0]) / "Trabajo IA")
        page.fill("#wizard .wiz-body input", folder)
        page.click("#wizard button:has-text('Usar esta carpeta')")
        page.wait_for_selector("#wizard .wiz-body .ok >> text=Listo")
        assert Path(folder).is_dir() and folder in cfg["write_roots"]
        page.click("#wizard .wiz-nav .primary")                                   # → correo
        page.wait_for_selector("#wizard >> text=¿Quieres que busque en tu correo?")
        page.click("#wizard .wiz-nav .primary")                                   # → comprobación
        page.wait_for_selector("#wizard .diag-summary", timeout=60000)
        assert page.locator("#wizard .diag").count() >= 6
        page.click("#wizard .wiz-nav .primary")                                   # Empezar
        page.wait_for_selector("#wizard", state="hidden")
        assert cfg["onboarded"] is True
        # «Comprobar todo» desde Ajustes, con botón que lleva a donde se arregla
        page.click("[data-view=settings]")
        page.click("#open-diag")
        page.wait_for_selector("#diag-dialog .diag-summary", timeout=60000)
        page.click("#diag-dialog .diag button:has-text('Abrir proveedores')")
        page.wait_for_selector("#settings-tabs [data-stab=providers].active")
        browser.close()
    assert errors == [], errors


def test_team_view(live):
    base, cfg = live
    errors: list[str] = []
    with playwright_sync.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_context(viewport={"width": 1280, "height": 820}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base}/?token={cfg['token']}")
        page.click("[data-view=team]")
        page.wait_for_selector(".tnode.dir >> text=G3G3AI")
        assert page.is_visible(".tnode.ext >> text=Claude Code")                   # el director externo, arriba
        page.click("#team-templates button:has-text('Investigador')")
        page.click("#team-templates button:has-text('Revisor')")
        assert page.locator(".tnode.mem").count() == 2 and page.is_checked("#team-enabled")
        assert page.locator(".tlines path").count() == 3                            # Claude→G3G3AI y G3G3AI→cada miembro
        page.fill("#team-editor input", "Revisora")                                 # editar el seleccionado (Revisor)
        page.wait_for_selector(".tnode.mem >> text=Revisora")
        assert page.evaluate("document.activeElement.tagName") == "INPUT"           # se puede seguir escribiendo
        page.click("#team-save")
        page.wait_for_selector("#toast >> text=Equipo guardado")
        assert [m["name"] for m in cfg["team"]["members"]] == ["Investigador", "Revisora"] and cfg["team"]["enabled"]
        page.click(".tnode.ext")
        page.wait_for_selector("#team-editor >> text=claude mcp add")
        page.click(".tnode.mem >> text=Investigador")
        page.click("#team-editor button:has-text('Quitar del equipo')")
        assert page.locator(".tnode.mem").count() == 1
        browser.close()
    assert errors == [], errors


@pytest.mark.skipif(sys.platform == "win32", reason="el whisper-cli falso es un script de shell")
def test_voice_dictation_with_fake_microphone(live, tmp_path):
    url, cfg = live
    from g3g3ai import voice
    fake = tmp_path / "whisper-cli"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {Path(__file__).parent / 'fake_whisper.py'} \"$@\"\n")
    fake.chmod(0o755)
    cfg.set("voice_binary", str(fake))
    m = voice.model_dir(cfg) / voice.DEFAULT_MODEL
    m.parent.mkdir(parents=True, exist_ok=True); m.write_bytes(b"\0" * 1_100_000)
    with playwright_sync.sync_playwright() as p:
        browser = launch(p, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.goto(url)
        page.wait_for_selector("#model-select option", state="attached")
        page.fill("#input", "Texto previo")
        page.click("#mic-btn")
        page.wait_for_selector("#mic-btn[data-state=rec]")
        time.sleep(1.2)
        page.click("#mic-btn")                                   # detener → WAV 16 kHz → whisper (falso)
        page.wait_for_function("document.querySelector('#input').value.includes('hola desde whisper')", timeout=10000)
        assert page.input_value("#input").startswith("Texto previo hola desde whisper (auto, ")
        assert page.get_attribute("#mic-btn", "data-state") == ""
        page.click("#mic-btn", button="right")                   # clic derecho: configuración
        page.wait_for_selector("dialog >> text=Dictado por voz")
        assert page.is_visible("text=Listo: se transcribe en este equipo")
        browser.close()
