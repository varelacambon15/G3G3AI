"""Punto de entrada: python -m g3g3ai [--host H] [--port P] [--show-token]"""
from __future__ import annotations

import argparse

import uvicorn

from .config import Config
from .llama import find_llama_server
from .server import create_app, lan_addresses


def main() -> None:
    ap = argparse.ArgumentParser(prog="g3g3ai", description="Cliente de IA local + API para Konkr")
    ap.add_argument("--host", help="Dirección de escucha (por defecto la de config, 0.0.0.0)")
    ap.add_argument("--port", type=int, help="Puerto (por defecto 8800)")
    ap.add_argument("--show-token", action="store_true", help="Muestra la contraseña de acceso y sale")
    ap.add_argument("--new-token", action="store_true", help="Genera una contraseña nueva y sale")
    args = ap.parse_args()

    cfg = Config()
    if args.new_token:
        import secrets
        cfg.set("token", secrets.token_urlsafe(9))
        args.show_token = True
    if args.show_token:
        print(cfg["token"])
        return
    host = args.host or cfg["host"]
    port = args.port or cfg["port"]

    print("\n  G3G3AI")
    print(f"  En este dispositivo:  http://127.0.0.1:{port}")
    if host in ("0.0.0.0", "::"):
        for ip in lan_addresses():
            print(f"  Desde móvil/portátil: http://{ip}:{port}/?token={cfg['token']}")
    print(f"  Contraseña: {cfg['token']}")
    if not find_llama_server(cfg["llama_server_path"]):
        print("  AVISO: no se encontró llama-server. Instálalo en Modelos → Motor (o ./install.sh en Linux).")
    print()
    app = create_app(cfg)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    app.state.request_exit = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
