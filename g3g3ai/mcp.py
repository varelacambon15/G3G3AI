"""Cliente MCP (Model Context Protocol) por stdio: conecta herramientas externas al agente.

Se configuran en Ajustes → «Servidores MCP», una línea por servidor:
    nombre = [VAR=valor …] comando arg1 arg2 …
p. ej.  archivos = npx -y @modelcontextprotocol/server-filesystem C:\\Proyectos
Cada herramienta del servidor aparece al agente como `mcp__nombre__herramienta`. Cada llamada pide permiso al
usuario (se puede marcar «Permitir siempre aquí»). Los servidores arrancan al usarlos y se cierran con la app.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import sys
import time

from . import __version__

PROTOCOL = "2024-11-05"
START_TIMEOUT = 30
CALL_TIMEOUT = 120
MAX_RESULT = 40_000
RETRY_AFTER = 60  # segundos antes de reintentar un servidor que falló


class MCPError(Exception):
    pass


def parse_servers(lines) -> list[dict]:
    """«nombre = [VAR=valor …] comando args» → [{name, argv, env}]. Ignora líneas vacías o mal formadas."""
    out = []
    for ln in lines or []:
        m = re.match(r"\s*([\w.-]+)\s*=\s*(.+)$", str(ln))
        if not m:
            continue
        try:
            parts = shlex.split(m.group(2), posix=sys.platform != "win32")
        except ValueError:
            continue
        if sys.platform == "win32":  # shlex no quita las comillas en modo Windows
            parts = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]
        env = {}
        while parts and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", parts[0]):
            k, v = parts.pop(0).split("=", 1)
            env[k] = v
        if parts:
            out.append({"name": m.group(1), "argv": parts, "env": env})
    return out


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)


class MCPServer:
    def __init__(self, name: str, argv: list[str], env: dict):
        self.name, self.argv, self.env = name, argv, env
        self.proc: asyncio.subprocess.Process | None = None
        self.tools: list[dict] = []
        self.error: str | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.stderr_tail: list[str] = []
        self.last_try = 0.0

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        async with self._lock:
            if self.alive:
                return
            exe = shutil.which(self.argv[0]) or self.argv[0]
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    exe, *self.argv[1:], stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, env={**os.environ, **self.env})
            except OSError as e:
                self.error = f"No se pudo arrancar «{self.argv[0]}»: {e}"
                raise MCPError(self.error)
            self._reader = asyncio.create_task(self._read_loop())
            asyncio.create_task(self._drain_stderr())
            try:
                await self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                  "clientInfo": {"name": "g3g3ai", "version": __version__}},
                                   timeout=START_TIMEOUT)
                await self.notify("notifications/initialized")
                tools, cursor = [], None
                while True:
                    r = await self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout=START_TIMEOUT)
                    tools += r.get("tools", [])
                    cursor = r.get("nextCursor")
                    if not cursor:
                        break
                self.tools, self.error = tools, None
            except Exception as e:  # noqa: BLE001
                tail = " | ".join(self.stderr_tail[-3:])
                self.error = f"{e}" + (f" ({tail})" if tail else "")
                await self.stop()
                raise MCPError(self.error)

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        try:
            async for line in self.proc.stderr:
                self.stderr_tail = (self.stderr_tail + [line.decode("utf-8", "replace").strip()])[-10:]
        except Exception:  # noqa: BLE001
            pass

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            async for raw in self.proc.stdout:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(MCPError(str((msg["error"] or {}).get("message", msg["error"]))))
                        else:
                            fut.set_result(msg["result"])
                elif "id" in msg and "method" in msg:  # petición del servidor: sólo se contesta a ping
                    reply = {"jsonrpc": "2.0", "id": msg["id"]}
                    reply.update({"result": {}} if msg["method"] == "ping" else
                                 {"error": {"code": -32601, "message": "No soportado por este cliente"}})
                    await self._send(reply)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MCPError("el servidor MCP se cerró"))
            self._pending.clear()

    async def _send(self, obj: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise MCPError("servidor no arrancado")
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    async def notify(self, method: str, params: dict | None = None) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    async def request(self, method: str, params: dict | None = None, timeout: float = CALL_TIMEOUT):
        self._id += 1
        rid = self._id
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise MCPError(f"sin respuesta en {int(timeout)} s ({method})")

    async def call(self, tool: str, args: dict) -> str:
        if not self.alive:
            await self.start()
        r = await self.request("tools/call", {"name": tool, "arguments": args})
        parts = []
        for c in r.get("content", []):
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif c.get("type") == "image":
                parts.append("[imagen devuelta por la herramienta; no se muestra]")
            elif c.get("type") == "resource":
                res = c.get("resource", {})
                parts.append(res.get("text") or f"[recurso {res.get('uri', '')}]")
            else:
                parts.append(f"[{c.get('type', 'contenido')}]")
        text = "\n".join(p for p in parts if p) or "(sin contenido)"
        if len(text) > MAX_RESULT:
            text = text[:MAX_RESULT] + "\n[… recortado …]"
        return ("Error de la herramienta: " + text) if r.get("isError") else text

    async def stop(self) -> None:
        p, self.proc = self.proc, None
        if p and p.returncode is None:
            try:
                p.terminate()
                await asyncio.wait_for(p.wait(), 3)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    p.kill()
                except ProcessLookupError:
                    pass
        if self._reader:
            self._reader.cancel()


class MCPManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.servers: dict[str, MCPServer] = {}
        self.map: dict[str, tuple[str, str]] = {}   # nombre expuesto → (servidor, herramienta)
        self._sig = None

    def _sync_servers(self) -> None:
        conf = parse_servers(self.cfg["mcp_servers"])
        sig = json.dumps(conf, sort_keys=True)
        if sig == self._sig:
            return
        self._sig = sig
        keep = {c["name"] for c in conf}
        for n in [n for n in self.servers if n not in keep]:
            asyncio.ensure_future(self.servers.pop(n).stop())
        for c in conf:
            cur = self.servers.get(c["name"])
            if cur and (cur.argv, cur.env) != (c["argv"], c["env"]):
                asyncio.ensure_future(cur.stop())
                cur = None
            if cur is None:
                self.servers[c["name"]] = MCPServer(c["name"], c["argv"], c["env"])

    async def refresh(self, force: bool = False) -> None:
        """Arranca los servidores configurados (los que aún no lo están) y reconstruye el mapa de herramientas."""
        self._sync_servers()
        now = time.monotonic()
        todo = [s for s in self.servers.values()
                if not s.alive and (not s.error or now - s.last_try > RETRY_AFTER or force)]
        for s in todo:
            s.last_try = now
        await asyncio.gather(*(s.start() for s in todo), return_exceptions=True)
        self.map = {}
        for s in self.servers.values():
            for t in s.tools if s.alive else []:
                self.map[f"mcp__{safe(s.name)}__{safe(t['name'])}"[:64]] = (s.name, t["name"])

    def specs(self) -> dict[str, tuple[str, dict]]:
        out = {}
        for exposed, (srv, tool) in self.map.items():
            t = next((x for x in self.servers[srv].tools if x["name"] == tool), None)
            if t:
                schema = t.get("inputSchema") or {"type": "object", "properties": {}}
                out[exposed] = (f"[MCP · {srv}] {t.get('description') or tool}", schema)
        return out

    async def call(self, exposed: str, args: dict) -> str:
        srv, tool = self.map[exposed]
        try:
            return await self.servers[srv].call(tool, args)
        except MCPError as e:
            return f"Error del servidor MCP «{srv}»: {e}"

    def status(self) -> list[dict]:
        return [{"name": s.name, "command": " ".join(s.argv), "ok": s.alive, "error": s.error,
                 "tools": [{"name": t["name"], "description": (t.get("description") or "")[:200]} for t in s.tools]}
                for s in self.servers.values()]

    async def stop(self) -> None:
        await asyncio.gather(*(s.stop() for s in self.servers.values()), return_exceptions=True)
