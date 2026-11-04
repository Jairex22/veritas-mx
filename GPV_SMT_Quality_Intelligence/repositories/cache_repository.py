"""Caché local de registros OData con deduplicación segura."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from database.db import Database
from models.entities import EMPTY_GUID
from services.odata_filters import GUID_RE
from services.timeparse import parse_odata_datetime


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc(value) -> str | None:
    dt = parse_odata_datetime(value)
    if dt is None or dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def dedup_key(entity: str, row: dict) -> str:
    """Clave estable. ODataKey solo se usa si es un GUID válido y no vacío."""
    key = row.get("ODataKey")
    if isinstance(key, str) and GUID_RE.match(key) and key.lower() != EMPTY_GUID:
        return "key:" + key.lower()
    canonical = json.dumps({"entity": entity, "row": row}, sort_keys=True, ensure_ascii=False, default=str)
    return "hash:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CacheRepository:
    def __init__(self, db: Database):
        self.db = db

    def store(self, entity: str, rows: list[dict], data_source: str) -> int:
        if data_source not in ("live", "demo") or not rows:
            return 0
        now = _now()
        with self.db.connection(write=True) as conn:
            for r in rows:
                raw = json.dumps(r, ensure_ascii=False, default=str)
                k = dedup_key(entity, r)
                if entity == "SMT":
                    conn.execute(
                        """INSERT INTO CachedSMTEvents (dedup_key, data_source, identifier, batch, assembly, customer,
                           operation, event_date, event_utc, odata_key, raw_json, first_seen_at, last_seen_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                        (k, data_source, r.get("Identifier"), r.get("Batch"), r.get("Assembly"), r.get("Customer"),
                         r.get("OperationName"), r.get("EventDate"), _utc(r.get("EventDate")), r.get("ODataKey"),
                         raw, now, now))
                elif entity == "Quality":
                    conn.execute(
                        """INSERT INTO CachedQualityDefects (dedup_key, data_source, defect_id, identifier, batch,
                           assembly, defect_status, line, date_created, created_utc, odata_key, raw_json,
                           first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                        (k, data_source, r.get("DefectID"), r.get("Identifier"), r.get("BatchName"), r.get("Assembly"),
                         r.get("DefectStatus"), r.get("Line"), r.get("DateCreated"), _utc(r.get("DateCreated")),
                         r.get("ODataKey"), raw, now, now))
                elif entity == "QualityHistory":
                    conn.execute(
                        """INSERT INTO CachedQualityHistory (dedup_key, data_source, defect_id, identifier,
                           history_time, history_utc, history_status, operation, odata_key, raw_json,
                           first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                        (k, data_source, r.get("DefectID"), r.get("Identifier"), r.get("DefectHistoryTime"),
                         _utc(r.get("DefectHistoryTime")), r.get("DefectHistoryStatus"),
                         r.get("DefectHistoryOperation"), r.get("ODataKey"), raw, now, now))
                else:
                    raise ValueError(f"Entidad no cacheable: {entity}")
        return len(rows)

    def _fetch(self, sql: str, params: tuple) -> tuple[list[dict], str | None]:
        with self.db.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        if not rows:
            return [], None
        return [json.loads(r["raw_json"]) for r in rows], max(r["last_seen_at"] for r in rows)

    def smt_by_identifier(self, identifier: str, data_source: str):
        return self._fetch("SELECT raw_json, last_seen_at FROM CachedSMTEvents WHERE data_source=? AND identifier=? "
                           "ORDER BY event_utc", (data_source, identifier))

    def smt_in_window(self, start_utc: datetime, end_utc: datetime, data_source: str, limit: int):
        return self._fetch("SELECT raw_json, last_seen_at FROM CachedSMTEvents WHERE data_source=? AND event_utc>=? "
                           "AND event_utc<=? ORDER BY event_utc DESC LIMIT ?",
                           (data_source, start_utc.isoformat(timespec="milliseconds"),
                            end_utc.isoformat(timespec="milliseconds"), limit))

    def quality_by_identifier(self, identifier: str, data_source: str):
        return self._fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=? "
                           "AND identifier=?", (data_source, identifier))

    def quality_in_window(self, start_utc: datetime, end_utc: datetime, data_source: str, limit: int):
        return self._fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=? "
                           "AND created_utc>=? AND created_utc<=? ORDER BY created_utc DESC LIMIT ?",
                           (data_source, start_utc.isoformat(timespec="milliseconds"),
                            end_utc.isoformat(timespec="milliseconds"), limit))

    def quality_by_defect(self, defect_id: str, data_source: str):
        return self._fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=? "
                           "AND lower(defect_id)=? ORDER BY id DESC", (data_source, defect_id.lower()))

    def history_by_defects(self, defect_ids: list[str], data_source: str):
        if not defect_ids:
            return [], None
        marks = ",".join("?" for _ in defect_ids)
        return self._fetch(f"SELECT raw_json, last_seen_at FROM CachedQualityHistory WHERE data_source=? "
                           f"AND lower(defect_id) IN ({marks}) ORDER BY history_utc",
                           (data_source, *[d.lower() for d in defect_ids]))

    def counts(self) -> dict:
        with self.db.connection() as conn:
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("CachedSMTEvents", "CachedQualityDefects", "CachedQualityHistory")}
