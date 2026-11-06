"""Gestión del proceso llama-server (llama.cpp) para los modelos locales."""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import time
from collections import deque
from pathlib import Path

import httpx

from .config import DATA_DIR


def find_llama_server(configured: str = "") -> str | None:
    candidates = [
        configured,
        str(DATA_DIR / "llama.cpp" / "build" / "bin" / "llama-server"),
        shutil.which("llama-server") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def default_threads() -> int:
    n = os.cpu_count() or 4
    return max(1, n)


class LlamaManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self.model_path: str | None = None
        self.params: dict = {}
        self.state = "stopped"  # stopped | loading | ready | error
        self.error: str | None = None
        self.started_at: float | None = None
        self.logs: deque[str] = deque(maxlen=400)
        self._log_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.cfg['llama_port']}"

    def status(self) -> dict:
        return {
            "state": self.state,
            "model": Path(self.model_path).name if self.model_path else None,
            "model_path": self.model_path,
            "params": self.params,
            "error": self.error,
            "started_at": self.started_at,
            "binary": find_llama_server(self.cfg["llama_server_path"]),
        }

    async def _read_logs(self, proc):
        assert proc.stdout
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            self.logs.append(line.decode("utf-8", errors="replace").rstrip())

    async def load(self, model_path: str, ctx: int | None = None, threads: int | None = None,
                   gpu_layers: int | None = None, extra_args: str | None = None) -> dict:
        async with self._lock:
            await self._stop_locked()
            binary = find_llama_server(self.cfg["llama_server_path"])
            if not binary:
                self.state, self.error = "error", (
                    "No se encuentra llama-server. Ejecuta install.sh para compilar llama.cpp "
                    "o indica la ruta en Ajustes."
                )
                return self.status()
            if not Path(model_path).is_file():
                self.state, self.error = "error", f"No existe el modelo: {model_path}"
                return self.status()

            ctx = int(ctx or self.cfg["llama_ctx"])
            threads = int(threads or self.cfg["llama_threads"] or default_threads())
            gpu_layers = int(gpu_layers if gpu_layers is not None else self.cfg["llama_gpu_layers"])
            extra = extra_args if extra_args is not None else self.cfg["llama_extra_args"]
            cmd = [
                binary, "-m", model_path,
                "--host", "127.0.0.1", "--port", str(self.cfg["llama_port"]),
                "-c", str(ctx), "-t", str(threads),
                "-ngl", str(gpu_layers),
                "--jinja",  # plantillas de chat del modelo + llamadas a herramientas
            ] + shlex.split(extra or "")
            self.params = {"ctx": ctx, "threads": threads, "gpu_layers": gpu_layers, "extra_args": extra}
            self.logs.clear()
            self.logs.append("$ " + shlex.join(cmd))
            self.state, self.error = "loading", None
            self.model_path = model_path
            self.started_at = time.time()
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )
            except OSError as e:
                self.state, self.error = "error", f"No se pudo iniciar llama-server: {e}"
                return self.status()
            self._log_task = asyncio.create_task(self._read_logs(self.proc))
            self.cfg.set("last_model", model_path)

        asyncio.create_task(self._wait_ready(self.proc))
        return self.status()

    async def _wait_ready(self, proc):
        deadline = time.time() + 600
        async with httpx.AsyncClient(timeout=3) as client:
            while time.time() < deadline:
                if proc is not self.proc:
                    return
                if proc.returncode is not None:
                    tail = "\n".join(list(self.logs)[-15:])
                    self.state, self.error = "error", f"llama-server terminó (código {proc.returncode}).\n{tail}"
                    return
                try:
                    r = await client.get(self.base_url + "/health")
                    if r.status_code == 200:
                        self.state = "ready"
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.7)
        self.state, self.error = "error", "Tiempo de espera agotado cargando el modelo."

    async def _stop_locked(self):
        proc = self.proc
        self.proc = None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 15)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        if self._log_task:
            self._log_task.cancel()
            self._log_task = None
        self.state, self.model_path, self.started_at, self.params = "stopped", None, None, {}

    async def unload(self) -> dict:
        async with self._lock:
            await self._stop_locked()
        return self.status()
