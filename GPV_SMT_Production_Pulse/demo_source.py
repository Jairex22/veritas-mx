"""DEMO mode: simulated OData transport.

``DemoTransport`` implements the same ``Transport`` interface as the real HTTP transport,
so demo mode exercises the *real* ``ODataClient`` (limits, breaker, URL building, parsing,
cache) without contacting FactoryLogix. All values produced here are SIMULATED and are
stored in a separate SQLite file (``production_pulse_demo.db``) so they can never mix
with real data.

The simulator understands only the subset of OData that this application emits:
``$select``, ``$filter`` (``and``-joined ``eq/ge/gt/le/lt`` clauses), ``$orderby`` and ``$top``.
Anything else returns HTTP 400, like a strict server would.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from odata_client import TransportConnectionError, TransportResponse, TransportTimeout
from timeutil import parse_odata_datetime, PlantClock

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
DEMO_METADATA_PATH = EXAMPLES_DIR / "metadata_sample.xml"

DEMO_MAPPING: dict[str, str] = {
    "timestamp": "IntervalStart",
    "quantity": "GoodCount",
    "line": "LineName",
    "station": "StationName",
    "shift": "ShiftName",
    "project": "ProjectName",
    "work_order": "WorkOrder",
    "product": "ProductName",
}

# line name -> (end-of-line station, nominal good boards per hour). Fictitious values.
_DEMO_LINES: list[tuple[str, str, int]] = [
    ("SMT-L01", "L01-AOI-FINAL", 180),
    ("SMT-L02", "L02-AOI-FINAL", 140),
    ("SMT-L03", "L03-AOI-FINAL", 210),
]
_FIELDS = ("RecordId", "IntervalStart", "IntervalEnd", "LineName", "StationName", "ShiftName",
           "ProjectName", "WorkOrder", "ProductName", "GoodCount", "RejectCount")
_PROJECTS = ("PRJ-SIM-ALFA", "PRJ-SIM-BETA", "PRJ-SIM-GAMMA")
INTERVAL_MINUTES = 15
_NON_FILTERABLE = {"RejectCount"}
_CLAUSE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) (eq|ge|gt|le|lt) (.+)$")


def _shift_for(local_hour: int) -> str:
    if 6 <= local_hour < 14:
        return "Turno A"
    if 14 <= local_hour < 22:
        return "Turno B"
    return "Turno C"


def generate_records(start: datetime, end: datetime, clock: PlantClock, now: datetime | None = None) -> list[dict[str, Any]]:
    """Deterministic simulated 15-minute records per line in [start, end).

    The interval containing ``now`` is returned as an *open* interval whose GoodCount grows
    as time passes (same RecordId), imitating an MES that updates the current interval.
    Nothing is generated in the future.
    """
    now = now or datetime.now(timezone.utc)
    step = timedelta(minutes=INTERVAL_MINUTES)
    start_utc = start.astimezone(timezone.utc)
    start_utc = start_utc.replace(minute=start_utc.minute - start_utc.minute % INTERVAL_MINUTES, second=0, microsecond=0)
    end_utc = min(end.astimezone(timezone.utc), now)
    records: list[dict[str, Any]] = []
    cursor = start_utc
    while cursor < end_utc:
        if cursor < start.astimezone(timezone.utc):
            cursor += step
            continue
        quarter = int(cursor.timestamp() // (INTERVAL_MINUTES * 60))
        hour_index = quarter // 4
        local = clock.to_local(cursor)
        fraction = min(1.0, (now - cursor) / step)
        for idx, (line, station, nominal) in enumerate(_DEMO_LINES):
            rng = random.Random(quarter * 31 + idx)
            factor = 0.85 + rng.random() * 0.25
            if local.hour in (2, 3, 4):
                factor *= 0.9  # night shift slightly lower
            if (hour_index + idx * 7) % 23 == 0:
                factor *= 0.35  # simulated stoppage
            if local.weekday() == 6:
                factor = 0.0 if local.hour < 22 else factor  # Sunday mostly idle
            good = int(nominal / 4 * factor * fraction)
            records.append({
                "RecordId": quarter * 10 + idx,
                "IntervalStart": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "IntervalEnd": (cursor + step).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "LineName": line,
                "StationName": station,
                "ShiftName": _shift_for(local.hour),
                "ProjectName": _PROJECTS[idx],
                "WorkOrder": f"WO-SIM-{1000 + (quarter // 32) * 3 + idx}",
                "ProductName": f"PN-SIM-{idx + 1:02d}{'AB'[(quarter // 32) % 2]}",
                "GoodCount": good,
                "RejectCount": int(good * rng.random() * 0.02),
            })
        cursor += step
    return records


def _parse_literal(text: str, clock: PlantClock) -> Any:
    text = text.strip()
    for prefix in ("datetimeoffset'", "datetime'"):
        if text.startswith(prefix) and text.endswith("'"):
            return parse_odata_datetime(text[len(prefix):-1], clock)
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})", text):
        return parse_odata_datetime(text, clock)
    raise ValueError(f"literal not understood: {text}")


def _compare(left: Any, op: str, right: Any) -> bool:
    if left is None:
        return False
    return {"eq": left == right, "ge": left >= right, "gt": left > right,
            "le": left <= right, "lt": left < right}[op]


def _error(status: int, message: str) -> TransportResponse:
    body = json.dumps({"error": {"code": str(status), "message": message}}).encode()
    return TransportResponse(status, {"Content-Type": "application/json"}, body)


class DemoTransport:
    """Simulated FactoryLogix OData endpoint. ``fail_with`` injects failures for tests."""

    def __init__(self, clock: PlantClock | None = None, fail_with: str | None = None,
                 now: datetime | None = None) -> None:
        self.clock = clock or PlantClock()
        self.fail_with = fail_with  # None | "timeout" | "connection" | "500" | "503" | "429" | "400" | "invalid_json"
        self.fixed_now = now
        self.requests: list[str] = []

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> TransportResponse:
        self.requests.append(url)
        if self.fail_with == "timeout":
            raise TransportTimeout("simulated timeout")
        if self.fail_with == "connection":
            raise TransportConnectionError("simulated connection refused")
        if self.fail_with in ("400", "500", "503", "429"):
            resp = _error(int(self.fail_with), "simulated failure")
            if self.fail_with == "429":
                resp.headers["Retry-After"] = "120"
            return resp
        if self.fail_with == "invalid_json":
            return TransportResponse(200, {"Content-Type": "application/json"}, b"{not json")

        parts = urlsplit(url)
        resource = parts.path.rstrip("/").rsplit("/", 1)[-1]
        if resource == "$metadata":
            return TransportResponse(200, {"Content-Type": "application/xml"}, DEMO_METADATA_PATH.read_bytes())
        if resource != "ProductivityOverTime":
            return _error(404, "resource not found")

        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        allowed = {"$select", "$filter", "$orderby", "$top", "$format"}
        if set(params) - allowed:
            return _error(400, "unsupported query option")
        now = self.fixed_now or datetime.now(timezone.utc)
        start = now - timedelta(days=2)
        end = now
        predicates: list[tuple[str, str, Any]] = []
        if params.get("$filter"):
            for clause in params["$filter"].split(" and "):
                match = _CLAUSE_RE.match(clause.strip())
                if not match:
                    return _error(400, "filter syntax not supported")
                name, op, literal = match.groups()
                if name not in _FIELDS:
                    return _error(400, f"property {name} not found")
                if name in _NON_FILTERABLE:
                    return _error(400, f"property {name} is not filterable")
                try:
                    value = _parse_literal(literal, self.clock)
                except ValueError as exc:
                    return _error(400, str(exc))
                if name == "IntervalStart" and isinstance(value, datetime):
                    if op in ("ge", "gt"):
                        start = max(value, now - timedelta(days=400))
                    elif op in ("lt", "le"):
                        end = min(value, now)
                predicates.append((name, op, value))
        if end - start > timedelta(days=60):
            return _error(400, "simulated server refuses ranges over 60 days")
        records = generate_records(start, end, self.clock, now)

        def field_value(record: dict[str, Any], name: str) -> Any:
            raw = record.get(name)
            if name in ("IntervalStart", "IntervalEnd"):
                return parse_odata_datetime(raw, self.clock)
            return raw

        records = [r for r in records if all(_compare(field_value(r, n), op, v) for n, op, v in predicates)]
        if params.get("$orderby"):
            pieces = params["$orderby"].split()
            if pieces[0] not in _FIELDS or len(pieces) > 2:
                return _error(400, "invalid orderby")
            reverse = len(pieces) == 2 and pieces[1] == "desc"
            records.sort(key=lambda r: (r.get(pieces[0]) is None, r.get(pieces[0])), reverse=reverse)
        more = False
        if params.get("$top"):
            if not params["$top"].isdigit():
                return _error(400, "invalid $top")
            top = int(params["$top"])
            more = len(records) > top
            records = records[:top]
        if params.get("$select"):
            fields = params["$select"].split(",")
            if any(f not in _FIELDS for f in fields):
                return _error(400, "invalid $select")
            records = [{f: r.get(f) for f in fields} for r in records]
        payload: dict[str, Any] = {"@odata.context": "$metadata#ProductivityOverTime", "value": records}
        if more:
            payload["@odata.nextLink"] = "ProductivityOverTime?$skiptoken=SIMULATED"
        body = json.dumps(payload).encode("utf-8")
        if len(body) > max_bytes:
            from odata_client import ResponseTooLargeError

            raise ResponseTooLargeError("simulated payload too large")
        return TransportResponse(200, {"Content-Type": "application/json", "OData-Version": "4.0"}, body)
