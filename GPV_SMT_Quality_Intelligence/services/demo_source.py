"""Fuente de datos de DEMOSTRACIÓN.

Implementa la misma interfaz que FactoryLogixODataClient (execute / fetch_metadata)
sobre fixtures locales. Todas las respuestas llevan data_source="demo".

Contenido:
- Caso histórico Mirion W07632100028 (evidencia confirmada por GPV, no producción actual).
- Eventos sintéticos relativos a la hora actual con identificadores y clientes
  claramente marcados "DEMO" para alimentar Production Pulse y Quality Intelligence.
- Identificadores de inyección de fallos para demostrar estados de error:
  DEMO-ERR-401, DEMO-ERR-403, DEMO-ERR-500, DEMO-TIMEOUT, DEMO-INVALID-JSON,
  DEMO-QH-FAIL (SMT y Quality responden, QualityHistory agota el tiempo).
"""
from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.entities import DATE_FIELD, KNOWN_ENTITIES, QUALITY_HISTORY_PROPERTIES, QUALITY_PROPERTIES
from models.query import Filter, QuerySpec
from models.results import ODataStatus, QueryResult
from services.metadata import parse_metadata
from services.timeparse import parse_odata_datetime

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

QH_FAIL_DEFECT = "dead0000-0000-4000-8000-0000000000fa"

FAULTS = {
    "DEMO-ERR-401": (ODataStatus.AUTH_ERROR, 401, "HTTP 401 simulado"),
    "DEMO-ERR-403": (ODataStatus.FORBIDDEN, 403, "HTTP 403 simulado"),
    "DEMO-ERR-500": (ODataStatus.SERVER_ERROR, 500, "HTTP 500 simulado"),
    "DEMO-TIMEOUT": (ODataStatus.TIMEOUT, None, "Timeout simulado"),
    "DEMO-INVALID-JSON": (ODataStatus.INVALID_RESPONSE, 200, "JSON inválido simulado"),
}


def _load(name: str) -> list[dict]:
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        return json.load(fh)["value"]


def _match(row: dict, f: Filter) -> bool:
    val = row.get(f.field)
    if f.op == "in":
        return any(_match(row, Filter(f.field, "eq", v)) for v in f.value)
    if isinstance(f.value, datetime):
        dt = parse_odata_datetime(val)
        if dt is None:
            return False
        a, b = dt, f.value
    else:
        a, b = val, f.value
        if isinstance(a, str) and isinstance(b, str) and f.field in ("DefectID", "ODataKey"):
            a, b = a.lower(), b.lower()
    try:
        return {"eq": a == b, "ne": a != b, "ge": a >= b, "gt": a > b, "le": a <= b, "lt": a < b}[f.op]
    except TypeError:
        return False


