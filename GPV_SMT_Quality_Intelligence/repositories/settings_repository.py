"""Ajustes editables desde la interfaz (sin secretos)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.config import EDITABLE_KEYS
from database.db import Database


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> dict:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT key, value_json FROM ApplicationSettings").fetchall()
        return {r["key"]: json.loads(r["value_json"]) for r in rows if r["key"] in EDITABLE_KEYS}

    def save(self, values: dict) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db.connection(write=True) as conn:
            for k, v in values.items():
                if k not in EDITABLE_KEYS:
                    raise ValueError(f"Clave no editable: {k}")
                conn.execute("INSERT INTO ApplicationSettings (key, value_json, updated_at) VALUES (?,?,?) "
                             "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                             (k, json.dumps(v), now))

    def reset(self) -> None:
        with self.db.connection(write=True) as conn:
            conn.execute("DELETE FROM ApplicationSettings")
