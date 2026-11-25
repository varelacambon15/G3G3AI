"""Exportar una conversación a Markdown o HTML (sin dependencias externas).

Sólo se exporta el texto de los mensajes, el modelo que respondió y los nombres de
los adjuntos: nunca claves, tokens ni el resto del `meta`.
"""
from __future__ import annotations

import html
import re
import time
import unicodedata
from urllib.parse import quote

FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
MAX_TITLE = 80
FALLBACK = "conversacion"

_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f5f4ed; --panel: #fffdf8; --text: #24231f; --muted: #6f6c66; --border: #e2dfd4;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #1f1e1c; --panel: #272624; --text: #eae8e1; --muted: #a09c94; --border: #3a3835; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.62 -apple-system, "Segoe UI", Roboto, system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 36px 20px 64px; }
h1 { font-size: 26px; line-height: 1.25; margin: 0 0 6px; overflow-wrap: anywhere; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 28px; }
.msg { background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
  padding: 14px 16px; margin: 0 0 14px; }
.msg.user { border-left: 3px solid var(--text); }
.who { font-weight: 600; font-size: 12.5px; letter-spacing: .2px; color: var(--muted);
  text-transform: uppercase; margin-bottom: 6px; }
.content { white-space: pre-wrap; overflow-wrap: anywhere; }
.att { color: var(--muted); font-size: 13px; margin-top: 10px; }
@media print {
  body { background: #fff; color: #000; }
  main { max-width: none; padding: 0; }
  .msg { background: #fff; border-color: #ccc; page-break-inside: avoid; }
  .who, .att { color: #444; }
}
"""


def safe_title(title: str | None) -> str:
    """Título apto para un nombre de archivo: sin caracteres prohibidos y máx. 80."""
    name = FORBIDDEN.sub("", str(title or ""))
    name = re.sub(r"\s+", " ", name).strip()
    name = name[:MAX_TITLE].strip().rstrip(". ")
    return name or FALLBACK


def filename(title: str | None, fmt: str) -> str:
    return f"{safe_title(title)}.{'html' if fmt == 'html' else 'md'}"


def content_disposition(name: str) -> str:
    """Cabecera Content-Disposition con alternativa ASCII (las cabeceras HTTP no admiten cualquier carácter)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r'["\\\r\n]', "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip() or FALLBACK
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def _messages(conv: dict):
    for m in conv.get("messages") or []:
        if m.get("role") in ("user", "assistant"):
            yield m


def _model_of(conv: dict, msg: dict) -> str:
    meta = msg.get("meta") if isinstance(msg.get("meta"), dict) else {}
    model = meta.get("model") or (conv.get("model") if msg.get("role") == "assistant" else "")
    return str(model or "").strip()


def _attachments(msg: dict) -> list[str]:
    """Sólo los nombres de los adjuntos (sin rutas, contenido ni otras claves del meta)."""
    meta = msg.get("meta") if isinstance(msg.get("meta"), dict) else {}
    names = []
    for a in meta.get("attachments") or []:
        name = a.get("name") if isinstance(a, dict) else a
        if str(name or "").strip():
            names.append(str(name).strip())
    return names


def _when() -> str:
    return time.strftime("%d/%m/%Y a las %H:%M")


def to_markdown(conv: dict) -> str:
    title = str(conv.get("title") or "Conversación")
    out = [f"# {title}", "", f"*Exportado de G3G3AI el {_when()}*", ""]
    for m in _messages(conv):
        model = _model_of(conv, m)
        if m.get("role") == "user":
            head = "**Tú**"
        else:
            head = f"**G3G3AI** ({model})" if model else "**G3G3AI**"
        out += ["---", "", head, ""]
        content = str(m.get("content") or "").strip()
        if content:
            out += [content, ""]
        atts = _attachments(m)
        if atts:
            out += [f"📎 {a}" for a in atts]
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def to_html(conv: dict) -> str:
    esc = html.escape
    title = str(conv.get("title") or "Conversación")
    blocks = []
    for m in _messages(conv):
        model = _model_of(conv, m)
        if m.get("role") == "user":
            who, cls = "Tú", "msg user"
        else:
            who, cls = (f"G3G3AI · {model}" if model else "G3G3AI"), "msg assistant"
        content = str(m.get("content") or "").strip()
        atts = "".join(f'<div class="att">📎 {esc(a)}</div>' for a in _attachments(m))
        blocks.append(
            f'<section class="{cls}">\n<div class="who">{esc(who)}</div>\n'
            + (f'<div class="content">{esc(content)}</div>\n' if content else "")
            + (atts + "\n" if atts else "")
            + "</section>"
        )
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>{esc(title)}</h1>
<p class="sub">Exportado de G3G3AI el {esc(_when())}</p>
{chr(10).join(blocks)}
</main>
</body>
</html>
"""
