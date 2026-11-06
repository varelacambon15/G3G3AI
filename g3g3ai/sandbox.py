"""Seguridad de los comandos que ejecuta la IA.

1) Evaluación del comando: algunos se bloquean siempre; otros obligan a pedir confirmación
   aunque el permiso esté en "Automático".
2) Aislamiento (Linux, con bubblewrap — el mismo que usa Flatpak): el comando ve el sistema en sólo
   lectura, sólo puede escribir en las carpetas que la IA puede modificar (+ /tmp temporal) y las
   rutas protegidas aparecen vacías.
"""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
from pathlib import Path

BLOCK = [
    (r"\brm\s+(-{1,2}[\w-]+\s+)*(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\s+(-{1,2}[\w-]+\s+)*"
     r"(/|~/?|\$HOME/?|/\*|~/\*|\$HOME/\*|/(home|usr|etc|var|boot|opt|bin|lib)/?)(\s|$)",
     "borrar todo el sistema o la carpeta personal"),
    (r"\bmkfs(\.\w+)?\b", "formatear un disco"),
    (r"\bdd\b[^|;&]*\bof=/dev/(sd|nvme|mmcblk|hd|vd)", "escribir directamente en un disco"),
    (r">\s*/dev/(sd|nvme|mmcblk|hd|vd)\w*", "escribir directamente en un disco"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "bomba fork"),
    (r"\bformat(\.com)?\s+[a-zA-Z]:", "formatear una unidad"),
    (r"\b(rd|rmdir)\s+/s\s+(/q\s+)?[a-zA-Z]:\\?\s*$", "borrar una unidad completa"),
    (r"\bdel\s+/[sfq].*\s[a-zA-Z]:\\\*?\s*$", "borrar una unidad completa"),
    (r"\bchmod\s+(-R\s+)?[0-7]{3,4}\s+/\s*$", "cambiar permisos de todo el sistema"),
]
WARN = [
    (r"\b(sudo|su|doas|pkexec|runas)\b", "pide privilegios de administrador"),
    (r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^|]*\|\s*(sudo\s+)?(ba|z|fi)?sh\b", "descarga y ejecuta un script de internet"),
    (r"\b(shutdown|reboot|poweroff|halt|Stop-Computer|Restart-Computer)\b", "apaga o reinicia el equipo"),
    (r"\bsystemctl\s+(?!--user)(start|stop|restart|enable|disable|mask)", "cambia servicios del sistema"),
    (r"\b(rm|del|rd|rmdir|Remove-Item)\b.*(-[a-zA-Z]*[rR]|/s\b|-Recurse)", "borra carpetas de forma recursiva"),
    (r"\b(chmod|chown)\s+-R\b", "cambia permisos de forma recursiva"),
    (r"\bgit\s+push\b.*(--force|-f\b)", "fuerza un push de git"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f)", "descarta cambios de git"),
    (r"\b(reg\s+(add|delete)|Set-ItemProperty\s+.*HK)", "modifica el registro de Windows"),
    (r"\bcrontab\b|\bschtasks\b", "programa tareas"),
    (r"\b(ssh|scp|rsync)\b.*@", "se conecta a otro equipo"),
    (r"(^|[\s;&|])(~|\$HOME)/\.(ssh|gnupg|aws|bashrc|profile|zshrc|config/autostart)", "toca configuración sensible"),
]


def assess(command: str) -> tuple[str, list[str]]:
    """Devuelve ("block" | "warn" | "ok", motivos)."""
    for pat, why in BLOCK:
        if re.search(pat, command, re.I | re.M):
            return "block", [why]
    reasons = [why for pat, why in WARN if re.search(pat, command, re.I | re.M)]
    return ("warn" if reasons else "ok"), reasons


@functools.lru_cache(maxsize=1)
def bwrap_path() -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    exe = shutil.which("bwrap")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
                           capture_output=True, timeout=10)
        return exe if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def available(cfg) -> bool:
    return (cfg["command_sandbox"] or "auto") != "off" and bwrap_path() is not None


def wrap(command: str, cwd: Path, writable: list[Path], hidden: list[Path]) -> list[str]:
    """Construye la orden bwrap: todo en sólo lectura salvo `writable`; `hidden` vacías."""
    exe = bwrap_path()
    assert exe
    args = [exe, "--die-with-parent", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp"]
    for w in writable:
        w.mkdir(parents=True, exist_ok=True)
        args += ["--bind", str(w), str(w)]
    for h in hidden:
        if h.is_dir():
            args += ["--tmpfs", str(h)]
        elif h.exists():
            args += ["--ro-bind", "/dev/null", str(h)]
    args += ["--chdir", str(cwd), "--setenv", "G3G3AI_SANDBOX", "1", "bash", "-c", command]
    return args
