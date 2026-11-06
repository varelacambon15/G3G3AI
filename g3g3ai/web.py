"""Búsqueda web y lectura de páginas para la IA.

- web_search: DuckDuckGo (sin clave), Brave Search o Tavily (con clave, más fiables).
- fetch_url: descarga una página y extrae su texto. Por seguridad no accede a la red local
  (127.0.0.1, 192.168.x.x…), para que una página no pueda hacer que la IA toque tus dispositivos.
"""
from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36 G3G3AI")
MAX_BYTES = 3_000_000
TEXT_LIMIT = 25_000


class WebError(Exception):
    pass


# --- Búsqueda -----------------------------------------------------------------------
def parse_duckduckgo(page: str, limit: int) -> list[dict]:
    out = []
    blocks = re.split(r'<div[^>]+class="[^"]*result[ _][^"]*results_links', page)
    for b in blocks[1:]:
        a = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not a:
            continue
        href = html.unescape(a.group(1))
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/y.js" in href:  # anuncios
            continue
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</(a|div|td)>', b, re.S)
        out.append({"title": _strip(a.group(2)), "url": href, "snippet": _strip(snip.group(1)) if snip else ""})
        if len(out) >= limit:
            break
    return out


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


async def search(cfg, query: str, limit: int = 8) -> list[dict]:
    provider = cfg["web_provider"] or "duckduckgo"
    key = cfg["web_api_key"] or ""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as c:
        if provider == "brave":
            if not key:
                raise WebError("Falta la clave de Brave Search (Ajustes → Búsqueda web).")
            r = await c.get("https://api.search.brave.com/res/v1/web/search",
                            params={"q": query, "count": limit},
                            headers={"X-Subscription-Token": key, "Accept": "application/json"})
            r.raise_for_status()
            return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": _strip(x.get("description", ""))}
                    for x in r.json().get("web", {}).get("results", [])[:limit]]
        if provider == "tavily":
            if not key:
                raise WebError("Falta la clave de Tavily (Ajustes → Búsqueda web).")
            r = await c.post("https://api.tavily.com/search",
                             json={"query": query, "max_results": limit},
                             headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")[:400]}
                    for x in r.json().get("results", [])[:limit]]
        r = await c.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "es-es"})
        r.raise_for_status()
        results = parse_duckduckgo(r.text, limit)
        if not results and ("anomaly" in r.text or "captcha" in r.text.lower()):
            raise WebError("DuckDuckGo ha bloqueado la búsqueda temporalmente. Configura Brave o Tavily en Ajustes.")
        return results


def format_results(query: str, results: list[dict]) -> str:
    if not results:
        return f"Sin resultados para «{query}»."
    lines = [f"Resultados para «{query}»:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    lines.append("\nUsa fetch_url para leer una página y cita las fuentes con su enlace.")
    return "\n".join(lines)


# --- Lectura de páginas ---------------------------------------------------------------
def _is_public_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
                or a.is_unspecified or getattr(a, "is_site_local", False))


async def check_public(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise WebError("Sólo se pueden abrir direcciones http(s).")
    host = u.hostname
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".lan", ".internal", ".home")):
        raise WebError("Por seguridad, la IA no puede acceder a tu red local.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, u.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise WebError(f"No se encuentra el dominio {host}") from e
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise WebError("Por seguridad, la IA no puede acceder a tu red local.")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
             "header", "footer", "blockquote", "pre", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("#" * int(tag[1]) + " ")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def html_to_text(page: str) -> tuple[str, str]:
    p = _Text()
    try:
        p.feed(page)
    except Exception:  # noqa: BLE001 — HTML roto: devolvemos lo que haya
        pass
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return p.title.strip(), text.strip()


async def fetch(url: str) -> str:
    async def hook(request: httpx.Request):
        await check_public(str(request.url))  # también en cada redirección

    async with httpx.AsyncClient(timeout=httpx.Timeout(20, read=30), follow_redirects=True,
                                 headers={"User-Agent": UA, "Accept-Language": "es,en;q=0.8"},
                                 event_hooks={"request": [hook]}) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "").lower()
            body = b""
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            final = str(r.url)
    if "pdf" in ctype:
        return f"URL: {final}\n(Es un PDF; no se puede leer como texto desde aquí. Descárgalo con run_command si lo necesitas.)"
    if not any(t in ctype for t in ("html", "text", "json", "xml")) and ctype:
        return f"URL: {final}\n(Tipo de contenido no legible: {ctype})"
    text = body.decode(r.encoding or "utf-8", errors="replace")
    title = ""
    if "html" in ctype or "<html" in text[:2000].lower():
        title, text = html_to_text(text)
    cut = ""
    if len(text) > TEXT_LIMIT:
        text, cut = text[:TEXT_LIMIT], "\n\n[... página recortada ...]"
    return f"Título: {title}\nURL: {final}\n\n{text}{cut}"
