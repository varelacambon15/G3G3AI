"""Aplicación de escritorio (usada por el .exe de Windows y los binarios de PC).

Arranca el servidor en segundo plano y abre la interfaz en una ventana propia (pywebview / WebView2).
Si no hay pywebview, abre el navegador. Con --headless sólo arranca el servidor (para dejarlo
encendido y usarlo desde el móvil).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser


def _fix_stdio(log_dir) -> None:
    # En un .exe sin consola, stdout/stderr son None y uvicorn falla al configurar el registro.
    if sys.stdout is None or sys.stderr is None:
        log_dir.mkdir(parents=True, exist_ok=True)
        f = open(log_dir / "g3g3ai.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class DesktopApi:
    """Funciones nativas que la interfaz llama desde la ventana (window.pywebview.api)."""

    def __init__(self, cfg):
        self._cfg = cfg
        self._window = None

    def attach(self, window) -> None:
        self._window = window

    def save_file(self, path, suggested=None):
        """Abre «Guardar como…» y copia el archivo generado al sitio elegido."""
        import shutil

        import webview

        from .files import FileAccessError, Files
        try:
            src = Files(self._cfg).resolve(path)
        except FileAccessError as e:
            return {"ok": False, "error": str(e)}
        if not src.is_file():
            return {"ok": False, "error": f"No existe {src}"}
        name = suggested or src.name
        ext = src.suffix.lstrip(".")
        kind = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
        kw = {"file_types": (f"{ext.upper()} (*.{ext})", "Todos los archivos (*.*)")} if ext else {}
        try:
            res = self._window.create_file_dialog(kind, save_filename=name, **kw)
        except TypeError:
            res = self._window.create_file_dialog(kind, save_filename=name)
        if not res:
            return {"ok": False, "cancelled": True}
        dest = res if isinstance(res, str) else res[0]
        try:
            shutil.copyfile(src, dest)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(dest)}


def main() -> None:
    from .config import DATA_DIR, Config

    _fix_stdio(DATA_DIR)
    ap = argparse.ArgumentParser(prog="G3G3AI")
    ap.add_argument("--headless", action="store_true", help="Sólo servidor, sin ventana")
    ap.add_argument("--browser", action="store_true", help="Abrir en el navegador en vez de en ventana propia")
    ap.add_argument("--port", type=int)
    args = ap.parse_args()

    cfg = Config()
    port = args.port or cfg["port"]
    url = f"http://127.0.0.1:{port}/"

    server = None
    if _port_in_use(port):
        print(f"G3G3AI ya está en marcha en el puerto {port}; abriendo la interfaz.")
    else:
        import uvicorn

        from .server import create_app

        app = create_app(cfg)
        server = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=port, log_level="warning",
                                               use_colors=False))
        app.state.request_exit = lambda: setattr(server, "should_exit", True)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        if args.headless:
            print(f"G3G3AI escuchando en {url} (contraseña: {cfg['token']})")
            try:
                while t.is_alive():
                    t.join(1)
            except KeyboardInterrupt:
                server.should_exit = True
                t.join(10)
            return

    opened = False
    if not args.browser and not os.environ.get("G3G3AI_NO_WEBVIEW"):
        try:
            import webview  # pywebview

            # text_select=True: pywebview desactiva por defecto la selección de texto (no se podría copiar)
            api = DesktopApi(cfg)
            win = webview.create_window("G3G3AI", url, width=1280, height=840, min_size=(380, 500), text_select=True,
                                        js_api=api)
            api.attach(win)
            webview.start()
            opened = True
        except Exception as e:  # noqa: BLE001
            print(f"No se pudo abrir la ventana propia ({e}); uso el navegador.")
    if not opened:
        webbrowser.open(url)
        if server:
            try:
                while not server.should_exit:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    if server:
        server.should_exit = True
        time.sleep(1.5)


if __name__ == "__main__":
    main()
