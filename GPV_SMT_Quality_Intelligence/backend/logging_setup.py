"""Logs diarios en logs/app_YYYY-MM-DD.log con sanitización de secretos."""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

_PATTERNS = [
    (re.compile(r"(Authorization\s*[:=]\s*)(Basic|Bearer)\s+[A-Za-z0-9+/=._-]+", re.I), r"\1\2 ***"),
    (re.compile(r"(password\s*[:=]\s*)\S+", re.I), r"\1***"),
    (re.compile(r"(GPV_ODATA_PASSWORD\s*=\s*)\S+", re.I), r"\1***"),
    (re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),
]


def sanitize(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


class SanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = sanitize(record.getMessage())
        record.msg, record.args = msg, None
        return True


class DailyFileHandler(logging.FileHandler):
    """Escribe en app_<fecha>.log y cambia de archivo al cambiar el día."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._day = date.today()
        super().__init__(self._path(), encoding="utf-8", delay=True)

    def _path(self) -> str:
        return str(self.directory / f"app_{self._day.isoformat()}.log")

    def emit(self, record: logging.LogRecord) -> None:
        today = date.today()
        if today != self._day:
            self.acquire()
            try:
                self.close()
                self._day = today
                self.baseFilename = self._path()
            finally:
                self.release()
        super().emit(record)


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    root = logging.getLogger("gpv")
    if any(isinstance(h, DailyFileHandler) for h in root.handlers):
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = DailyFileHandler(log_dir)
    fh.setFormatter(fmt)
    fh.addFilter(SanitizingFilter())
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(SanitizingFilter())
    root.addHandler(fh)
    root.addHandler(sh)
