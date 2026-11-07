"""Herramientas de programación para que la IA pueda crear programas (.exe en Windows).

- detect(): qué hay instalado (Python, Git, Node.js, .NET, compiladores...).
- Entorno de compilación propio: un entorno virtual de Python en la carpeta de datos de G3G3AI con
  PyInstaller (no toca el Python del sistema). En Windows, si falta Python, se instala con winget.
- build(): compila un script de Python a un ejecutable de un solo archivo.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .config import DATA_DIR

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WIN = sys.platform == "win32"
DEVENV = DATA_DIR / "devenv"

# Paquetes instalables con winget (sólo Windows), ámbito de usuario cuando es posible
WINGET = {
    "python": ("Python.Python.3.12", "Python 3.12"),
    "git": ("Git.Git", "Git"),
    "node": ("OpenJS.NodeJS.LTS", "Node.js LTS"),
    "dotnet": ("Microsoft.DotNet.SDK.8", ".NET 8 SDK"),
}


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _version(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    code, out = _run(cmd)
    if code != 0:
        return None
    m = re.search(r"\d+\.\d+(\.\d+)?", out)
    return m.group(0) if m else (out.splitlines()[0][:40] if out else "sí")


def system_python() -> list[str] | None:
    """Comando del Python del sistema (no el empaquetado dentro de G3G3AI.exe)."""
    cands = [["py", "-3"], ["python"], ["python3"]] if WIN else [["python3"], ["python"]]
    for c in cands:
        exe = shutil.which(c[0])
        if not exe or "WindowsApps" in exe:  # el alias de la Microsoft Store no es un Python real
            continue
        code, out = _run(c + ["--version"])
        if code == 0 and "Python 3" in out:
            return c
    return None


def devenv_python(cfg=None) -> Path | None:
    if cfg is not None and cfg["devenv_python"]:
        p = Path(cfg["devenv_python"])
        return p if p.is_file() else None
    p = DEVENV / ("Scripts/python.exe" if WIN else "bin/python")
    return p if p.is_file() else None


def pyinstaller_version(cfg=None) -> str | None:
    py = devenv_python(cfg)
    if not py:
        return None
    code, out = _run([str(py), "-m", "PyInstaller", "--version"], timeout=60)
    return out.strip().splitlines()[-1] if code == 0 and out else None


_cache: tuple[float, dict] | None = None


def detect(cfg=None, refresh: bool = False) -> dict:
    global _cache
    if _cache and not refresh and time.time() - _cache[0] < 60:
        return _cache[1]
    py = system_python()
    info = {
        "platform": sys.platform,
        "python": _version(py + ["--version"]) if py else None,
        "git": _version(["git", "--version"]),
        "node": _version(["node", "--version"]),
        "dotnet": _version(["dotnet", "--version"]),
        "gcc": _version(["gcc", "--version"]),
        "cl": "sí" if WIN and shutil.which("cl") else None,
        "cargo": _version(["cargo", "--version"]),
        "winget": _version(["winget", "--version"]) if WIN else None,
        "pyinstaller": pyinstaller_version(cfg),
    }
    _cache = (time.time(), info)
    return info


def summary(cfg=None) -> str:
    d = detect(cfg)
    names = {"python": "Python", "git": "Git", "node": "Node.js", "dotnet": ".NET SDK", "gcc": "GCC",
             "cl": "MSVC (cl)", "cargo": "Rust (cargo)", "pyinstaller": "PyInstaller (entorno de G3G3AI)"}
    have = [f"{names[k]} {v}" for k, v in d.items() if k in names and v]
    return ", ".join(have) or "ninguna"


class DevEnvInstaller:
    """Instalación en segundo plano con registro visible en la interfaz."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state = {"status": "idle", "log": [], "error": None, "what": None}
        self._task: asyncio.Task | None = None

    def _log(self, line: str):
        self.state["log"] = (self.state["log"] + [line])[-80:]

    async def _cmd(self, cmd: list[str], timeout: int = 1800) -> int:
        self._log("$ " + " ".join(cmd))
        proc = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, errors="replace",
            timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        for line in (proc.stdout + proc.stderr).strip().splitlines()[-15:]:
            self._log(line)
        return proc.returncode

    def start(self, what: str) -> dict:
        if self._task and not self._task.done():
            return self.state
        self.state = {"status": "running", "log": [], "error": None, "what": what}
        self._task = asyncio.create_task(self._run(what))
        return self.state

    async def _run(self, what: str):
        global _cache
        try:
            if what == "pyinstaller":
                await self._setup_devenv()
            elif what in WINGET:
                if not WIN or not shutil.which("winget"):
                    raise RuntimeError("Instalación automática sólo disponible en Windows con winget. "
                                       "En Linux usa el gestor de paquetes de tu distribución.")
                pkg = WINGET[what][0]
                code = await self._cmd(["winget", "install", "--id", pkg, "-e", "--scope", "user",
                                        "--accept-package-agreements", "--accept-source-agreements",
                                        "--disable-interactivity"])
                if code != 0:  # algunos paquetes no admiten ámbito de usuario
                    code = await self._cmd(["winget", "install", "--id", pkg, "-e", "--accept-package-agreements",
                                            "--accept-source-agreements", "--disable-interactivity"])
                if code != 0:
                    raise RuntimeError(f"winget terminó con código {code}")
                self._log("Instalado. Puede que haga falta reiniciar G3G3AI para que se detecte.")
            else:
                raise RuntimeError(f"Herramienta desconocida: {what}")
            self.state["status"] = "done"
        except Exception as e:  # noqa: BLE001
            self.state["status"], self.state["error"] = "error", str(e)
            self._log("ERROR: " + str(e))
        finally:
            _cache = None

    async def _setup_devenv(self):
        py = system_python()
        if not py:
            if WIN and shutil.which("winget"):
                self._log("No hay Python en el sistema: instalándolo con winget…")
                await self._cmd(["winget", "install", "--id", WINGET["python"][0], "-e", "--scope", "user",
                                 "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"])
                # winget no actualiza el PATH de este proceso: buscamos la instalación de usuario
                local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
                found = sorted(local.glob("Python3*/python.exe"), reverse=True)
                py = [str(found[0])] if found else system_python()
            if not py:
                raise RuntimeError("Hace falta Python 3 en el equipo. Instálalo desde python.org y vuelve a intentarlo.")
        if not devenv_python():
            if await self._cmd(py + ["-m", "venv", str(DEVENV)]) != 0:
                raise RuntimeError("No se pudo crear el entorno virtual de Python.")
        vpy = str(devenv_python())
        await self._cmd([vpy, "-m", "pip", "install", "--upgrade", "pip"])
        if await self._cmd([vpy, "-m", "pip", "install", "--upgrade", "pyinstaller"]) != 0:
            raise RuntimeError("No se pudo instalar PyInstaller.")
        self._log("✔ Entorno listo: la IA ya puede crear ejecutables con build_exe.")


