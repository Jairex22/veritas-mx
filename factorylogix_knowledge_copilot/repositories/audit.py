"""Repositorio de auditoría append-only con cadena de hashes (evidencia de manipulación)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.logging_setup import redact
from core.text import truncate
from core.utils import new_id, now_iso
from database.connection import Database

GENESIS = "0" * 64
_FIELDS = ("id", "ts", "username", "role", "action", "object_type", "object_id", "result", "reason",
           "correlation_id", "details", "prev_hash")


def _compute_hash(record: dict[str, Any]) -> str:
    canonical = json.dumps({k: record[k] for k in _FIELDS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditRepository:
    def __init__(self, db: Database):
        self.db = db

    def append(self, *, username: str, role: str, action: str, object_type: str, object_id: str,
               result: str, reason: str = "", correlation_id: str = "", details: str = "") -> str:
        record = {
            "id": new_id("aud-"),
            "ts": now_iso(),
            "username": truncate(username or "anonymous", 120),
            "role": truncate(role or "-", 60),
            "action": truncate(action, 120),
            "object_type": truncate(object_type, 60),
            "object_id": truncate(object_id or "-", 120),
            "result": truncate(result, 40),
            "reason": truncate(redact(reason or ""), 500),
            "correlation_id": correlation_id or "-",
            "details": truncate(redact(details or ""), 1000),
        }
        with self.db.transaction() as conn:
            row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            record["prev_hash"] = row[0] if row else GENESIS
            record["hash"] = _compute_hash(record)
            cols = ", ".join(record)
            conn.execute(f"INSERT INTO audit_log ({cols}) VALUES ({','.join('?' for _ in record)})",
                         list(record.values()))
        return record["id"]

    def list(self, *, action: str = "", username: str = "", result: str = "", since: str = "",
             limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: list[Any] = []
        if action:
            sql += " AND action LIKE ?"
            params.append(f"%{action}%")
        if username:
            sql += " AND username = ?"
            params.append(username)
        if result:
            sql += " AND result = ?"
            params.append(result)
        if since:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(int(limit))
        return self.db.query(sql, params)

    def verify_chain(self) -> tuple[bool, int, str]:
        """Devuelve (ok, registros verificados, id del primer registro alterado)."""
        prev = GENESIS
        count = 0
        for row in self.db.query("SELECT * FROM audit_log ORDER BY seq ASC"):
            if row["prev_hash"] != prev or _compute_hash(row) != row["hash"]:
                return False, count, row["id"]
            prev = row["hash"]
            count += 1
        return True, count, ""

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM audit_log", default=0))
