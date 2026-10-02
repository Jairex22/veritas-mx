"""Logging técnico seguro (separado de la auditoría).

- Archivo rotativo en logs/app.log.
- Filtro de redacción de secretos (contraseñas, tokens, cabeceras Authorization, cadenas de conexión).
- Nunca se registra el texto completo de documentos ni de preguntas; solo longitudes e IDs.
"""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd|contrase(?:n|ñ)a|secret|token|api[_-]?key)\s*[=:]\s*\S+"), r"\1=***"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(basic|bearer)\s+\S+"), r"\1\2 ***"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),
    (re.compile(r"scrypt\$[^\s]+"), "scrypt$***"),
    (re.compile(r"pbkdf2\$[^\s]+"), "pbkdf2$***"),
]


def redact(text: str) -> str:
    redacted = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - un mensaje mal formado no debe romper el logging
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        return True


_CONFIGURED: set[str] = set()


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("flkc")
    key = str(logs_dir.resolve())
    if key in _CONFIGURED:
        return logger
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    _CONFIGURED.add(key)
    return logger


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"flkc.{name}")
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