def build(cfg, script: Path, name: str | None = None, windowed: bool = False, packages: list[str] | None = None,
          icon: Path | None = None, sandbox_wrap=None) -> tuple[Path, str]:
    """Compila un script de Python a un único ejecutable en <carpeta del script>/dist. Devuelve (ruta, registro)."""
    py = devenv_python(cfg)
    if not py:
        raise RuntimeError("Falta el entorno de compilación. Prepáralo en Ajustes → Herramientas de programación.")
    log = []
    if packages:
        clean = [p for p in packages if re.fullmatch(r"[A-Za-z0-9_.\-\[\],<>=!~]+", p)]
        if clean:
            code, out = _run([str(py), "-m", "pip", "install", *clean], timeout=1200)
            log.append(out[-3000:])
            if code != 0:
                raise RuntimeError("No se pudieron instalar los paquetes:\n" + out[-1500:])
    name = re.sub(r"[^\w\-]", "_", name or script.stem)[:60]
    dist = script.parent / "dist"
    with tempfile.TemporaryDirectory(prefix="g3build-") as tmp:
        cmd = [str(py), "-m", "PyInstaller", "--noconfirm", "--onefile", "--clean", "--name", name,
               "--distpath", str(dist), "--workpath", tmp, "--specpath", tmp]
        if windowed:
            cmd.append("--windowed")
        if icon and icon.is_file():
            cmd += ["--icon", str(icon)]
        cmd.append(str(script))
        argv = sandbox_wrap(cmd, script.parent, Path(tmp)) if sandbox_wrap else cmd
        try:
            r = subprocess.run(argv, cwd=str(script.parent), capture_output=True, text=True, errors="replace",
                               timeout=1800, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("La compilación tardó más de 30 minutos.") from e
        out = (r.stdout + r.stderr).strip()
        log.append(out[-4000:])
        exe = dist / (name + (".exe" if WIN else ""))
        if r.returncode != 0 or not exe.is_file():
            errs = [l for l in out.splitlines() if re.search(r"error|Error|Traceback|not found|No module", l)]
            raise RuntimeError("PyInstaller falló:\n" + "\n".join((errs or out.splitlines())[-25:]))
    return exe, "\n".join(log)
