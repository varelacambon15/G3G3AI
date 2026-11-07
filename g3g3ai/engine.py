"""Descarga del motor llama.cpp precompilado desde GitHub (para Windows, macOS y Linux x64).

En la Konkr (ARM) se recomienda compilarlo con install.sh, que lo optimiza para su CPU.
"""
from __future__ import annotations

import asyncio
import platform
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

import httpx

from .config import DATA_DIR
from .llama import EXE

RELEASES = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
SD_RELEASES = "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest"


def sd_rules() -> list[tuple[str, re.Pattern, str]]:
    """Binarios de stable-diffusion.cpp (los nombres de sus archivos varían entre versiones)."""
    m = platform.machine().lower()
    arm = m in ("arm64", "aarch64")
    if sys.platform == "win32":
        return [
            ("vulkan", re.compile(r"bin-win-vulkan-x64\.zip$", re.I), "GPU (Vulkan) — recomendado si tienes gráfica."),
            ("cpu", re.compile(r"bin-win-avx2-x64\.zip$", re.I), "Sólo procesador (lento)."),
        ]
    if sys.platform == "darwin":
        return [("metal", re.compile(r"bin-Darwin.*" + ("arm64" if arm else "x86_64") + r".*\.zip$", re.I), "Mac")]
    a = "(aarch64|arm64)" if arm else "x86_64"
    return [("cpu", re.compile(r"bin-Linux.*" + a + r".*\.zip$", re.I), "Linux")]


def platform_rules() -> list[tuple[str, re.Pattern, str]]:
    """(variante, patrón del nombre del archivo, descripción) para esta plataforma."""
    m = platform.machine().lower()
    arm = m in ("arm64", "aarch64")
    ext = r"\.(zip|tar\.gz)$"
    if sys.platform == "win32":
        a = "arm64" if arm else "x64"
        return [
            ("vulkan", re.compile(rf"bin-win-vulkan-{a}{ext}"), "GPU (Vulkan) — NVIDIA, AMD o Intel. Recomendado si tienes gráfica."),
            ("cpu", re.compile(rf"bin-win-cpu-{a}{ext}"), "Sólo procesador — funciona en cualquier PC."),
        ]
    if sys.platform == "darwin":
        a = "arm64" if arm else "x64"
        return [("metal", re.compile(rf"bin-macos-{a}{ext}"), "Mac (Metal)")]
    a = "arm64" if arm else "x64"
    return [
        ("vulkan", re.compile(rf"bin-ubuntu-vulkan-{a}{ext}"), "GPU (Vulkan)"),
        ("cpu", re.compile(rf"bin-ubuntu-{a}{ext}"), "Sólo procesador"),
    ]


class EngineInstaller:
    """kind="llama" (llama-server) o "sd" (stable-diffusion.cpp)."""

    def __init__(self, cfg, kind: str = "llama"):
        self.cfg = cfg
        self.kind = kind
        self.releases = SD_RELEASES if kind == "sd" else RELEASES
        self.rules = sd_rules if kind == "sd" else platform_rules
        self.exe_names = (["sd-cli", "sd"] if kind == "sd" else [EXE.removesuffix(".exe")])
        self.cfg_key = "sd_path" if kind == "sd" else "llama_server_path"
        self.folder = "sd-engine" if kind == "sd" else "engine"
        self.state = {"status": "idle", "done": 0, "total": 0, "error": None, "name": None}
        self._task: asyncio.Task | None = None

    async def assets(self) -> dict:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                     headers={"Accept": "application/vnd.github+json"}) as c:
            r = await c.get(self.releases)
            r.raise_for_status()
        rel = r.json()
        out = []
        for variant, pat, desc in self.rules():
            for a in rel.get("assets", []):
                if pat.search(a["name"]):
                    out.append({"variant": variant, "name": a["name"], "url": a["browser_download_url"],
                                "size": a.get("size", 0), "description": desc})
                    break
        note = None
        if not out:
            note = ("No hay binarios precompilados para esta plataforma "
                    f"({sys.platform} {platform.machine()}). En Linux/ARM usa ./install.sh para compilarlo.")
        return {"release": rel.get("tag_name"), "assets": out, "note": note}

    def start(self, url: str, name: str) -> dict:
        if self._task and not self._task.done():
            return self.state
        self.state = {"status": "downloading", "done": 0, "total": 0, "error": None, "name": name}
        self._task = asyncio.create_task(self._run(url, name))
        return self.state

    async def _run(self, url: str, name: str):
        engine = DATA_DIR / self.folder
        tmp = engine / "_tmp"
        archive = engine / name
        try:
            engine.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True) as c:
                async with c.stream("GET", url) as r:
                    r.raise_for_status()
                    self.state["total"] = int(r.headers.get("content-length") or 0)
                    with open(archive, "wb") as f:
                        async for chunk in r.aiter_bytes(1 << 20):
                            f.write(chunk)
                            self.state["done"] += len(chunk)
            self.state["status"] = "extracting"
            exe = await asyncio.to_thread(self._extract, archive, tmp, engine / re.sub(r"\.(zip|tar\.gz)$", "", name),
                                          self.exe_names)
            self.cfg.set(self.cfg_key, str(exe))
            self.state["status"] = "done"
            self.state["path"] = str(exe)
        except Exception as e:  # noqa: BLE001
            self.state["status"], self.state["error"] = "error", str(e)
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _extract(archive: Path, tmp: Path, dest: Path, names: list[str]) -> Path:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
        else:
            with tarfile.open(archive) as t:
                try:
                    t.extractall(tmp, filter="data")
                except TypeError:  # Python sin filtros de tarfile
                    t.extractall(tmp)
        suffix = ".exe" if sys.platform == "win32" else ""
        found = next((p for n in names for p in sorted(tmp.rglob(n + suffix))), None)
        if not found:
            raise RuntimeError(f"El archivo descargado no contiene {names[0]}{suffix}")
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(found.parent), dest)
        exe = dest / found.name
        if sys.platform != "win32":
            for p in dest.iterdir():
                if p.is_file():
                    p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return exe