class DemoDataSource:
    data_source = "demo"

    def __init__(self, seed: int = 4821, now: datetime | None = None):
        self._lock = threading.Lock()
        self._seed = seed
        self._fixed_now = now
        self._generated_for: datetime | None = None
        self._synthetic: dict[str, list[dict]] = {}
        self.fixtures = {
            "SMT": _load("mirion_W07632100028_smt.json"),
            "Quality": _load("mirion_W07632100028_quality.json"),
            "QualityHistory": _load("mirion_W07632100028_quality_history.json"),
        }
        self.last_metadata_status = None

    # ------------------------------------------------------------ synthetic data
    def _now(self) -> datetime:
        return self._fixed_now or datetime.now(timezone.utc)

    def _ensure_synthetic(self) -> None:
        now = self._now().replace(second=0, microsecond=0)
        with self._lock:
            if self._generated_for and abs((now - self._generated_for).total_seconds()) < 600:
                return
            self._synthetic = self._generate(now)
            self._generated_for = now

    def _generate(self, now: datetime) -> dict[str, list[dict]]:
        rnd = random.Random(self._seed)
        tz = timezone(timedelta(hours=-6))
        customers = [("DEMO Cliente A", "DEMO-ASM-100", "DEMO-B100"),
                     ("DEMO Cliente B", "DEMO-ASM-200", "DEMO-B200"),
                     ("DEMO Cliente C", "DEMO-ASM-300", "DEMO-B300")]
        flow = ["SMT Solder Paste Inspection", "SMT Pick and Place", "SMT Post-Reflow AOI Top", "QA SMT"]
        smt, quality, history = [], [], []
        for i in range(1, 61):
            cust, asm, batch = customers[i % 3]
            ident = f"DEMO-{i:05d}"
            t = now - timedelta(minutes=rnd.randint(1, 170))
            ops = list(flow)
            defect = i % 9 == 0
            if defect:
                ops = flow[:3] + ["SMT REPAIR", "SMT Post-Reflow AOI Top", "QA SMT"]
            for j, op in enumerate(ops):
                smt.append({"Customer": cust, "Assembly": asm, "AssemblyRevision": asm + "$$A",
                            "AssemblyDescription": "Ensamble de demostración", "Process": "DEMO Process",
                            "ProcessRevision": "1", "WorkOrder": "DEMO-WO-" + batch[-3:], "Batch": batch,
                            "OperationName": op, "Attempts": None, "Placements": None, "Identifier": ident,
                            "EventDate": (t + timedelta(minutes=2 * j)).astimezone(tz).isoformat(),
                            "ODataKey": "00000000-0000-0000-0000-000000000000"})
            if defect:
                did = f"d3a0{i:04d}-0000-4000-8000-{i:012d}"
                created = t + timedelta(minutes=4)
                status = "Open" if i % 18 == 0 else "Closed"
                q = {k: None for k in QUALITY_PROPERTIES}
                q.update({"CustomerName": cust, "Assembly": asm, "BatchName": batch, "Identifier": ident,
                          "DefectID": did, "DefectStatus": status, "SourceOperation": "SMT Post-Reflow AOI Top",
                          "AegisInspectionCodeName": rnd.choice(["Insufficient Solder", "Tombstone", "Bridging"]),
                          "AegisCategoryName": "DEMO Categoría", "DefectReference": f"R{rnd.randint(1, 99)}",
                          "DefectComment": "Defecto de demostración", "Line": "DEMO Line 1",
                          "DateCreated": created.astimezone(tz).isoformat(),
                          "ODataKey": "00000000-0000-0000-0000-000000000000"})
                quality.append(q)
                base = {k: None for k in QUALITY_HISTORY_PROPERTIES}
                base.update({"Identifier": ident, "DefectID": did, "Batch": batch, "Assembly": asm,
                             "DateCreated": q["DateCreated"], "SourceOperation": "SMT Post-Reflow AOI Top",
                             "ODataKey": "00000000-0000-0000-0000-000000000000"})
                history.append({**base, "DefectHistoryTime": q["DateCreated"], "DefectHistoryStatus": "Open",
                                "DefectHistoryOperation": "SMT Post-Reflow AOI Top"})
                if status == "Closed":
                    history.append({**base, "DefectHistoryTime": (created + timedelta(minutes=3)).astimezone(tz).isoformat(),
                                    "DefectHistoryStatus": "Closed", "DefectHistoryOperation": "SMT REPAIR",
                                    "DefectHistoryWorkstation": "DEMO-REPAIR-01", "DefectHistoryOperator": "DEMO-OP"})
        return {"SMT": smt, "Quality": quality, "QualityHistory": history}

    # ------------------------------------------------------------- interface
    def policy_check(self, entity: str):
        return None

    def fetch_metadata(self, force: bool = False):
        meta = parse_metadata((FIXTURES / "metadata_sample.xml").read_bytes())
        res = QueryResult(ODataStatus.OK, "$metadata", http_status=200, elapsed_ms=3.0, attempts=1,
                          query_description="$metadata (muestra local)", data_source="demo",
                          fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.last_metadata_status = res.to_status_dict()
        return res, meta

    def metadata(self):
        return self.fetch_metadata()[1]

    def execute(self, spec: QuerySpec) -> QueryResult:
        desc = spec.describe() + " | DEMO"
        if spec.entity not in KNOWN_ENTITIES:
            return QueryResult(ODataStatus.VALIDATION_ERROR, spec.entity, error="Entidad no autorizada",
                               query_description=desc, data_source="demo")
        ident = next((f.value for f in spec.filters if f.field == "Identifier" and f.op == "eq"), None)
        if ident in FAULTS:
            st, http, msg = FAULTS[ident]
            return QueryResult(st, spec.entity, http_status=http, error=msg, attempts=1, query_description=desc,
                               elapsed_ms=10000.0 if st == ODataStatus.TIMEOUT else 25.0, data_source="demo")
        defect_ids = set()
        for f in spec.filters:
            if f.field == "DefectID":
                defect_ids |= set(f.value) if f.op == "in" else {f.value}
        if spec.entity == "QualityHistory" and QH_FAIL_DEFECT in defect_ids:
            return QueryResult(ODataStatus.TIMEOUT, spec.entity, error="Timeout simulado en QualityHistory",
                               attempts=1, elapsed_ms=10000.0, query_description=desc, data_source="demo")
        self._ensure_synthetic()
        # El caso histórico (Mirion) solo se devuelve en búsquedas puntuales por unidad, defecto o batch;
        # nunca en ventanas temporales, para no mezclarlo con la "actividad actual" de demostración.
        targeted = any(f.field in ("Identifier", "DefectID", "Batch", "BatchName") for f in spec.filters)
        rows = list(self._synthetic.get(spec.entity, []))
        if targeted:
            rows = list(self.fixtures[spec.entity]) + rows
        if targeted and spec.entity in ("SMT", "Quality"):
            # Unidad DEMO-QH-FAIL: copia del caso Mirion con identificador y DefectID de demostración
            rows += [dict(r, Identifier="DEMO-QH-FAIL", **({"DefectID": QH_FAIL_DEFECT} if "DefectID" in r else {}))
                     for r in self.fixtures[spec.entity]]
        for f in spec.filters:
            rows = [r for r in rows if _match(r, f)]
        for fld, direction in reversed(spec.orderby):
            if fld == DATE_FIELD.get(spec.entity) or fld.endswith("Time") or fld.endswith("Date"):
                rows.sort(key=lambda r: (parse_odata_datetime(r.get(fld)) or datetime.min.replace(tzinfo=timezone.utc)),
                          reverse=direction == "desc")
            else:
                rows.sort(key=lambda r: str(r.get(fld) or ""), reverse=direction == "desc")
        truncated = len(rows) > spec.top
        rows = rows[:spec.top]
        return QueryResult(ODataStatus.OK if rows else ODataStatus.EMPTY, spec.entity, rows=rows, http_status=200,
                           elapsed_ms=float(random.Random(len(desc)).randint(40, 300)), attempts=1,
                           timings={"wait_headers_ms": 0.0, "download_ms": 0.0, "parse_ms": 0.0},
                           query_description=desc, data_source="demo", truncated=truncated,
                           fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
