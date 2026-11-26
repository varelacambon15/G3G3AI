"""Programas incluidos en la «edición completa» (carpeta G3G3AI-extras junto al ejecutable).

Estructura (la crea packaging/fetch_extras.py al compilar):
    G3G3AI-extras/
      llama-cpu/      llama-server(.exe) y sus bibliotecas — sólo procesador
      llama-vulkan/   llama-server(.exe) — con gráfica (Vulkan)
      sd/             sd(.exe) — generación de imágenes (stable-diffusion.cpp)
      whisper/        whisper-cli(.exe) — dictado por voz (whisper.cpp) — sólo Windows
      python/         Python portátil (python.exe / bin/python3) con pip y venv
      git/            Git portátil (cmd/git.exe) — sólo Windows
Si no existe la carpeta, todo funciona como antes (se descarga o se usa lo instalado en el sistema).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WIN = sys.platform == "win32"
EXE = ".exe" if WIN else ""


def extras_dir() -> Path | None:
    env = os.environ.get("G3G3AI_EXTRAS")
    cands = [Path(env)] if env else []
    if getattr(sys, "frozen", False):
        cands.append(Path(sys.executable).resolve().parent / "G3G3AI-extras")
    cands.append(Path(__file__).resolve().parent.parent / "G3G3AI-extras")   # al ejecutar desde el código fuente
    for c in cands:
        if c.is_dir():
            return c
    return None


def _first(base: Path | None, *names: str) -> Path | None:
    if not base or not base.is_dir():
        return None
    for n in names:
        for p in sorted(base.rglob(n)):
            if p.is_file():
                return p
    return None


def llama_server(prefer_gpu: bool) -> Path | None:
    d = extras_dir()
    if not d:
        return None
    order = ("llama-vulkan", "llama-cpu") if prefer_gpu else ("llama-cpu", "llama-vulkan")
    for sub in order:
        p = _first(d / sub, "llama-server" + EXE)
        if p:
            return p
    return None


def sd_binary() -> Path | None:
    d = extras_dir()
    return _first(d / "sd", "sd" + EXE, "sd-cli" + EXE) if d else None


def whisper_binary() -> Path | None:
    d = extras_dir()
    return _first(d / "whisper", "whisper-cli" + EXE, "main" + EXE) if d else None


def python_exe() -> Path | None:
    d = extras_dir()
    if not d:
        return None
    return _first(d / "python", "python.exe") if WIN else _first(d / "python", "python3", "python")


def path_additions() -> list[str]:
    """Carpetas a anteponer al PATH de los comandos: que «python», «pip» y «git» funcionen sin instalarlos."""
    out = []
    py = python_exe()
    if py:
        out.append(str(py.parent))
        scripts = py.parent / ("Scripts" if WIN else "")
        if WIN and scripts.is_dir():
            out.append(str(scripts))
    d = extras_dir()
    if d and WIN:
        g = _first(d / "git", "git.exe")
        if g:
            out.append(str(g.parent))
    return out


def command_env() -> dict | None:
    """Entorno para run_command con los programas incluidos delante en el PATH (None = el del sistema)."""
    add = path_additions()
    if not add:
        return None
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(add + [env.get("PATH", "")])
    return env


def summary() -> dict:
    d = extras_dir()
    return {"dir": str(d) if d else None,
            "llama_cpu": bool(d and _first(d / "llama-cpu", "llama-server" + EXE)),
            "llama_vulkan": bool(d and _first(d / "llama-vulkan", "llama-server" + EXE)),
            "sd": bool(sd_binary()), "whisper": bool(whisper_binary()), "python": bool(python_exe()),
            "git": bool(d and WIN and _first(d / "git", "git.exe"))}
