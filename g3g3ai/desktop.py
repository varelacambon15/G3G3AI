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

            webview.create_window("G3G3AI", url, width=1280, height=840, min_size=(380, 500))
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
