"""Gestión del proceso llama-server (llama.cpp) para los modelos locales. Multiplataforma."""
from __future__ import annotations

import asyncio
import atexit
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import httpx

from .config import DATA_DIR

EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_llama_server(configured: str = "") -> str | None:
    candidates = [configured, str(DATA_DIR / "llama.cpp" / "build" / "bin" / EXE)]
    engine = DATA_DIR / "engine"
    if engine.is_dir():
        candidates += [str(p) for p in sorted(engine.rglob(EXE))]
    candidates.append(shutil.which("llama-server") or "")
    for c in candidates:
        if c and Path(c).is_file() and (sys.platform == "win32" or os.access(c, os.X_OK)):
            return c
    return None


def default_threads() -> int:
    n = os.cpu_count() or 4
    return max(1, n)


class LlamaManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.model_path: str | None = None
        self.params: dict = {}
        self.state = "stopped"  # stopped | loading | ready | error
        self.error: str | None = None
        self.started_at: float | None = None
        self.logs: deque[str] = deque(maxlen=400)
        self._lock = asyncio.Lock()
        atexit.register(self._kill_sync)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.cfg['llama_port']}"

    @property
    def ready(self) -> bool:
        return self.state == "ready"

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

    def _read_logs(self, proc: subprocess.Popen):
        assert proc.stdout
        for line in iter(proc.stdout.readline, b""):
            self.logs.append(line.decode("utf-8", errors="replace").rstrip())

    async def load(self, model_path: str, ctx: int | None = None, threads: int | None = None,
                   gpu_layers: int | None = None, extra_args: str | None = None) -> dict:
        async with self._lock:
            await self._stop_locked()
            binary = find_llama_server(self.cfg["llama_server_path"])
            if not binary:
                self.state, self.error = "error", (
                    "No se encuentra llama-server. Instálalo desde Modelos → Motor llama.cpp "
                    "(o con install.sh en Linux)."
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
            ] + shlex.split(extra or "", posix=sys.platform != "win32")
            self.params = {"ctx": ctx, "threads": threads, "gpu_layers": gpu_layers, "extra_args": extra}
            self.logs.clear()
            self.logs.append("$ " + " ".join(cmd))
            self.state, self.error = "loading", None
            self.model_path = model_path
            self.started_at = time.time()
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, cwd=str(Path(binary).parent),
                                             creationflags=NO_WINDOW)
            except OSError as e:
                self.state, self.error = "error", f"No se pudo iniciar llama-server: {e}"
                return self.status()
            threading.Thread(target=self._read_logs, args=(self.proc,), daemon=True).start()
            self.cfg.set("last_model", model_path)

        asyncio.create_task(self._wait_ready(self.proc))
        return self.status()

    async def _wait_ready(self, proc: subprocess.Popen):
        deadline = time.time() + 600
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            while time.time() < deadline:
                if proc is not self.proc:
                    return
                if proc.poll() is not None:
                    await asyncio.sleep(0.3)  # deja que el lector capture las últimas líneas
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
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, 15)
            except subprocess.TimeoutExpired:
                proc.kill()
                await asyncio.to_thread(proc.wait)
        self.state, self.model_path, self.started_at, self.params = "stopped", None, None, {}

    def _kill_sync(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    async def unload(self) -> dict:
        async with self._lock:
            await self._stop_locked()
        return self.status()
