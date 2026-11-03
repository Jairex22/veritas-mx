"""SQLite persistence: OData cache, query history, saved reports and settings.

* One connection shared across threads, guarded by a lock (SQLite in WAL mode).
* Timestamps stored as ISO-8601 UTC text (no deprecated sqlite3 datetime adapters).
* Retention policy and maximum file size are enforced by ``cleanup()``.
* No credentials are ever stored. Values written to ``application_settings`` are
  validated by the service layer and contain only non-secret parameters.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from timeutil import iso_utc, utc_now

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS odata_cache (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    query_set_id     TEXT NOT NULL,
    signature        TEXT NOT NULL,
    data_mode        TEXT NOT NULL CHECK (data_mode IN ('demo', 'live')),
    query_params     TEXT NOT NULL,
    relative_url     TEXT NOT NULL,
    fetched_at       TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    record_count     INTEGER NOT NULL,
    records_json     TEXT NOT NULL,
    more_available   INTEGER NOT NULL DEFAULT 0,
    validation_state TEXT NOT NULL,
    response_hash    TEXT NOT NULL,
    schema_hash      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cache_signature ON odata_cache(signature, fetched_at);
CREATE INDEX IF NOT EXISTS ix_cache_fetched ON odata_cache(fetched_at);

CREATE TABLE IF NOT EXISTS query_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    data_mode      TEXT NOT NULL,
    kind           TEXT NOT NULL,
    query_text     TEXT NOT NULL,
    response_ms    REAL,
    record_count   INTEGER,
    http_status    INTEGER,
    result_status  TEXT NOT NULL,
    cache_status   TEXT NOT NULL,
    error_detail   TEXT
);
CREATE INDEX IF NOT EXISTS ix_history_created ON query_history(created_at);

CREATE TABLE IF NOT EXISTS saved_reports (
    report_id      TEXT PRIMARY KEY,
    generated_at   TEXT NOT NULL,
    data_mode      TEXT NOT NULL,
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    filters_json   TEXT NOT NULL,
    data_source    TEXT NOT NULL,
    data_fetched_at TEXT NOT NULL,
    from_cache     INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_generated ON saved_reports(generated_at);

CREATE TABLE IF NOT EXISTS application_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now_iso(now: datetime | None = None) -> str:
    return iso_utc(now or utc_now())


def signature_for(params: dict[str, Any]) -> str:
    """Stable signature for normalized query parameters."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Database:
    """Thread-safe SQLite wrapper with explicit, bounded operations."""

    def __init__(self, path: Path, data_mode: str) -> None:
        if data_mode not in ("demo", "live"):
            raise ValueError("data_mode must be 'demo' or 'live'")
        self.path = path
        self.data_mode = data_mode
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_DDL)
            self._conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
            stored_mode = self.get_setting("_data_mode")
            if stored_mode is None:
                self.set_setting("_data_mode", data_mode)
            elif stored_mode != data_mode:
                raise RuntimeError(
                    f"La base {path.name} pertenece al modo '{stored_mode}'; no se mezclan datos simulados y reales."
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ cache
    def put_cache(self, *, signature: str, query_params: dict[str, Any], relative_url: str,
                  records: list[dict[str, Any]], ttl_seconds: int, more_available: bool,
                  validation_state: str, schema_hash: str, now: datetime | None = None) -> int:
        now = now or utc_now()
        records_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._conn:
            cur = self._conn.execute(
                """INSERT INTO odata_cache (query_set_id, signature, data_mode, query_params, relative_url,
                       fetched_at, expires_at, record_count, records_json, more_available, validation_state,
                       response_hash, schema_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, signature, self.data_mode,
                 json.dumps(query_params, ensure_ascii=False, sort_keys=True), relative_url,
                 _now_iso(now), _now_iso(now + timedelta(seconds=ttl_seconds)), len(records), records_json,
                 int(more_available), validation_state,
                 hashlib.sha256(records_json.encode("utf-8")).hexdigest()[:32], schema_hash),
            )
            # Keep only the 3 most recent snapshots per signature.
            self._conn.execute(
                """DELETE FROM odata_cache WHERE signature = ? AND id NOT IN (
                       SELECT id FROM odata_cache WHERE signature = ? ORDER BY fetched_at DESC, id DESC LIMIT 3)""",
                (signature, signature),
            )
            return int(cur.lastrowid)

    def _cache_row(self, row: sqlite3.Row | None, now: datetime) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["query_params"] = json.loads(data["query_params"])
        data["records"] = json.loads(data.pop("records_json"))
        data["more_available"] = bool(data["more_available"])
        fetched = datetime.fromisoformat(data["fetched_at"])
        data["age_seconds"] = max(0.0, (now - fetched).total_seconds())
        data["is_fresh"] = datetime.fromisoformat(data["expires_at"]) > now
        return data

    def get_cache(self, signature: str, now: datetime | None = None) -> dict[str, Any] | None:
        """Most recent snapshot for a signature (fresh or stale; see ``is_fresh``)."""
        now = now or utc_now()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM odata_cache WHERE signature = ? ORDER BY fetched_at DESC, id DESC LIMIT 1",
                (signature,),
            ).fetchone()
        return self._cache_row(row, now)

    def get_cache_by_id(self, cache_id: int, now: datetime | None = None) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM odata_cache WHERE id = ?", (int(cache_id),)).fetchone()
        return self._cache_row(row, now or utc_now())

    def latest_cache(self, now: datetime | None = None) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM odata_cache ORDER BY fetched_at DESC, id DESC LIMIT 1").fetchone()
        return self._cache_row(row, now or utc_now())

    def list_cache(self, limit: int = 50, now: datetime | None = None) -> list[dict[str, Any]]:
        """Stored snapshots (without records) for the trends page."""
        now = now or utc_now()
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, signature, query_params, fetched_at, expires_at, record_count, more_available,
                          validation_state FROM odata_cache ORDER BY fetched_at DESC, id DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["query_params"] = json.loads(data["query_params"])
            data["more_available"] = bool(data["more_available"])
            data["is_fresh"] = datetime.fromisoformat(data["expires_at"]) > now
            data["age_seconds"] = max(0.0, (now - datetime.fromisoformat(data["fetched_at"])).total_seconds())
            result.append(data)
        return result

    def known_values(self, field: str, limit_rows: int = 30, max_values: int = 100) -> list[str]:
        """Distinct values of a field seen in recent cached records (for filter suggestions)."""
        values: set[str] = set()
        with self._lock:
            rows = self._conn.execute(
                "SELECT records_json FROM odata_cache ORDER BY fetched_at DESC LIMIT ?", (int(limit_rows),)
            ).fetchall()
        for row in rows:
            for record in json.loads(row["records_json"]):
                value = record.get(field)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    values.add(str(value))
                    if len(values) >= max_values:
                        return sorted(values)
        return sorted(values)

    # ------------------------------------------------------------------ history
    def add_history(self, *, kind: str, query_text: str, result_status: str, cache_status: str,
                    response_ms: float | None = None, record_count: int | None = None,
                    http_status: int | None = None, error_detail: str | None = None,
                    now: datetime | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO query_history (created_at, data_mode, kind, query_text, response_ms, record_count,
                       http_status, result_status, cache_status, error_detail) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (_now_iso(now), self.data_mode, kind, query_text[:2000], response_ms, record_count, http_status,
                 result_status, cache_status, (error_detail or "")[:1000] or None),
            )

    def list_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM query_history ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_odata_requests_since(self, since: datetime) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM query_history WHERE created_at >= ? AND cache_status = 'miss'",
                (_now_iso(since),),
            ).fetchone()
        return int(row[0])

    # ------------------------------------------------------------------ reports
    def save_report(self, *, period_start: str, period_end: str, filters: dict[str, Any], data_source: str,
                    data_fetched_at: str, from_cache: bool, snapshot: dict[str, Any],
                    now: datetime | None = None) -> str:
        report_id = uuid.uuid4().hex
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO saved_reports (report_id, generated_at, data_mode, period_start, period_end,
                       filters_json, data_source, data_fetched_at, from_cache, snapshot_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (report_id, _now_iso(now), self.data_mode, period_start, period_end,
                 json.dumps(filters, ensure_ascii=False), data_source, data_fetched_at, int(from_cache),
                 json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))),
            )
        return report_id

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM saved_reports WHERE report_id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["filters"] = json.loads(data.pop("filters_json"))
        data["snapshot"] = json.loads(data.pop("snapshot_json"))
        data["from_cache"] = bool(data["from_cache"])
        return data

    def list_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT report_id, generated_at, data_mode, period_start, period_end, filters_json, data_source,
                          data_fetched_at, from_cache FROM saved_reports ORDER BY generated_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["filters"] = json.loads(data.pop("filters_json"))
            data["from_cache"] = bool(data["from_cache"])
            result.append(data)
        return result

    def delete_report(self, report_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM saved_reports WHERE report_id = ?", (report_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value_json FROM application_settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO application_settings (key, value_json, updated_at) VALUES (?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), _now_iso()),
            )

    def delete_setting(self, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM application_settings WHERE key = ?", (key,))

    # ------------------------------------------------------------------ maintenance
    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                total += p.stat().st_size
        return total

    def cleanup(self, *, cache_retention_days: int, history_retention_days: int, report_retention_days: int,
                max_db_size_mb: int, now: datetime | None = None) -> dict[str, int]:
        """Apply the retention policy and keep the file under ``max_db_size_mb``."""
        now = now or utc_now()
        removed = {"cache": 0, "history": 0, "reports": 0, "size_trim": 0}
        with self._lock, self._conn:
            removed["cache"] = self._conn.execute(
                "DELETE FROM odata_cache WHERE fetched_at < ?",
                (_now_iso(now - timedelta(days=cache_retention_days)),)).rowcount
            removed["history"] = self._conn.execute(
                "DELETE FROM query_history WHERE created_at < ?",
                (_now_iso(now - timedelta(days=history_retention_days)),)).rowcount
            removed["reports"] = self._conn.execute(
                "DELETE FROM saved_reports WHERE generated_at < ?",
                (_now_iso(now - timedelta(days=report_retention_days)),)).rowcount
        limit = max_db_size_mb * 1024 * 1024
        guard = 0
        while self.size_bytes() > limit and guard < 20:
            guard += 1
            with self._lock, self._conn:
                count = self._conn.execute("SELECT COUNT(*) FROM odata_cache").fetchone()[0]
                if count == 0:
                    break
                trimmed = self._conn.execute(
                    """DELETE FROM odata_cache WHERE id IN (
                           SELECT id FROM odata_cache ORDER BY fetched_at ASC LIMIT ?)""",
                    (max(1, count // 4),)).rowcount
                removed["size_trim"] += trimmed
            self.vacuum()
        if any(removed.values()):
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return removed

    def vacuum(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.execute("VACUUM")

    def stats(self) -> dict[str, Any]:
        with self._lock:
            cache = self._conn.execute("SELECT COUNT(*), MAX(fetched_at) FROM odata_cache").fetchone()
            history = self._conn.execute("SELECT COUNT(*) FROM query_history").fetchone()[0]
            reports = self._conn.execute("SELECT COUNT(*) FROM saved_reports").fetchone()[0]
            fresh = self._conn.execute("SELECT COUNT(*) FROM odata_cache WHERE expires_at > ?",
                                       (_now_iso(),)).fetchone()[0]
        return {"cache_entries": cache[0], "cache_fresh_entries": fresh, "cache_latest": cache[1],
                "history_entries": history, "reports": reports, "size_bytes": self.size_bytes(),
                "file": self.path.name}
