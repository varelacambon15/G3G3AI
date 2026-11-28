"""Actualizar G3G3AI a la última versión publicada en sus Releases de GitHub.

- Comprueba la última Release del repositorio de la aplicación y la compara con la versión en uso.
- Descarga el ejecutable de este sistema (G3G3AI.exe en Windows, G3G3AI-linux-x64 en Linux, G3G3AI-macos.zip con la
  aplicación en macOS), comprueba su huella
  SHA-256 con la que publica GitHub y lo pone en lugar del actual. Después la aplicación se reinicia sola.
- En Windows un .exe en marcha no se puede sobrescribir: un pequeño script espera a que se cierre, lo cambia y lo
  vuelve a abrir. En Linux se sustituye directamente y se vuelve a lanzar.
- La versión completa (con «G3G3AI-extras») sólo cambia el ejecutable: los motores incluidos siguen sirviendo.
- Si se ejecuta desde el código fuente no se sustituye nada: se avisa de que hay versión nueva.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__

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
        return "G3G3AI-macos.zip"
    return None


def installed_exe() -> Path | None:
    """Lo que se puede sustituir (sólo en la aplicación compilada): el ejecutable o, en macOS, la carpeta G3G3AI.app."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            app = next((p for p in exe.parents if p.suffix == ".app"), None)
            return app
        return exe
    return None


def mac_script(app: Path, stage: Path, pid: int, args: list[str]) -> str:
    """Script de macOS: espera a que la app se cierre, cambia la carpeta .app por la nueva y la vuelve a abrir."""
    import shlex
    q = shlex.quote
    argv = (" --args " + " ".join(q(a) for a in args)) if args else ""
    return ("#!/bin/sh\n"
            f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
            f"rm -rf {q(str(app) + '.old')}\n"
            f"if mv {q(str(app))} {q(str(app) + '.old')} && mv {q(str(stage / app.name))} {q(str(app))}; then\n"
            f"  open -n {q(str(app))}{argv}\n"
            f"  sleep 3; rm -rf {q(str(app) + '.old')} {q(str(stage))}\n"
            "else\n"
            f"  [ -d {q(str(app) + '.old')} ] && [ ! -d {q(str(app))} ] && mv {q(str(app) + '.old')} {q(str(app))}\n"
            f"  open -n {q(str(app))}{argv}\n"
            "fi\n"
            'rm -f "$0"\n')


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
        translocated = bool(exe and "AppTranslocation" in str(exe))
        if translocated:
            exe = None
        if not exe and translocated:
            how = "Mueve G3G3AI a la carpeta Aplicaciones y ábrela desde allí: así podrá actualizarse sola."
        elif not exe:
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
            new = exe.with_name(exe.name + (".new.zip" if sys.platform == "darwin" else ".new"))
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
        if (sys.platform == "win32" and head[:2] != b"MZ" or sys.platform.startswith("linux") and head != b"\x7fELF"
                or sys.platform == "darwin" and head[:2] != b"PK"):
            path.unlink(missing_ok=True)
            raise UpdateError("El archivo descargado no es un ejecutable válido.")

    def _swap_and_restart(self, exe: Path, new: Path) -> None:
        args = [a for a in sys.argv[1:]]
        if sys.platform == "darwin":
            stage = exe.parent / ".G3G3AI-actualizacion"
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir()
            r = subprocess.run(["ditto", "-x", "-k", str(new), str(stage)], capture_output=True, text=True)
            new.unlink(missing_ok=True)
            if r.returncode != 0 or not (stage / exe.name).is_dir():
                shutil.rmtree(stage, ignore_errors=True)
                raise UpdateError("No se pudo descomprimir la actualización: " + (r.stderr or "archivo no válido")[:200])
            script = exe.parent / ".g3g3ai-actualizar.sh"
            script.write_text(mac_script(exe, stage, os.getpid(), args), encoding="utf-8")
            os.chmod(script, 0o755)
            subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True)
        elif sys.platform == "win32":
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
            os.chmod(new, 0o755)
            os.replace(new, exe)                 # en Linux se puede sustituir un ejecutable en marcha
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
