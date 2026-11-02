"""Build GPV_Operations_Hub_v<version>.zip with a single root folder and a SHA-256 manifest.

  python tools/build_release.py --output ../dist

Excludes virtual environments, caches, runtime data, .env files and screenshots, and refuses to
package anything that looks like a secret.
"""
import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"
INCLUDE_DIRS = ["apps", "gpvhub", "templates", "static", "samples", "tools", "scripts"]
INCLUDE_FILES = ["manage.py", "requirements.txt", "requirements-optional.txt", ".env.example", ".gitignore"]
EXCLUDE_PARTS = {"__pycache__", ".venv", "data", "node_modules", ".pytest_cache", "dist"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".sqlite3", ".log", ".png.tmp"}
SECRET_PATTERNS = [re.compile(rb"-----BEGIN (RSA |EC |)PRIVATE KEY-----"), re.compile(rb"^GPV_SECRET_KEY=[^<\s]\S{9,}", re.M),
                   re.compile(rb"^GPV_DB_PASSWORD=[^<\s]\S*", re.M), re.compile(rb"ghp_[A-Za-z0-9]{30,}"), re.compile(rb"sk-[A-Za-z0-9]{30,}")]


def files():
    out = [ROOT / f for f in INCLUDE_FILES if (ROOT / f).exists()]
    out += sorted(ROOT.glob("*.md"))
    for d in INCLUDE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and not (set(p.relative_to(ROOT).parts) & EXCLUDE_PARTS) and p.suffix not in EXCLUDE_SUFFIX \
                    and not (p.name.startswith("e2e_") and p.suffix == ".png"):
                out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT.parent / "dist"))
    a = ap.parse_args()
    out_dir = Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"GPV_Operations_Hub_v{VERSION}"
    target = out_dir / f"{name}.zip"
    items = files()
    problems = []
    manifest = []
    for p in items:
        data = p.read_bytes()
        rel = p.relative_to(ROOT).as_posix()
        if p.name == ".env":
            problems.append(f"{rel}: archivo .env no permitido")
        for rx in SECRET_PATTERNS:
            if rx.search(data) and p.name != "build_release.py":
                problems.append(f"{rel}: posible secreto ({rx.pattern[:30]!r})")
        manifest.append((rel, len(data), hashlib.sha256(data).hexdigest()))
    if problems:
        print("ERROR: no se empaqueta:\n" + "\n".join(problems))
        sys.exit(1)
    man_text = "GPV Operations Hub v%s — manifiesto (ruta, bytes, sha256)\n" % VERSION
    man_text += "\n".join(f"{r}\t{s}\t{h}" for r, s, h in manifest) + "\n"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in items:
            zf.write(p, f"{name}/{p.relative_to(ROOT).as_posix()}")
        zf.writestr(f"{name}/MANIFEST.txt", man_text)
    with zipfile.ZipFile(target) as zf:
        bad = zf.testzip()
        roots = {n.split("/", 1)[0] for n in zf.namelist()}
        if bad or roots != {name}:
            print(f"ERROR: ZIP inválido (archivo dañado: {bad}, raíces: {roots})")
            sys.exit(1)
        count = len(zf.namelist())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{target}  ({target.stat().st_size // 1024} KB, {count} entradas, una carpeta raíz «{name}»)")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
