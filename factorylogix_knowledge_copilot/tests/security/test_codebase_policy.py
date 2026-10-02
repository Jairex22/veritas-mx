"""Criterios de aceptación verificables sobre el código: sin archivos vacíos, sin `pass`, sin TODO,
sin credenciales embebidas y sin llamadas a APIs de nube de LLM."""
import ast
import re

from tests.conftest import ROOT

EXCLUDED_DIRS = {".venv", "__pycache__", ".pytest_cache", "data", "logs", "reports", "dist", "wheelhouse",
                 "models_local", "files"}


def project_files(suffixes):
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in suffixes and not (set(path.relative_to(ROOT).parts) & EXCLUDED_DIRS) \
                and not path.name.startswith("scratch_"):
            yield path


def test_no_empty_files():
    empty = [str(p.relative_to(ROOT)) for p in project_files({".py", ".md", ".yaml", ".bat", ".sql", ".toml", ".txt",
                                                               ".csv", ".html"}) if p.stat().st_size == 0]
    assert not empty, empty


def test_no_pass_statements_or_todos_in_code():
    offenders = []
    for path in project_files({".py"}):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders += [f"{path.name}:{n.lineno} pass" for n in ast.walk(tree) if isinstance(n, ast.Pass)]
        offenders += [f"{path.name}: TODO" for line in source.splitlines()
                      if re.search(r"#\s*(TODO|FIXME|XXX)\b", line)]
    assert not offenders, offenders


def test_no_cloud_llm_apis_or_hardcoded_credentials():
    forbidden = re.compile(r"api\.openai\.com|import openai|anthropic\.com|from anthropic|generativelanguage")
    credential = re.compile(r"(password|passwd|secret|token)\s*=\s*['\"][^'\"]{6,}['\"]", re.IGNORECASE)
    offenders = []
    for path in project_files({".py", ".yaml", ".toml"}):
        if "tests" in path.relative_to(ROOT).parts:
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden.search(text):
            offenders.append(f"{path.name}: API de nube")
        for match in credential.finditer(text):
            offenders.append(f"{path.name}: {match.group(0)[:40]}")
    assert not offenders, offenders


def test_streamlit_telemetry_disabled():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "gatherUsageStats = false" in config and "showErrorDetails = false" in config


def test_bat_scripts_are_crlf_and_do_not_use_powershell():
    for path in ROOT.rglob("*.bat"):
        raw = path.read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), path.name
        commands = [l for l in raw.decode("ascii").lower().splitlines()
                    if not l.strip().startswith(("rem", "echo", "::"))]
        assert not any("powershell" in l for l in commands), path.name
