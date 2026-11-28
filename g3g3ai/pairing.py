# -*- coding: utf-8 -*-
"""Emparejamiento con el móvil: código de 6 dígitos, descubrimiento UDP y página /m.

El PC muestra en Ajustes → Acceso un código y un QR; el móvil los introduce (o los
escanea con la app) y recibe la contraseña de acceso. El código caduca a los 10
minutos, admite 5 intentos y sólo está activo mientras la pantalla de emparejamiento
está abierta. El descubrimiento UDP responde a los «ping» de la app con el nombre,
la dirección y el puerto del servidor (nunca la contraseña).
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
import time

CODE_TTL = 600          # el código vale 10 minutos
CODE_ATTEMPTS = 5       # intentos por código
DISCOVERY_PROTO = 1     # versión del protocolo de descubrimiento


class Pairing:
    """Códigos de emparejamiento pendientes y servicio de descubrimiento UDP."""

    def __init__(self, port: int, get_name, get_urls):
        self.port = port                  # puerto TCP del servidor (para anunciarlo)
        self.get_name = get_name          # -> nombre del equipo
        self.get_urls = get_urls          # -> ["http://ip:puerto", ...]
        self._lock = threading.Lock()
        self._code = ""
        self._expires = 0.0
        self._attempts = CODE_ATTEMPTS
        self._token: str | None = None   # contraseña que se entrega al emparejar
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_ping: dict[str, float] = {}   # ip -> hora del último ping (anti-inundación)

    # --- Código de emparejamiento ---------------------------------------------------
    def new_code(self) -> str:
        with self._lock:
            self._code = f"{secrets.randbelow(1000000):06d}"
            self._expires = time.time() + CODE_TTL
            self._attempts = CODE_ATTEMPTS
            return self._code

    def current(self) -> dict:
        """Código vigente (para mostrarlo en la pantalla del PC)."""
        with self._lock:
            if self._code and time.time() < self._expires:
                return {"code": self._code, "expires_in": int(self._expires - time.time())}
            return {}

    def exchange(self, code: str) -> str | None:
        """Cambia un código válido por la contraseña; None si es erróneo o caducado."""
        with self._lock:
            if not self._code or time.time() >= self._expires or self._attempts <= 0:
                return None
            if not secrets.compare_digest(str(code).strip().zfill(6), self._code):
                self._attempts -= 1
                return None
            return self._token

    def set_token(self, token: str) -> None:
        self._token = token

    # --- Descubrimiento UDP ----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._serve, daemon=True, name="g3g3ai-discovery")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _serve(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", self.port))
            s.settimeout(0.5)
        except OSError:
            return                     # sin descubrimiento; el código/QR siguen funcionando
        while not self._stop.is_set():
            try:
                data, addr = s.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except ValueError:
                continue
            if msg.get("g3g3ai") != DISCOVERY_PROTO or msg.get("q") != "discover":
                continue
            now = time.time()
            if now - self._last_ping.get(addr[0], 0) < 1.0:   # máx. 1 respuesta/seg por IP
                continue
            self._last_ping[addr[0]] = now
            reply = {"g3g3ai": DISCOVERY_PROTO, "name": self.get_name(),
                     "host": addr[0], "port": self.port, "urls": self.get_urls()}
            try:
                s.sendto(json.dumps(reply).encode(), addr)
            except OSError:
                pass
        try:
            s.close()
        except OSError:
            pass
