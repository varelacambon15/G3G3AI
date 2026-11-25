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
                     "llama_server_path": str(fake), "llama_port": free_port(), "autoload_last_model": False})
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


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:  # noqa: BLE001  (sin el navegador de esta versión de Playwright)
        exe = os.environ.get("G3G3AI_CHROMIUM") or "/opt/pw-browsers/chromium"
        if os.path.exists(exe):
            return p.chromium.launch(executable_path=exe)
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

        # 3) Code: proyecto, comandos con / y atajos
        page.click("[data-view=code]")
        page.fill("#code-dir", str(Path(cfg["write_roots"][0]) / "proyecto"))
        page.click("#code-dir-set")
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

        # 5) La app sigue viva
        page.click("[data-view=chat]")
        assert page.is_visible("#input")
        browser.close()
    assert errors == [], errors
