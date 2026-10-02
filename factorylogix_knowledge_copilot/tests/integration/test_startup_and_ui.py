"""Prueba de arranque real del servidor y renderizado de todas las páginas (Streamlit AppTest)."""
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from streamlit.testing.v1 import AppTest

from scripts.launch import find_port, port_free
from scripts.process_utils import is_running, read_pid_file, write_pid_file
from tests.conftest import ROOT

PAGES = ["chat", "sources", "training_center", "catalog", "governance", "feedback_review", "evaluations",
         "incidents", "analytics", "audit", "users", "settings", "health"]


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    for key, sub in (("FLKC_DATA_DIR", "data"), ("FLKC_FILES_DIR", "files"), ("FLKC_ATTACHMENTS_DIR", "att"),
                     ("FLKC_REPORTS_DIR", "rep"), ("FLKC_LOGS_DIR", "logs")):
        monkeypatch.setenv(key, str(tmp_path / sub))
    monkeypatch.setenv("FLKC_DATABASE", str(tmp_path / "data" / "ui.db"))
    from ui.state import get_container
    get_container.clear()  # cada prueba usa su propia base de datos temporal
    yield tmp_path
    get_container.clear()


def test_port_and_pid_helpers(tmp_path):
    port = find_port("127.0.0.1", 8650, 8700)
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
        s.listen()
        assert not port_free("127.0.0.1", port)
        assert find_port("127.0.0.1", port, port + 20) != port
    pid_file = tmp_path / "server.pid"
    write_pid_file(pid_file, os.getpid(), 8501, "127.0.0.1")
    assert read_pid_file(pid_file)["port"] == 8501 and is_running(os.getpid())
    assert not is_running(999999)


def test_real_server_starts_and_answers_health(isolated_env):
    """Arranque real: launch.py --check-only y luego streamlit en un puerto libre."""
    env = dict(os.environ)
    check = subprocess.run([sys.executable, "scripts/launch.py", "--check-only", "--no-browser"], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
    assert check.returncode == 0, check.stdout + check.stderr
    assert "PRIMER ARRANQUE" in check.stdout and "admin" in check.stdout
    port = find_port("127.0.0.1", 8710, 8790)
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port),
                             "--server.address", "127.0.0.1", "--server.headless", "true"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline, healthy = time.time() + 90, False
        while time.time() < deadline and not healthy:
            try:
                with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=3) as resp:
                    healthy = resp.status == 200
            except OSError:
                time.sleep(1)
        assert healthy, "el servidor no respondió /_stcore/health"
        with opener.open(f"http://127.0.0.1:{port}/", timeout=10) as resp:
            assert resp.status == 200
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def test_login_and_forced_password_change(isolated_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception
    password = re.search(r"un solo uso\): (\S+)",
                         (isolated_env / "data" / "PRIMER_ACCESO_ADMIN.txt").read_text(encoding="utf-8")).group(1)
    at.text_input[0].input("admin")
    at.text_input[1].input("incorrecta")
    next(b for b in at.button if b.label == "Entrar").click()
    at.run()
    assert at.error and "inválidos" in at.error[0].value
    at.text_input[0].input("admin")
    at.text_input[1].input(password)
    next(b for b in at.button if b.label == "Entrar").click()
    at.run()
    assert any("Cambio de contraseña obligatorio" in m.value for m in at.markdown)
    at.text_input[0].input(password)
    at.text_input[1].input("Planta-Segura-2026")
    at.text_input[2].input("Planta-Segura-2026")
    next(b for b in at.button if b.label == "Cambiar contraseña").click()
    at.run()
    assert not at.exception
    assert not (isolated_env / "data" / "PRIMER_ACCESO_ADMIN.txt").exists()
    at.text_area[0].input("¿Qué hago si el operador no está certificado?")
    next(b for b in at.button if b.label == "Preguntar").click()
    at.run()
    assert not at.exception
    assert any("no debe procesar" in m.value for m in at.markdown)


@pytest.mark.parametrize("username", ["admin", "demo_operator", "demo_auditor"])
def test_all_pages_render_without_exceptions(isolated_env, username):
    from services.container import build_container
    build_container()
    for name in PAGES:
        script = f'''
import sys; sys.path.insert(0, r"{ROOT}")
import streamlit as st
from ui.state import container
from pages import {name}
c = container()
st.session_state["user"] = c.auth.build_user(c.auth.users.get_by_username("{username}"))
{name}.render()
'''
        at = AppTest.from_string(script, default_timeout=180)
        at.run()
        assert not at.exception, (username, name, [e.value for e in at.exception])


def test_launcher_start_and_stop_scripts(isolated_env):
    """Ciclo completo del lanzador usado por los .bat: launch.py -> servidor -> stop.py."""
    env = dict(os.environ)
    assert subprocess.run([sys.executable, "scripts/check_env.py", "python"], cwd=ROOT).returncode == 0
    port = find_port("127.0.0.1", 8800, 8890)
    launcher = subprocess.Popen([sys.executable, "scripts/launch.py", "--no-browser", "--port", str(port)], cwd=ROOT,
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_file = isolated_env / "data" / "server.pid"
    try:
        deadline = time.time() + 120
        while time.time() < deadline and not (pid_file.is_file() and not port_free("127.0.0.1", port)):
            time.sleep(1)
        info = read_pid_file(pid_file)
        assert info and info["port"] == port and is_running(info["pid"])
        again = subprocess.run([sys.executable, "scripts/launch.py", "--no-browser"], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=120)
        assert "ya está en ejecución" in again.stdout
        stop = subprocess.run([sys.executable, "scripts/stop.py"], cwd=ROOT, env=env, capture_output=True,
                              text=True, timeout=60)
        assert "Servidor detenido" in stop.stdout
        launcher.wait(timeout=60)
        assert not pid_file.exists()
    finally:
        if launcher.poll() is None:
            launcher.kill()


def test_python_app_py_delegates_to_launcher(isolated_env):
    """'python app.py' (modo bare) no debe mostrar avisos ScriptRunContext: delega al lanzador."""
    proc = subprocess.run([sys.executable, "app.py", "--check-only", "--no-browser"], cwd=ROOT, env=dict(os.environ),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0 and "Verificación completada" in proc.stdout
    assert "ScriptRunContext" not in proc.stdout + proc.stderr
