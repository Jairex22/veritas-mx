"""Logs estructurados (JSON por línea) con identificador de correlación."""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

from .context import get_correlation_id

_SENSITIVE = ("password", "token", "secret", "authorization", "cookie")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": get_correlation_id(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = {k: ("***" if any(s in k.lower() for s in _SENSITIVE) else v) for k, v in extra.items()}
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("gpv")
    if getattr(root, "_gpv_configured", False):
        return
    root.setLevel(level)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    root.addHandler(file_handler)
    root.addHandler(console)
    root.propagate = False
    root._gpv_configured = True  # type: ignore[attr-defined]
