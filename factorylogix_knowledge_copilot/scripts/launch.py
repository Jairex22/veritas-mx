"""Lanzador multiplataforma usado por INICIAR_WINDOWS.bat.

- Inicializa la base de datos y el administrador inicial (muestra la contraseña temporal UNA vez).
- Detecta un puerto libre, inicia Streamlit en modo local (127.0.0.1) o red interna (0.0.0.0).
- Espera a que el servidor responda, abre el navegador y muestra las URL.
- Guarda el PID para DETENER_WINDOWS.bat.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_settings  # noqa: E402
from scripts.process_utils import is_running, read_pid_file, remove_pid_file, write_pid_file  # noqa: E402


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_port(host: str, start: int, end: int) -> int:
    for port in range(start, end + 1):
        if port_free(host, port):
            return port
    raise RuntimeError(f"No hay puertos libres entre {start} y {end}.")


def lan_addresses() -> list[str]:
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except socket.gaierror:
        return []
    return sorted({info[4][0] for info in infos if not info[4][0].startswith("127.")})


def wait_healthy(port: int, timeout: float = 90, process: subprocess.Popen | None = None) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca usar proxy para localhost
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return False  # el servidor terminó (error o DETENER_WINDOWS.bat) antes de estar listo
        try:
            with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=3) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            time.sleep(1)
    return False


def bootstrap() -> None:
    from services.container import build_container

    container = build_container()
    if container.bootstrap_password:
        print("=" * 70)
        print(" PRIMER ARRANQUE - USUARIO ADMINISTRADOR INICIAL")
        print("   Usuario: admin")
        print(f"   Contraseña temporal (un solo uso): {container.bootstrap_password}")
        print("   Se exigirá cambiarla al iniciar sesión.")
        print("   También se guardó en data\\PRIMER_ACCESO_ADMIN.txt (se borra al cambiarla).")
        print("=" * 70)
    for warning in container.startup_warnings:
        print("AVISO:", warning)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicia FactoryLogix Knowledge Copilot")
    parser.add_argument("--bind", choices=["local", "network"], default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="Inicializa y verifica sin iniciar el servidor")
    args = parser.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    pid_file = settings.path("paths.data_dir") / "server.pid"

    info = read_pid_file(pid_file)
    if info and is_running(info["pid"]):
        url = f"http://localhost:{info['port']}"
        print(f"La aplicación ya está en ejecución: {url}")
        if not args.no_browser and settings.get("server.open_browser", True):
            webbrowser.open(url)
        return 0
    remove_pid_file(pid_file)

    print("Inicializando base de datos y conocimiento...")
    bootstrap()
    if args.check_only:
        print("Verificación completada.")
        return 0

    bind = args.bind or settings.get("server.bind", "local")
    host = "0.0.0.0" if bind == "network" else "127.0.0.1"
    start = args.port or int(settings.get("server.preferred_port", 8501))
    port = find_port(host, start, max(start, int(settings.get("server.port_range_end", 8599))))

    cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.port", str(port),
           "--server.address", host, "--server.headless", "true", "--browser.gatherUsageStats", "false",
           "--global.developmentMode", "false"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env.setdefault("HF_HUB_OFFLINE", "1")
    process = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    write_pid_file(pid_file, process.pid, port, host)

    print("Iniciando servidor...")
    if not wait_healthy(port, process=process):
        if process.poll() is not None:
            print("El servidor se detuvo antes de quedar listo. Si no lo detuviste tú, revisa logs\\app.log.")
        else:
            print("ERROR: el servidor no respondió a tiempo. Revisa logs\\app.log.")
        process.terminate()
        remove_pid_file(pid_file)
        return 1
    local_url = f"http://localhost:{port}"
    print("=" * 70)
    print(f" FactoryLogix Knowledge Copilot listo: {local_url}")
    if bind == "network":
        for ip in lan_addresses():
            print(f" Red interna: http://{ip}:{port}")
        print(" (Si no conecta desde otros equipos, TI debe permitir el puerto en el firewall local.)")
    print(" Para detener: cierra esta ventana o ejecuta DETENER_WINDOWS.bat")
    print("=" * 70)
    if not args.no_browser and settings.get("server.open_browser", True):
        webbrowser.open(local_url)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0
    finally:
        remove_pid_file(pid_file)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - mensaje comprensible para el usuario final
        print(f"ERROR al iniciar: {type(exc).__name__}: {exc}")
        print(json.dumps({"hint": "Revisa logs\\app.log y ejecuta INSTALAR_WINDOWS.bat de nuevo."}))
        sys.exit(1)
