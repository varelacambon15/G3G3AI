"""Ollama como motor local alternativo a llama.cpp (cómodo en PC: descarga modelos por nombre y usa la gráfica).

- status(): si está instalado, si está en marcha y qué modelos tiene.
- Instalar: Windows con winget (o el instalador oficial si no hay winget), macOS con Homebrew.
  En Linux el instalador oficial necesita permisos de administrador: se muestra el comando.
- Descargar (pull) modelos con progreso, borrarlos y arrancar el servicio.
En el chat se usa como el proveedor «Ollama (local)», que habla su API compatible con OpenAI.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0)
WIN_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
LINUX_INSTALL = "curl -fsSL https://ollama.com/install.sh | sh"

# Sugerencias por tamaño recomendado (nombres de la biblioteca de Ollama; puede haber versiones más nuevas)
SUGGESTIONS = {
    "3–4B": ["qwen3:4b", "gemma3:4b"],
    "7–8B": ["qwen3:8b", "llama3.1:8b"],
    "12–14B": ["qwen3:14b", "gemma3:12b"],
    "MoE ~30B-A3B": ["qwen3:30b"],
    "27–32B": ["qwen3:32b", "gemma3:27b"],
}
VISION = {"3–4B": "gemma3:4b", "7–8B": "qwen2.5vl:7b", "12–14B": "gemma3:12b", "MoE ~30B-A3B": "gemma3:12b",
          "27–32B": "gemma3:27b"}


def base_url(cfg) -> str:
    return (cfg["ollama_url"] or "http://127.0.0.1:11434").rstrip("/")


def find_binary() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        return str(p) if p.is_file() else None
    for p in ("/usr/local/bin/ollama", "/usr/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"):
        if Path(p).is_file():
            return p
    return None


async def status(cfg) -> dict:
    base = base_url(cfg)
    out = {"installed": bool(find_binary()), "running": False, "version": None, "models": [], "url": base,
           "can_install": sys.platform == "win32" or (sys.platform == "darwin" and bool(shutil.which("brew"))),
           "linux_command": LINUX_INSTALL if sys.platform.startswith("linux") else None}
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as c:
            v = await c.get(f"{base}/api/version")
            if v.status_code == 200:
                out["running"] = True
                out["installed"] = True  # en marcha (quizá en otro equipo o en Docker)
                out["version"] = v.json().get("version")
                tags = await c.get(f"{base}/api/tags")
                for m in (tags.json().get("models") or []) if tags.status_code == 200 else []:
                    d = m.get("details") or {}
                    out["models"].append({"name": m.get("name"), "size": m.get("size", 0),
                                          "params": d.get("parameter_size"), "quant": d.get("quantization_level"),
                                          "family": d.get("family")})
    except httpx.HTTPError:
        pass
    return out


class OllamaManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.job = {"status": "idle", "what": None, "log": [], "error": None, "total": 0, "completed": 0}
        self._task: asyncio.Task | None = None

    def _log(self, line: str):
        self.job["log"] = (self.job["log"] + [line])[-60:]

    def _start(self, what: str, coro) -> dict:
        if self._task and not self._task.done():
            return self.job
        self.job = {"status": "running", "what": what, "log": [], "error": None, "total": 0, "completed": 0}

        async def runner():
            try:
                await coro
                self.job["status"] = "done"
            except Exception as e:  # noqa: BLE001
                self.job["status"], self.job["error"] = "error", str(e)
                self._log("ERROR: " + str(e))
        self._task = asyncio.create_task(runner())
        return self.job

    # Instalar / arrancar ------------------------------------------------------------------
    def install(self) -> dict:
        return self._start("instalar Ollama", self._install())

    async def _install(self):
        if sys.platform == "win32":
            if shutil.which("winget"):
                self._log("Instalando Ollama con winget…")
                code, out = await asyncio.to_thread(self._run, ["winget", "install", "--id", "Ollama.Ollama", "-e",
                                                                "--accept-package-agreements",
                                                                "--accept-source-agreements", "--disable-interactivity"])
                self._log(out[-1500:])
                if code == 0:
                    self._log("✔ Ollama instalado. Se arrancará solo; si no, pulsa «Iniciar».")
                    return
                self._log("winget no pudo instalarlo; se descarga el instalador oficial…")
            setup = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True) as c:
                async with c.stream("GET", WIN_SETUP_URL) as r:
                    r.raise_for_status()
                    self.job["total"] = int(r.headers.get("content-length") or 0)
                    with open(setup, "wb") as f:
                        async for chunk in r.aiter_bytes(1 << 20):
                            f.write(chunk)
                            self.job["completed"] += len(chunk)
            self._log("Abriendo el instalador de Ollama: sigue sus pasos en la ventana que aparece.")
            os.startfile(str(setup))  # type: ignore[attr-defined]  # instalador interactivo de Ollama
            return
        if sys.platform == "darwin" and shutil.which("brew"):
            code, out = await asyncio.to_thread(self._run, ["brew", "install", "ollama"], 1800)
            self._log(out[-1500:])
            if code != 0:
                raise RuntimeError("brew install ollama falló")
            return
        raise RuntimeError("En Linux, instala Ollama desde una terminal con:  " + LINUX_INSTALL
                           + "  (pide la contraseña de administrador). En SteamOS no se recomienda: usa llama.cpp.")

    def start(self) -> dict:
        exe = find_binary()
        if not exe:
            raise RuntimeError("Ollama no está instalado.")
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         creationflags=NO_WINDOW | DETACHED, start_new_session=sys.platform != "win32")
        return {"ok": True}

    # Modelos -------------------------------------------------------------------------------
    def pull(self, name: str) -> dict:
        return self._start(f"descargar {name}", self._pull(name))

    async def _pull(self, name: str):
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=None), trust_env=False) as c:
            async with c.stream("POST", f"{base_url(self.cfg)}/api/pull", json={"model": name, "stream": True}) as r:
                if r.status_code >= 400:
                    raise RuntimeError(f"Ollama respondió {r.status_code}: {(await r.aread())[:300]!r}")
                last = ""
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    if ev.get("total"):
                        self.job["total"], self.job["completed"] = ev["total"], ev.get("completed", 0)
                    st = ev.get("status", "")
                    if st and st != last:
                        self._log(st)
                        last = st
        self._log(f"✔ {name} listo")

    async def delete(self, name: str) -> None:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
            r = await c.request("DELETE", f"{base_url(self.cfg)}/api/delete", json={"model": name})
            if r.status_code >= 400:
                raise RuntimeError(f"No se pudo borrar {name}: {r.text[:200]}")

    @staticmethod
    def _run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                               creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            return -1, str(e)


def suggestions_for(tier: str) -> dict:
    return {"models": SUGGESTIONS.get(tier, SUGGESTIONS["3–4B"]), "vision": VISION.get(tier, "gemma3:4b")}
