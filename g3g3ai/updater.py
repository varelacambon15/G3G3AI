"""Actualizar G3G3AI a la última versión publicada en sus Releases de GitHub.

- Comprueba la última Release del repositorio de la aplicación y la compara con la versión en uso.
- Descarga el ejecutable de este sistema (G3G3AI.exe en Windows, G3G3AI-linux-x64 en Linux), comprueba su huella
  SHA-256 con la que publica GitHub y lo pone en lugar del actual. Después la aplicación se reinicia sola.
- En Windows un .exe en marcha no se puede sobrescribir: un pequeño script espera a que se cierre, lo cambia y lo
  vuelve a abrir. En Linux se sustituye directamente y se vuelve a lanzar.
- La versión completa (con «G3G3AI-extras») sólo cambia el ejecutable: los motores incluidos siguen sirviendo.
- Si se ejecuta desde el código fuente no se sustituye nada: se avisa de que hay versión nueva.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__

log = logging.getLogger(__name__)

REPO = "varelacambon15/G3G3AI"
API = "https://api.github.com"
CHECK_EVERY = 6 * 3600


class UpdateError(Exception):
    pass


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", str(v or ""))[:3]
    return tuple(int(x) for x in nums) + (0,) * (3 - len(nums))


def asset_name() -> str | None:
    if sys.platform == "win32":
        return "G3G3AI.exe"
    if sys.platform.startswith("linux"):
        return "G3G3AI-linux-x64"
    if sys.platform == "darwin":
        return "G3G3AI-macos-arm64"   # binario de la .app (Contents/MacOS/G3G3AI); la .app completa va aparte
    return None


def installed_exe() -> Path | None:
    """El ejecutable que se puede sustituir (sólo en la aplicación compilada)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


