"""Prueba del «Chat directo» de la app de Android (la página empaquetada en la APK) en un navegador real.

El puente nativo de la app (window.G3Native) se simula: responde a /models y hace streaming de /chat/completions.
Se omite si Playwright no está instalado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIRECT = ROOT / "android/app/src/main/assets/direct"


def test_android_catalog_is_in_sync_with_desktop():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_android_catalog
    assert (DIRECT / "catalog.js").read_text(encoding="utf-8") == gen_android_catalog.render(), \
        "Ejecuta: python scripts/gen_android_catalog.py"


BRIDGE = r"""
window.__reqs = [];
window.G3Native = {
  request(id, method, url, headers, body) {
    window.__reqs.push({ method, url, headers: JSON.parse(headers || "{}"), body: body ? JSON.parse(body) : null });
    const send = (k, d) => setTimeout(() => window.__g3net(id, k, d), 5);
    if (url.endsWith("/models")) {
      const key = JSON.parse(headers).Authorization || "";
      if (key.includes("mala")) { send("status", 401); send("line", '{"error":{"message":"bad key"}}'); send("end"); return; }
      send("status", 200); send("line", JSON.stringify({ data: [{ id: "glm-5" }, { id: "kimi-k3" }] })); send("end"); return;
    }
    send("status", 200);
    const words = ["Hola, ", "soy ", "una ", "respuesta ", "**en streaming**."];
    words.forEach((w, i) => setTimeout(() => window.__g3net(id, "line", "data: " + JSON.stringify({ choices: [{ delta: { content: w } }] })), 10 * (i + 1)));
    setTimeout(() => { window.__g3net(id, "line", "data: [DONE]"); window.__g3net(id, "end"); }, 80);
  },
  abort() {}, getStore(k) { return localStorage.getItem("ns:" + k) || ""; },
  setStore(k, v) { localStorage.setItem("ns:" + k, v); }, getServers() { return "[]"; },
};
"""


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:  # noqa: BLE001
        exe = os.environ.get("G3G3AI_CHROMIUM") or "/opt/pw-browsers/chromium"
        if os.path.exists(exe):
            return p.chromium.launch(executable_path=exe)
        pytest.skip("No hay navegador de Playwright instalado")


def test_android_direct_chat_flow():
    pw = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with pw.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(BRIDGE)
        page.goto((DIRECT / "index.html").as_uri())
        # Sin proveedores: la bienvenida invita a configurar uno
        page.wait_for_selector(".empty >> text=Configurar un proveedor")
        assert page.locator("#send svg").count() == 1 and "☰" not in page.inner_text(".top")      # iconos, sin emojis
        page.click(".empty .primary")
        page.wait_for_selector("#settings:not(.hidden)")
        names = page.eval_on_selector_all("details.prov summary b", "els => els.map(e => e.textContent)")
        assert "OpenCode Go" in names and "OpenRouter" in names and len(names) >= 18
        page.fill("#prov-search", "opencode go")
        assert page.eval_on_selector_all("details.prov summary b", "els => els.map(e => e.textContent)") == ["OpenCode Go"]
        page.click("details.prov summary")
        assert page.is_visible("details.prov >> text=Conseguir una clave")
        # Clave mala → error claro; clave buena → funciona
        page.fill("details.prov input[type=password]", "sk-mala")
        page.click("details.prov button:has-text('Probar')")
        page.wait_for_selector("details.prov .test-out.error >> text=clave incorrecta")
        page.fill("details.prov input[type=password]", "sk-buena")
        page.click("details.prov button:has-text('Probar')")
        page.wait_for_selector("details.prov .test-out.ok >> text=2 modelos")
        assert page.is_checked("details.prov[open] .toggle input")                       # queda activado a la vista
        page.click("#settings-save")
        page.wait_for_selector("#settings.hidden", state="attached")
        page.wait_for_selector("#model option[value='opencode-go::glm-5']", state="attached")
        # Bienvenida con sugerencias y envío con streaming
        page.wait_for_selector(".empty .ideas button")
        page.fill("#input", "Hola")
        page.click("#send")
        page.wait_for_selector(".msg.assistant .bubble strong >> text=en streaming")
        req = [r for r in page.evaluate("window.__reqs") if r["url"].endswith("/chat/completions")][-1]
        assert req["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
        assert req["headers"]["Authorization"] == "Bearer sk-buena" and req["body"]["model"] == "glm-5"
        # Regenerar y editar
        page.wait_for_function("!document.querySelector('#send').classList.contains('stop')")
        page.click(".msg.assistant .meta button[aria-label='Volver a generar']")
        page.wait_for_function("document.querySelectorAll('.msg.assistant').length === 1 && !document.querySelector('#send').classList.contains('stop')")
        page.click(".msg.user .meta button[aria-label='Editar']")
        assert page.input_value("#input") == "Hola" and page.locator(".msg").count() == 0
        # La conversación quedó guardada y se puede buscar
        page.click("#menu")
        page.fill("#conv-search", "zzz-nada")
        page.wait_for_selector("#convs >> text=Sin resultados")
        browser.close()
    assert errors == [], errors


def test_android_decrypts_cloud_copy_made_by_the_pc():
    """El chat directo descifra en el móvil el archivo que el PC deja en OneDrive / Google Drive."""
    import json
    from g3g3ai import cloudsync
    doc = {"app": "g3g3ai", "changes": {"settings": {"values": {"providers": [
        {"id": "deepseek", "name": "DeepSeek", "type": "openai", "base_url": "https://api.deepseek.com", "api_key": "sk-nube-1", "enabled": True}]}}}}
    data = list(cloudsync._seal(json.dumps(doc).encode(), "secreto-largo"))
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        page.add_init_script(BRIDGE)
        page.goto((DIRECT / "index.html").as_uri())
        got = page.evaluate("async (d) => (await decryptCloud(new Uint8Array(d), 'secreto-largo')).changes.settings.values.providers[0].api_key", data)
        assert got == "sk-nube-1"
        err = page.evaluate("async (d) => { try { await decryptCloud(new Uint8Array(d), 'otra'); return 'ok'; } catch (e) { return e.message; } }", data)
        assert err == "contraseña incorrecta"
        browser.close()


BRIDGE_GO = r"""
window.__reqs = [];
window.__opened = 0;
window.G3Native = {
  openServers() { window.__opened++; },
  request(id, method, url, headers, body) {
    window.__reqs.push({ method, url });
    const send = (k, d) => setTimeout(() => window.__g3net(id, k, d), 5);
    if (url.endsWith("/models")) {
      send("status", 200);
      send("line", JSON.stringify({ data: [{ id: "glm-5.3-flash", name: "GLM-5.3-Flash", description: "Rápido y barato",
        limit: { context: 1000000 }, modalities: { input: ["text", "image/png"] },
        cost: { text: { input: { price: 0.15, cache: { read: 0.03 } }, output: { price: 0.5 } } },
        go: { monthly_usage: { go: 60 }, zdr: true } }] }));
      send("end"); return;
    }
    if (url.endsWith("/usage")) {
      send("status", 200);
      send("line", JSON.stringify({ usage: { rolling: { status: "ok", percent: 34, resetsAt: new Date(Date.now() + 3 * 3600e3).toISOString() },
        weekly: { status: "ok", percent: 72, resetsAt: new Date(Date.now() + 3 * 86400e3).toISOString() },
        monthly: { status: "ok", percent: 41, resetsAt: new Date(Date.now() + 12 * 86400e3).toISOString() } } }));
      send("end"); return;
    }
    send("status", 200);
    setTimeout(() => window.__g3net(id, "line", "data: " + JSON.stringify({ choices: [{ delta: { content: "Hecho." } }] })), 10);
    setTimeout(() => window.__g3net(id, "line", "data: " + JSON.stringify({ choices: [], usage: { cost: 0, opencode: { allowance: 0.0123 } } })), 20);
    setTimeout(() => { window.__g3net(id, "line", "data: [DONE]"); window.__g3net(id, "end"); }, 40);
  },
  abort() {}, getStore(k) { return localStorage.getItem("ns:" + k) || ""; },
  setStore(k, v) { localStorage.setItem("ns:" + k, v); }, getServers() { return "[]"; },
};
localStorage.setItem("ns:providers", JSON.stringify([{ id: "opencode-go", name: "OpenCode Go", type: "openai",
  base_url: "https://opencode.ai/zen/go/v1", api_key: "sk-go", enabled: true }]));
