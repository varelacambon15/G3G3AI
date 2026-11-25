"""Exportación de conversaciones a Markdown y HTML."""
import re

from test_app import auth, env  # noqa: F401  (fixture y ayudante compartidos con el resto)


def new_conv(client, headers, title="Prueba de exportación"):
    r = client.post("/api/conversations", headers=headers, json={})
    assert r.status_code == 200
    c = r.json()
    # El título se cambia con PATCH (al crear siempre es «Nueva conversación»).
    r = client.patch(f"/api/conversations/{c['id']}", headers=headers, json={"title": title})
    assert r.status_code == 200
    return r.json()


def add_user(db, cid, text, attachments=None):
    meta = {"attachments": attachments or []}
    db.add_message(cid, "user", text, meta=meta)


def add_ai(db, cid, text, model="deepseek-chat"):
    db.add_message(cid, "assistant", text, None, {"model": model})


def test_export_markdown(env):
    client, cfg, *_ = env
    h = auth(cfg)
    c = new_conv(client, h)
    db = client.app.state.db
    add_user(db, c["id"], "Hola, ¿qué es G3G3AI?", [{"name": "informe.pdf", "path": "/documentos/informe.pdf",
                                                      "kind": "document"}])
    add_ai(db, c["id"], "Es un cliente de IA para tu PC y tu móvil.")

    r = client.get(f"/api/conversations/{c['id']}/export?format=md", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    cd = r.headers["content-disposition"]
    assert "attachment" in cd and ".md" in cd
    text = r.text
    assert text.startswith("# Prueba de exportación")
    assert "**Tú**" in text and "Hola, ¿qué es G3G3AI?" in text
    assert "**G3G3AI** (deepseek-chat)" in text
    assert "Es un cliente de IA para tu PC y tu móvil." in text
    assert "📎 informe.pdf" in text


def test_export_html_escapes_and_hides_secrets(env):
    client, cfg, *_ = env
    h = auth(cfg)
    c = new_conv(client, h)
    db = client.app.state.db
    add_user(db, c["id"], '<script>alert("xss")</script> y <b>negrita</b>')
    add_ai(db, c["id"], "Respuesta sin scripts.")

    # Una clave API guardada en el equipo no puede acabar en la exportación.
    s = client.get("/api/settings", headers=h).json()
    op = next(p for p in s["providers"] if p["id"] == "openai")
    op["api_key"] = "sk-export-secreto-123"; op["enabled"] = True
    client.put("/api/settings", headers=h, json=s)
    assert cfg.provider("openai")["api_key"] == "sk-export-secreto-123"

    r = client.get(f"/api/conversations/{c['id']}/export?format=html", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert body.lstrip().lower().startswith("<!doctype html>")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "<b>negrita</b>" not in body
    assert "Respuesta sin scripts." in body
    assert "prefers-color-scheme: dark" in body  # legible en claro y oscuro
    assert "http://" not in body and "https://" not in body  # sin recursos externos
    assert "sk-export-secreto-123" not in body
    assert cfg["token"] not in body


def test_export_unknown_conversation_404(env):
    client, cfg, *_ = env
    h = auth(cfg)
    r = client.get("/api/conversations/no-existe/export?format=md", headers=h)
    assert r.status_code == 404


def test_export_sanitizes_filename(env):
    client, cfg, *_ = env
    h = auth(cfg)
    title = 'Ventas: 2026 / Q1 *raro*? "x" <y> | fin' + "z" * 100
    c = new_conv(client, h, title=title)
    for fmt in ("md", "html"):
        r = client.get(f"/api/conversations/{c['id']}/export?format={fmt}", headers=h)
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        name = re.search(r'filename="([^"]+)"', cd).group(1)
        assert name.endswith("." + fmt)
        for ch in '/\\:*?"<>|':
            assert ch not in name
        assert len(name) <= 80 + len(fmt) + 1