class Updater:
    def __init__(self, cfg, token_fn=lambda: ""):
        self.cfg, self.token_fn = cfg, token_fn
        self.repo = os.environ.get("G3G3AI_UPDATE_REPO") or REPO
        self.state = {"phase": "idle", "done": 0, "total": 0, "error": None, "version": None}
        self._last: tuple[float, dict] | None = None
        self.request_exit = None            # lo pone el servidor: cerrar la app para reiniciarla

    def _headers(self, accept: str = "application/vnd.github+json") -> dict:
        h = {"Accept": accept, "User-Agent": f"G3G3AI/{__version__}", "X-GitHub-Api-Version": "2022-11-28"}
        tok = (self.token_fn() or "").strip()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def check(self, force: bool = False) -> dict:
        if os.environ.get("G3G3AI_NO_UPDATE_CHECK"):
            return {"current": __version__, "latest": __version__, "newer": False, "can_install": False, "disabled": True,
                    "reason": "Comprobación de actualizaciones desactivada.", "asset": None, "notes": "", "name": "", "url": None}
        if self._last and not force and time.time() - self._last[0] < CHECK_EVERY:
            return self._last[1]
        import httpx
        try:
            r = httpx.get(f"{API}/repos/{self.repo}/releases/latest", headers=self._headers(), timeout=20, follow_redirects=True)
        except httpx.HTTPError as e:
            raise UpdateError(f"No se pudo consultar GitHub: {e}") from e
        if r.status_code == 404:
            raise UpdateError("No encuentro versiones publicadas. Si el repositorio es privado, conecta tu cuenta de "
                              "GitHub en «Conectores».")
        if r.status_code >= 400:
            raise UpdateError(f"GitHub respondió {r.status_code} al buscar actualizaciones.")
        rel = r.json()
        latest = str(rel.get("tag_name") or "").lstrip("v")
        want = asset_name()
        asset = next((a for a in rel.get("assets") or [] if a.get("name") == want), None)
        exe = installed_exe()
        if not exe:
            how = "Estás usando G3G3AI desde el código fuente: actualiza con «git pull» (o descarga la versión nueva)."
        elif not asset:
            how = "Esta versión no tiene ejecutable para tu sistema; descárgala desde la página de la versión."
        else:
            how = None
        out = {"current": __version__, "latest": latest, "newer": parse_version(latest) > parse_version(__version__),
               "name": rel.get("name") or f"G3G3AI {latest}", "notes": (rel.get("body") or "")[:6000],
               "published": rel.get("published_at"), "url": rel.get("html_url"),
               "asset": {"name": asset["name"], "size": asset.get("size"), "id": asset.get("id"),
                         "digest": asset.get("digest"), "download": asset.get("browser_download_url")} if asset else None,
               "can_install": bool(exe and asset), "reason": how, "exe": str(exe) if exe else None}
        self._last = (time.time(), out)
        return out

    # --- Descargar e instalar -----------------------------------------------------------
    def start_install(self) -> dict:
        if self.state["phase"] in ("downloading", "installing", "restarting"):
            return self.state
        info = self.check(force=True)
        if not info["newer"]:
            raise UpdateError(f"Ya tienes la última versión ({info['current']}).")
        if not info["can_install"]:
            raise UpdateError(info["reason"] or "No se puede actualizar automáticamente.")
        self.state = {"phase": "downloading", "done": 0, "total": info["asset"]["size"] or 0, "error": None,
                      "version": info["latest"]}
        threading.Thread(target=self._install, args=(info,), daemon=True).start()
        return self.state

    def _install(self, info: dict) -> None:
        try:
            exe = Path(info["exe"])
            new = exe.with_name(exe.name + ".new")
            self._download(info["asset"], new)
            self.state["phase"] = "installing"
            self._verify(new, info["asset"])
            self.state["phase"] = "restarting"
            self._swap_and_restart(exe, new)
        except Exception as e:  # noqa: BLE001
            self.state.update(phase="error", error=str(e))

    def _download(self, asset: dict, dest: Path) -> None:
        import httpx
        url = f"{API}/repos/{self.repo}/releases/assets/{asset['id']}"
        sha = hashlib.sha256()
        with httpx.stream("GET", url, headers=self._headers("application/octet-stream"), timeout=httpx.Timeout(30, read=120),
                          follow_redirects=True) as r:
            if r.status_code >= 400:
                raise UpdateError(f"GitHub respondió {r.status_code} al descargar {asset['name']}.")
            self.state["total"] = int(r.headers.get("content-length") or asset.get("size") or 0)
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    sha.update(chunk)
                    self.state["done"] += len(chunk)
        self._sha = sha.hexdigest()

    def _verify(self, path: Path, asset: dict) -> None:
        size = path.stat().st_size
        if asset.get("size") and size != asset["size"]:
            raise UpdateError("La descarga está incompleta; vuelve a intentarlo.")
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:") and digest[7:].lower() != self._sha:
            path.unlink(missing_ok=True)
            raise UpdateError("La huella del archivo descargado no coincide con la publicada: no se instala.")
        with open(path, "rb") as f:
            head = f.read(4)
        if sys.platform == "win32" and head[:2] != b"MZ" or sys.platform.startswith("linux") and head != b"\x7fELF":
            path.unlink(missing_ok=True)
            raise UpdateError("El archivo descargado no es un ejecutable válido.")
        if sys.platform == "darwin" and head not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            # MH_MAGIC_64 (arm64) o FAT_MAGIC (binario universal)
            path.unlink(missing_ok=True)
            raise UpdateError("El archivo descargado no es un ejecutable de macOS válido.")

    def _resign_macos(self, exe: Path) -> None:
        """Al cambiar el binario dentro de G3G3AI.app, la firma ad hoc deja de valer y macOS
        mataría el proceso al arrancar. Se vuelve a firmar la .app entera (ad hoc, sin cuenta).
        Si la .app no está firmada o no hay codesign, no se hace nada: no es un error."""
        app = next((p for p in exe.parents if p.suffix == ".app"), None)
        if app is None:
            return
        try:
            r = subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                log.warning("No se pudo volver a firmar %s: %s", app, (r.stderr or "").strip())
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo volver a firmar %s: %s", app, e)

    def _swap_and_restart(self, exe: Path, new: Path) -> None:
        args = [a for a in sys.argv[1:]]
        if sys.platform == "win32":
            # Un .exe en marcha no se puede sobrescribir: lo cambia un script en cuanto esta app se cierra
            script = exe.with_name("g3g3ai-actualizar.cmd")
            pid = os.getpid()
            argline = " ".join(f'"{a}"' for a in args)
            script.write_text(
                "@echo off\r\n"
                ":wait\r\n"
                f'tasklist /FI "PID eq {pid}" /NH | find /I "{exe.name}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
                f'move /Y "{exe}" "{exe}.old" >nul\r\n'
                f'move /Y "{new}" "{exe}" >nul || move /Y "{exe}.old" "{exe}" >nul\r\n'
                f'start "" "{exe}" {argline}\r\n'
                "timeout /t 5 /nobreak >nul\r\n"
                f'del /F /Q "{exe}.old" >nul 2>&1\r\n'
                '(goto) 2>nul & del "%~f0"\r\n', encoding="utf-8")
            subprocess.Popen(["cmd", "/c", str(script)], creationflags=0x00000008 | 0x00000200 | 0x08000000,
                             close_fds=True)      # DETACHED_PROCESS | NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            # Linux y macOS: se puede sustituir un ejecutable en marcha y volver a lanzar.
            # En macOS el binario vive dentro de G3G3AI.app/Contents/MacOS/, y al cambiarlo
            # queda actualizada la .app entera (todo lo demás va dentro del binario).
            os.chmod(new, 0o755)
            os.replace(new, exe)
            if sys.platform == "darwin":
                self._resign_macos(exe)
            env = {**os.environ, "G3G3AI_WAIT_PID": str(os.getpid())}
            subprocess.Popen([str(exe), *args], env=env, start_new_session=True, close_fds=True)
        self._exit_soon()

    def _exit_soon(self) -> None:
        def bye():
            time.sleep(1.5)                      # deja que la interfaz reciba el «reiniciando»
            if self.request_exit:
                try:
                    self.request_exit()
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1.5)
            os._exit(0)
        threading.Thread(target=bye, daemon=True).start()


def wait_for_previous() -> None:
    """Al arrancar tras una actualización (Linux): esperar a que la versión anterior suelte el puerto."""
    pid = os.environ.pop("G3G3AI_WAIT_PID", None)
    if not pid:
        return
    for _ in range(60):
        try:
            os.kill(int(pid), 0)
        except (OSError, ValueError):
            return
        time.sleep(0.25)
