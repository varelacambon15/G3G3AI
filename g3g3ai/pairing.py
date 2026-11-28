"""Conectar el móvil con el PC sin teclear direcciones ni contraseñas largas.

- Código de emparejamiento: 6 cifras, válido 10 minutos y de un solo uso. El móvil lo cambia por la contraseña
  (POST /api/pair). Tras 5 intentos fallidos se bloquea 1 minuto.
- QR: lleva un enlace http a la página /m del propio PC (cualquier cámara lo abre): ahí se elige «Abrir en la app»
  o «Usar en el navegador».
- Descubrimiento: el PC contesta por UDP (puerto 8799) a «¿hay algún G3G3AI?» con su nombre y puerto, para que la
  app los encuentre sola en la misma red. No revela ningún secreto.
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
import time
from urllib.parse import quote

CODE_TTL = 600
MAX_FAILS = 5
LOCK_SECONDS = 60
DISCOVERY_PORT = 8799
DISCOVERY_QUERY = b"G3G3AI?"


class PairError(Exception):
    pass


class Pairing:
    def __init__(self):
        self._code: str | None = None
        self._expires = 0.0
        self._fails = 0
        self._locked_until = 0.0
        self._lock = threading.Lock()

    def new_code(self) -> tuple[str, float]:
        with self._lock:
            self._code = f"{secrets.randbelow(1_000_000):06d}"
            self._expires = time.time() + CODE_TTL
            self._fails = 0
            return self._code, self._expires

    def current(self) -> tuple[str | None, float]:
        with self._lock:
            if self._code and time.time() < self._expires:
                return self._code, self._expires
            return None, 0.0

    def redeem(self, code: str) -> None:
        """Valida (y gasta) el código; PairError con el motivo si no vale."""
        with self._lock:
            now = time.time()
            if now < self._locked_until:
                raise PairError(f"Demasiados intentos. Espera {int(self._locked_until - now) + 1} s y vuelve a probar.")
            code = "".join(ch for ch in str(code or "") if ch.isdigit())
            if self._code and now < self._expires and secrets.compare_digest(code, self._code):
                self._code, self._fails = None, 0
                return
            self._fails += 1
            if self._fails >= MAX_FAILS:
                self._locked_until, self._fails = now + LOCK_SECONDS, 0
            if not self._code or now >= self._expires:
                raise PairError("El código ha caducado. Pide uno nuevo en el PC (Ajustes → Acceso).")
            raise PairError("Código incorrecto.")


def preferred_ip(ips: list[str]) -> str | None:
    """La dirección más probable de la red doméstica (192.168.x.x, luego 10.x, luego 172.16–31)."""
    def rank(ip: str) -> int:
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31:
            return 2
        return 3
    return sorted(ips, key=rank)[0] if ips else None


def pair_link(ips: list[str], port: int, code: str) -> str:
    ip = preferred_ip(ips)
    return f"http://{ip}:{port}/m?c={code}" if ip else ""


def app_intent(urls: list[str], code: str, name: str) -> str:
    """Enlace «intent:» de Android que abre la app instalada (o, si no está, la página de descargas)."""
    q = f"u={quote(','.join(urls), safe='')}&c={code}&n={quote(name, safe='')}"
    return (f"intent://pair?{q}#Intent;scheme=g3g3ai;package=com.g3g3ai.client;"
            f"S.browser_fallback_url={quote('https://github.com/varelacambon15/G3G3AI/releases/latest', safe='')};end")


def info(name: str, port: int, version: str) -> dict:
    return {"app": "g3g3ai", "name": name, "port": port, "version": version}


def start_discovery(get_info) -> threading.Thread | None:
    """Hilo que contesta a las búsquedas de la app. Si el puerto está ocupado, no pasa nada (otra instancia ya lo hace)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", DISCOVERY_PORT))
    except OSError:
        return None
    sock.settimeout(1.0)
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if data.strip() == DISCOVERY_QUERY:
                try:
                    sock.sendto(json.dumps(get_info()).encode("utf-8"), addr)
                except OSError:
                    pass
    t = threading.Thread(target=loop, daemon=True, name="g3g3ai-discovery")
    t.start()
    t.stop = lambda: (stop.set(), sock.close())          # type: ignore[attr-defined]
    return t


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Conectar con G3G3AI</title>
<style>
:root{color-scheme:light dark;--bg:#faf9f5;--fg:#1f1e1d;--mut:#75716a;--acc:#c2603f;--card:#fff;--bd:#e6e3da}
@media(prefers-color-scheme:dark){:root{--bg:#262624;--fg:#f1efe8;--mut:#a9a59b;--card:#30302d;--bd:#444}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif;display:flex;justify-content:center}
main{width:100%;max-width:440px;padding:28px 18px}h1{font-size:22px;margin:0 0 4px}p{color:var(--mut);margin:6px 0 16px}
.btn{display:block;text-align:center;padding:14px 16px;border-radius:12px;border:1px solid var(--bd);background:var(--card);
color:var(--fg);text-decoration:none;font-size:16px;margin:10px 0;width:100%;box-sizing:border-box;cursor:pointer}
.btn.p{background:var(--acc);border-color:var(--acc);color:#fff}small{color:var(--mut)}#msg{color:#c0392b;min-height:1.4em}
</style></head><body><main>
<h1>Conectar con __NAME__</h1>
<p>Elige cómo quieres usar G3G3AI en este móvil.</p>
<a class="btn p" href="__INTENT__">Abrir en la app de G3G3AI</a>
<small>Si no la tienes: <a href="https://github.com/varelacambon15/G3G3AI/releases/latest">descargar la app</a>.</small>
<button class="btn" id="web">Usar en el navegador</button>
<div id="msg"></div>
<script>
document.getElementById('web').onclick=async()=>{
  const m=document.getElementById('msg');m.textContent='Conectando…';
  try{const r=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'__CODE__'})});
  const d=await r.json();if(!r.ok)throw new Error(d.detail||'No se pudo conectar');location.href='/';}
  catch(e){m.textContent=e.message;}};
</script></main></body></html>"""
