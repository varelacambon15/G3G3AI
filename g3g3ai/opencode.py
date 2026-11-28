"""Cliente asíncrono de la API HTTP de OpenCode (el agente de código que corre en este equipo).

OpenCode escucha en `opencode_url` (por defecto http://127.0.0.1:28894) y pide autenticación
Basic con el usuario «opencode» y la contraseña de `opencode_password` (si está vacía, la
variable de entorno OPENCODE_PASSWORD). Rutas y cuerpos siguen el OpenAPI de OpenCode.
La configuración se lee en cada llamada, para que un cambio en Ajustes surta efecto sin reiniciar.
"""
from __future__ import annotations

import base64
import os

import httpx

DEFAULT_URL = "http://127.0.0.1:28894"
TIMEOUT = httpx.Timeout(10, read=60)


class OpenCodeError(Exception):
    """No se pudo hablar con OpenCode (red, autenticación o respuesta inesperada)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # código HTTP que devolvió OpenCode, si lo devolvió


def normalize(session: dict) -> dict:
    """Forma común de una sesión. Defensivo porque en el OpenCode real el directorio viene en
    `location.directory`, el tiempo en `time` **en milisegundos** y el modelo es un objeto
    `{id, providerID}`: aquí se quedan segundos, el id del modelo y el resultado."""
    loc = session.get("location")
    loc = loc if isinstance(loc, dict) else {}
    when = session.get("time")
    when = when if isinstance(when, dict) else {}
    updated = when.get("updated")
    if isinstance(updated, (int, float)):
        updated = updated / 1000  # G3G3AI trabaja con segundos (time.time())
    model = session.get("model")
    model = model.get("id") if isinstance(model, dict) else model
    return {"id": session.get("id"), "title": session.get("title"),
            "directory": loc.get("directory") or session.get("subpath"),
            "updated": updated, "agent": session.get("agent"),
            "model": model, "outcome": session.get("outcome")}


class OpenCodeClient:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def url(self) -> str:
        return (self.cfg["opencode_url"] or DEFAULT_URL).rstrip("/")

    @property
    def headers(self) -> dict:
        password = self.cfg["opencode_password"] or os.environ.get("OPENCODE_PASSWORD", "")
        raw = base64.b64encode(f"opencode:{password}".encode()).decode()
        return {"Authorization": f"Basic {raw}"}

    async def _req(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            async with httpx.AsyncClient(base_url=self.url, headers=self.headers, trust_env=False,
                                         timeout=TIMEOUT) as c:
                r = await c.request(method, path, **kw)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise OpenCodeError(f"No se pudo contactar con OpenCode en {self.url}: {e}") from e
        if r.status_code >= 400:
            raise OpenCodeError(self._msg(r), r.status_code)
        return r

    @staticmethod
    def _msg(r: httpx.Response) -> str:
        """Texto de error en español a partir de la respuesta de OpenCode."""
        try:
            data = r.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            detail = data.get("message") or data.get("detail") or data.get("_tag") or ""
            if detail:
                return f"OpenCode devolvió {r.status_code}: {detail}"
        return f"OpenCode devolvió {r.status_code}"

    async def status(self) -> dict:
        """Estado del servidor: `{available, version, error}` (nunca lanza)."""
        try:
            data = (await self._req("GET", "/api/info")).json()
        except OpenCodeError as e:
            return {"available": False, "version": "", "error": str(e)}
        except ValueError:
            return {"available": False, "version": "", "error": "OpenCode devolvió una respuesta no válida"}
        if not isinstance(data, dict):
            return {"available": False, "version": "", "error": "OpenCode devolvió una respuesta no válida"}
        return {"available": True, "version": str(data.get("version") or ""), "error": None}

    async def sessions(self, limit: int = 50) -> list[dict]:
        data = (await self._req("GET", "/api/session", params={"limit": limit})).json()
        items = data.get("data") if isinstance(data, dict) else data
        return [normalize(s) for s in (items or []) if isinstance(s, dict)]

    async def create_session(self, title: str | None = None, directory: str | None = None) -> dict:
        body: dict = {}
        if title:
            body["title"] = title
        if directory:
            body["location"] = {"directory": directory}
        data = (await self._req("POST", "/api/session", json=body)).json()
        session = data.get("data") if isinstance(data, dict) else data
        return normalize(session if isinstance(session, dict) else {})

    async def messages(self, session_id: str) -> list[dict]:
        """Mensajes de la sesión, tal cual los devuelve OpenCode (sin normalizar)."""
        data = (await self._req("GET", f"/api/session/{session_id}/message")).json()
        if isinstance(data, dict):
            return list(data.get("data") or [])
        return list(data or [])

    async def permissions(self) -> list[dict]:
        """Peticiones de permiso pendientes, tal cual las devuelve OpenCode (sin normalizar)."""
        data = (await self._req("GET", "/api/permission/request")).json()
        items = data.get("data") if isinstance(data, dict) else None
        return list(items) if isinstance(items, list) else []

    async def active(self) -> set[str] | None:
        """Sesiones que OpenCode está ejecutando; None si el servidor no lo soporta."""
        try:
            data = (await self._req("GET", "/api/session/active")).json()
        except (OpenCodeError, ValueError):
            return None
        running = data.get("data") if isinstance(data, dict) else None
        return set(running or {}) if isinstance(running, dict) else None

    async def prompt(self, session_id: str, text: str) -> None:
        await self._req("POST", f"/api/session/{session_id}/prompt", json={"text": text})

    async def interrupt(self, session_id: str) -> None:
        await self._req("POST", f"/api/session/{session_id}/interrupt")

    async def reply_permission(self, session_id: str, request_id: str, approved: bool) -> None:
        # El OpenAPI pide `decision`: «once» aprueba sólo esta vez, «reject» la rechaza.
        await self._req("POST", f"/api/session/{session_id}/permission/{request_id}/reply",
                        json={"decision": "once" if approved else "reject"})

    async def delete_session(self, session_id: str) -> None:
        await self._req("DELETE", f"/api/session/{session_id}")