localStorage.setItem("ns:settings", JSON.stringify({ system: "", temperature: "0.7", max_tokens: "2048" }));
"""


def test_android_direct_pins_favorites_usage_and_model_info():
    pw = pytest.importorskip("playwright.sync_api")
    errors: list[str] = []
    with pw.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(BRIDGE_GO)
        page.goto((DIRECT / "index.html").as_uri())
        page.wait_for_selector("#model option[value='opencode-go::glm-5.3-flash']", state="attached")
        assert "$0.15/$0.50" in page.inner_text("#model")                       # el precio, en el propio selector
        # Uso del plan de OpenCode Go (5 h / semana / mes) en la cabecera
        page.wait_for_selector("#usage-chip:not(.hidden)")
        assert page.inner_text("#usage-chip") == "72 %" and page.get_attribute("#usage-chip", "data-level") == "high"
        page.click("#usage-chip")
        page.wait_for_selector(".sheet >> text=5 horas")
        assert page.locator(".sheet .meter").count() == 3 and "Semana" in page.inner_text(".sheet")
        page.click(".sheet >> text=Cerrar")
        # Ficha del modelo
        page.click("#model-info")
        page.wait_for_selector(".sheet >> text=Rápido y barato")
        sheet = page.inner_text(".sheet")
        assert "$0.15" in sheet and "1 M tokens" in sheet and "$60/mes" in sheet and "no guarda tus datos" in sheet
        page.click(".sheet >> text=Cerrar")
        # Dos conversaciones: respuesta con el cupo descontado, exportar, fijar y favoritas
        for txt in ("primera", "segunda"):
            page.fill("#input", txt)
            page.click("#send")
            page.wait_for_selector(".msg.assistant .bubble >> text=Hecho.")
            page.wait_for_function("!document.querySelector('#send').classList.contains('stop')")
            page.click("#menu")
            page.click("#new-chat")
        page.click("#menu")
        convs = page.locator("#convs .conv")
        assert convs.count() == 2
        oldest = convs.nth(1).inner_text()
        convs.nth(1).locator("button[aria-label='Fijar arriba']").click()
        page.wait_for_selector("#convs .conv-group >> text=Fijadas")
        assert page.locator("#convs .conv").first.inner_text() == oldest        # la fijada, arriba
        page.locator("#convs .conv").nth(1).locator("button[aria-label='Marcar como favorita']").click()
        page.click("#fav-filter")
        page.wait_for_function("document.querySelectorAll('#convs .conv').length === 1")
        page.click("#fav-filter")
        page.click("#convs .conv >> nth=0")
        assert "cupo" in page.inner_text(".msg.assistant .meta")                  # cupo descontado por la respuesta
        page.wait_for_selector("#export-btn:not(.hidden)")
        page.click("#menu")
        page.click("#to-pc")
        assert page.evaluate("window.__opened") == 1                              # vuelve a la lista de equipos
        browser.close()
    assert errors == [], errors
