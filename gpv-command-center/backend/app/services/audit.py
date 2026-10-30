"""Motor de auditoría con cadena de hashes (evidencia de manipulación)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..core.context import get_correlation_id
from ..core.db import Database

GENESIS = "0" * 64


class AuditService:
    CATEGORIES = ("AUTH", "OPERATION", "CONFIG", "PRINT", "DIAGNOSTIC", "SYSTEM", "SECURITY")

    def __init__(self, db: Database, mode: str):
        self.db = db
        self.mode = mode

    @staticmethod
    def _digest(prev_hash: str, record: dict[str, Any]) -> str:
        payload = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256((prev_hash + payload).encode()).hexdigest()

    def record(self, *, category: str, action: str, outcome: str, username: str | None = None,
               role: str | None = None, target: str | None = None, details: dict | None = None) -> dict:
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        record = {
            "ts": ts, "correlation_id": get_correlation_id(), "username": username, "role": role,
            "mode": self.mode, "category": category, "action": action, "target": target,
            "outcome": outcome, "details": json.dumps(details or {}, ensure_ascii=False, sort_keys=True, default=str),
        }
        with self.db.transaction() as conn:
            row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            digest = self._digest(prev, record)
            cur = conn.execute(
                "INSERT INTO audit_log (ts, correlation_id, username, role, mode, category, action, target, outcome,"
                " details, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts, record["correlation_id"], username, role, self.mode, category, action, target, outcome,
                 record["details"], prev, digest),
            )
        return {"id": cur.lastrowid, **record, "hash": digest}

    def list(self, *, category: str | None = None, limit: int = 200, search: str | None = None) -> list[dict]:
        sql = "SELECT * FROM audit_log"
        clauses, params = [], []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if search:
            clauses.append("(action LIKE ? OR target LIKE ? OR username LIKE ? OR correlation_id LIKE ?)")
            params.extend([f"%{search}%"] * 4)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        out = []
        for r in self.db.query(sql, tuple(params)):
            d = dict(r)
            d["details"] = json.loads(d["details"] or "{}")
            out.append(d)
        return out

    def verify_chain(self) -> dict:
        prev = GENESIS
        count = 0
        for r in self.db.query("SELECT * FROM audit_log ORDER BY id ASC"):
            record = {k: r[k] for k in ("ts", "correlation_id", "username", "role", "mode", "category", "action",
                                         "target", "outcome", "details")}
            if r["prev_hash"] != prev or self._digest(prev, record) != r["hash"]:
                return {"valid": False, "checked": count, "broken_at_id": r["id"]}
            prev = r["hash"]
            count += 1
        return {"valid": True, "checked": count, "broken_at_id": None}

    def log_access(self, *, username: str | None, method: str, path: str, status: int,
                   duration_ms: float, client_ip: str | None) -> None:
        self.db.execute(
            "INSERT INTO access_log (ts, correlation_id, username, method, path, status, duration_ms, client_ip)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="milliseconds"), get_correlation_id(), username,
             method, path, status, round(duration_ms, 2), client_ip),
        )

    def list_access(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM access_log ORDER BY id DESC LIMIT ?",
                                               (max(1, min(limit, 1000)),))]
