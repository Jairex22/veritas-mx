"""
Application configuration, filesystem paths and logging setup for
GPV XML Cleaner & Diagnostics.

Handles both "run from source" (python main.py) and "frozen" execution
(PyInstaller --onefile), always keeping data/ and logs/ next to the
real executable/script instead of inside the temporary PyInstaller
extraction folder.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from threading import Lock
from typing import Any, Dict

APP_NAME = "GPV XML Cleaner & Diagnostics"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "retention_days": 30,
    "safe_mode": True,
    "move_instead_of_delete": True,
    "archive_folder": "XML_Archive",
    "recent_days": 7,
    "warning_days": 30,
    "critical_days": 90,
    "api_port": 8765,
    "api_host": "127.0.0.1",
    "health_warning_old_ratio": 0.25,
    "health_critical_old_ratio": 0.50,
    "health_warning_size_gb": 10.0,
    "health_critical_size_gb": 25.0,
    "last_folder": "",
}


def get_base_dir() -> Path:
    """Return the directory that should own data/ and logs/.

    When frozen by PyInstaller, sys.executable points at the portable
    .exe, so settings/logs live next to it. When run from source, it is
    the project root (parent of the app/ package).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = LOGS_DIR / "xml_cleaner.log"

_settings_lock = Lock()
_logger_configured = False


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Dict[str, Any]:
    """Load settings.json, creating it with defaults if missing/corrupt."""
    ensure_directories()
    with _settings_lock:
        if not SETTINGS_FILE.exists():
            _write_settings_unlocked(DEFAULT_SETTINGS)
            return dict(DEFAULT_SETTINGS)
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data if isinstance(data, dict) else {})
            return merged
        except (json.JSONDecodeError, OSError):
            _write_settings_unlocked(DEFAULT_SETTINGS)
            return dict(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with _settings_lock:
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings)
        _write_settings_unlocked(merged)


def _write_settings_unlocked(settings: Dict[str, Any]) -> None:
    ensure_directories()
    tmp_file = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=4, ensure_ascii=False)
    tmp_file.replace(SETTINGS_FILE)


def get_logger(name: str = "gpv_xml_cleaner") -> logging.Logger:
    """Return the shared application logger, configuring it once."""
    global _logger_configured
    ensure_directories()
    logger = logging.getLogger(name)
    if not _logger_configured:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        try:
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.propagate = False
        _logger_configured = True
    return logger
