"""GPV SMT Quality Intelligence - punto de entrada.

Uso:
    py -3.14 main.py                    # inicia el servidor local y abre el navegador
    py -3.14 main.py --no-browser       # sin abrir navegador
    py -3.14 main.py --port 8800
    py -3.14 main.py --set-credential   # guarda usuario/contraseña en el Administrador de credenciales de Windows
    py -3.14 main.py --check            # verifica configuración y sale
"""
from __future__ import annotations

import argparse
import getpass
import ipaddress
import logging
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api import Api  # noqa: E402
from backend.config import APP_VERSION, ConfigError, load_config, resolve_path  # noqa: E402
from backend.credentials import CredentialError, save_to_windows_credential_manager  # noqa: E402
from backend.logging_setup import setup_logging  # noqa: E402
from backend.server import create_server  # noqa: E402
from services.context import AppContext  # noqa: E402

log = logging.getLogger("gpv.main")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPV SMT Quality Intelligence")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--set-credential", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR de configuración: {exc}", file=sys.stderr)
        return 2

    if args.set_credential:
        target = cfg["odata"]["credential_target"]
        user = input("Usuario FactoryLogix: ").strip()
        pwd = getpass.getpass("Contraseña (no se mostrará): ")
        try:
            save_to_windows_credential_manager(target, user, pwd)
        except CredentialError as exc:
            print(f"No se pudo guardar la credencial: {exc}", file=sys.stderr)
            return 3
        print(f"Credencial guardada en el Administrador de credenciales de Windows como '{target}'.")
        print("Configure odata.credential_source = windows_credential_manager.")
        return 0

    setup_logging(resolve_path(cfg, "logs"))
    host = cfg["server"]["host"]
    port = args.port or int(cfg["server"]["port"])
    try:
        if not ipaddress.ip_address(host).is_loopback:
            log.warning("ATENCIÓN: el servidor escuchará en %s (no loopback). Requiere aprobación de TI.", host)
    except ValueError:
        log.warning("server.host no es una IP; se recomienda 127.0.0.1")

    ctx = AppContext(cfg)
    if args.check:
        print(f"GPV SMT Quality Intelligence v{APP_VERSION} | modo={ctx.config['mode']} | "
              f"base={ctx.config['odata']['base_url']} | db={resolve_path(cfg, 'database')}")
        return 0

    server, _ = create_server(Api(ctx), host, port)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}/"
    log.info("GPV SMT Quality Intelligence v%s escuchando en %s (modo %s)", APP_VERSION, url, ctx.config["mode"])
    if ctx.config["mode"] == "demo":
        log.info("MODO DEMOSTRACIÓN: no se consulta FactoryLogix; los datos son de ejemplo.")
    print(f"\n  Abra {url} en el navegador.  Ctrl+C para detener.\n")
    if cfg["server"]["open_browser"] and not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - abrir el navegador es opcional
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Detenido por el usuario")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
