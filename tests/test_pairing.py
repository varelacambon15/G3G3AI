# -*- coding: utf-8 -*-
"""Emparejamiento con el móvil: código, caducidad, bloqueo, página /m y descubrimiento UDP.

Sin dependencia de pytest a propósito: se puede ejecutar con pytest en CI o a mano
con un corredor mínimo (python corredor.py) donde no haya pytest instalado.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time
import traceback
from pathlib import Path


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


COOKIE_NAME = "g3g3ai_token"   # la misma que usa el servidor (server.py)


def make_app():
    """App de G3G3AI en un directorio temporal; devuelve (app, cfg)."""
    for m in [m for m in sys.modules if m.startswith("g3g3ai")]:
        del sys.modules[m]
    tmp = tempfile.mkdtemp(prefix="g3g3ai-pair-")
    os.environ["G3G3AI_CONFIG_DIR"] = str(Path(tmp) / "cfg")
    os.environ["G3G3AI_DATA_DIR"] = str(Path(tmp) / "data")
    os.environ["G3G3AI_NO_UPDATE_CHECK"] = "1"
    from g3g3ai.config import Config
    from g3g3ai.server import create_app

    home = Path(tmp) / "home"; home.mkdir(parents=True)
    cfg = Config(Path(tmp) / "cfg" / "config.json")
    cfg.data.update({"file_roots": [str(home)], "write_roots": [str(home)],
                     "models_dir": str(Path(tmp) / "models"),
                     "llama_port": free_port(), "port": free_port(),
                     "autoload_last_model": False, "localhost_without_token": False})
    cfg.save()
    return create_app(cfg), cfg


def test_pair_code_solo_local():
    """Generar código desde fuera del propio equipo debe estar prohibido (aunque esté autenticado)."""
    from fastapi.testclient import TestClient
    app, cfg = make_app()
    with TestClient(app) as client:  # TestClient llega como «testclient», no como 127.0.0.1
        h = {"Authorization": f"Bearer {cfg['token']}"}
        r = client.post("/api/pair/code", headers=h)
        assert r.status_code == 403, r.text
        r = client.get("/api/pair/status", headers=h)
        assert r.status_code == 403, r.text


def run(coro):
    """Ejecuta una corrutina sincrónicamente (el transporte ASGI de httpx es asíncrono)."""
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)


def test_pairing_ciclo_completo():
    """Código -> contraseña -> cookie; el QR lleva el código dentro; /m se sirve."""
    import httpx
    app, cfg = make_app()

    async def local_flow():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pc") as local:
            h = {"Authorization": f"Bearer {cfg['token']}"}
            r = await local.post("/api/pair/code", headers=h)   # ASGITransport llega como 127.0.0.1
            assert r.status_code == 200, r.text
            d = r.json()
            assert len(d["code"]) == 6 and d["code"].isdigit()
            assert d["expires_in"] == 600
            assert d["qr"].startswith("<svg")          # QR en SVG para la tarjeta de Ajustes
            assert d["urls"], "debe anunciar al menos una URL LAN"
            st = await local.get("/api/pair/status", headers=h)
            assert st.json().get("code") == d["code"] and 0 < st.json()["expires_in"] <= 600
            # La página del escáner se sirve sin autenticar
            r = await local.get("/m")
            assert r.status_code == 200 and "Conectar con tu PC" in r.text
            return d

    d = run(local_flow())
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        r = client.post("/api/pair/exchange", json={"code": "000000"})
        assert r.status_code == 401
        r = client.post("/api/pair/exchange", json={"code": d["code"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token"] == cfg["token"]
        assert body["urls"]
        assert client.cookies.get(COOKIE_NAME) == cfg["token"]  # deja la cookie puesta
        # y con esa cookie ya pasa la autenticación normal
        assert client.get("/api/status").status_code == 200


def test_pairing_bloqueo_por_intentos():
    """A los 5 códigos erróneos, el correcto también se rechaza hasta regenerar."""
    import httpx
    app, cfg = make_app()

    async def new_code():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pc") as local:
            r = await local.post("/api/pair/code", headers={"Authorization": f"Bearer {cfg['token']}"})
            assert r.status_code == 200, r.text
            return r.json()["code"]

    code = run(new_code())
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post("/api/pair/exchange", json={"code": "999999"}).status_code == 401
        assert client.post("/api/pair/exchange", json={"code": code}).status_code == 401
        # regenerar el código desbloquea
        code2 = run(new_code())
        assert client.post("/api/pair/exchange", json={"code": code2}).status_code == 200


def test_pairing_caducidad():
    """Un código con la hora de caducidad pasada no cambia nada."""
    from g3g3ai.pairing import Pairing
    p = Pairing(58000, lambda: "PC", lambda: ["http://1.2.3.4:58000"])
    p.set_token("secreto")
    code = p.new_code()
    assert p.exchange(code) == "secreto"          # vigente, funciona
    code = p.new_code()
    p._expires = time.time() - 1                  # forzamos caducidad
    assert p.exchange(code) is None
    assert p.current() == {}


def test_descubrimiento_udp():
    """El ping UDP del móvil recibe nombre, puerto y URLs (nunca la contraseña)."""
    from g3g3ai.pairing import Pairing
    port = free_port()
    p = Pairing(port, lambda: "PC-de-Alejandro", lambda: [f"http://192.168.1.10:{port}"])
    p.start()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(json.dumps({"g3g3ai": 1, "q": "discover"}).encode(), ("127.0.0.1", port))
        data, _ = s.recvfrom(2048)
        d = json.loads(data)
        assert d["g3g3ai"] == 1
        assert d["name"] == "PC-de-Alejandro"
        assert d["port"] == port and d["host"] == "127.0.0.1"
        assert d["urls"] == [f"http://192.168.1.10:{port}"]
        assert "token" not in d and "secreto" not in data.decode().lower()
        # anti-inundación: un segundo ping inmediato desde la misma IP no recibe respuesta
        s.settimeout(1.2)
        s.sendto(json.dumps({"g3g3ai": 1, "q": "discover"}).encode(), ("127.0.0.1", port))
        try:
            s.recvfrom(2048)
            raise AssertionError("respondió dos veces en menos de 1 s")
        except socket.timeout:
            pass
        # los mensajes que no son del protocolo no responden nada
        s.sendto(b"no-soy-g3g3ai", ("127.0.0.1", port))
        try:
            s.recvfrom(2048)
            raise AssertionError("respondió a un mensaje ajeno")
        except socket.timeout:
            pass
    finally:
        p.stop()


if __name__ == "__main__":
    fallas = 0
    for nombre, fn in sorted(list(globals().items())):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK    {nombre}")
            except Exception:
                fallas += 1
                print(f"FALLA {nombre}")
                traceback.print_exc()
    sys.exit(1 if fallas else 0)
