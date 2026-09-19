"""
Capa de normalización FactoryLogix -> modelo interno.

Cada `normalize_*` recibe una lista de registros crudos de OData (dict, con
los nombres de campo que FactoryLogix entregue) y devuelve una lista de dict
en el "esquema interno" que usan `models.py` / `seed_data.py`. Los nombres de
campo de origen (columnas OData) son configurables porque cada instalación de
FactoryLogix puede exponerlos distinto: ajusta los `FIELD_MAP` de abajo según
la respuesta real que te comparta el administrador de FactoryLogix.

Este módulo NUNCA asume una estructura fija: si un campo no existe en el
registro crudo, se deja `None` y se contabiliza en `warnings` para que quede
visible en el estado de sincronización en vez de fallar silenciosamente.

Flujo esperado de uso (ver README > "Conectar FactoryLogix"):
    client = FactoryLogixClient()
    raw = client.fetch_entity(ODataQuery(entity=settings.flx_entity_production_activity))
    normalized = normalize_production_activity(raw)
    # -> guardar cada dict normalizado como ProductionEvent en la base local
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NormalizationResult:
    records: list[dict]
    warnings: list[str] = field(default_factory=list)


def _get_first(record: dict, *candidate_keys: str):
    for key in candidate_keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def normalize_production_activity(raw_records: list[dict]) -> NormalizationResult:
    """Mapea 'Production Activity' / 'Active Product Tracking (Detail)' a ProductionEvent."""
    records, warnings = [], []
    for r in raw_records:
        op_number = _get_first(r, "OperatorNumber", "EmployeeNumber", "UserID")
        station = _get_first(r, "StationName", "ProcessName", "OperationName")
        product = _get_first(r, "PartNumber", "ProductCode", "ItemNumber")
        wo = _get_first(r, "WorkOrderNumber", "JobNumber", "OrderNumber")
        qty_processed = _get_first(r, "QuantityProcessed", "UnitsProcessed", "Qty")
        qty_pass = _get_first(r, "QuantityPass", "UnitsPass", "PassCount")
        qty_fail = _get_first(r, "QuantityFail", "UnitsFail", "FailCount")
        cycle_time = _get_first(r, "CycleTimeSeconds", "ProcessTime", "Duration")
        event_date = _get_first(r, "EventDate", "TransactionDate", "Date")
        shift = _get_first(r, "ShiftName", "Shift")

        if op_number is None or station is None:
            warnings.append(f"Registro omitido por falta de operador o estación: {r}")
            continue

        records.append(
            {
                "operator_employee_number": str(op_number),
                "station_name": station,
                "product_code": product,
                "work_order_code": wo,
                "units_processed": int(qty_processed or 0),
                "units_conforming": int(qty_pass) if qty_pass is not None else None,
                "units_rejected": int(qty_fail) if qty_fail is not None else None,
                "cycle_time_seconds": float(cycle_time) if cycle_time is not None else None,
                "event_date": event_date,
                "shift": shift,
            }
        )
    return NormalizationResult(records=records, warnings=warnings)


def normalize_quality(raw_records: list[dict]) -> NormalizationResult:
    """Mapea 'Quality' / 'Faults' / 'Non-Conformance' / 'Validation Exceptions' a QualityEvent."""
    records, warnings = [], []
    for r in raw_records:
        op_number = _get_first(r, "OperatorNumber", "EmployeeNumber")
        station = _get_first(r, "StationName", "ProcessName")
        defect_code = _get_first(r, "DefectCode", "FaultCode", "NonConformanceCode")
        defect_desc = _get_first(r, "DefectDescription", "FaultDescription", "Description")
        quantity = _get_first(r, "Quantity", "DefectQty")
        event_date = _get_first(r, "EventDate", "Date")

        if defect_code is None:
            warnings.append(f"Registro de calidad omitido por falta de código de defecto: {r}")
            continue

        records.append(
            {
                "operator_employee_number": str(op_number) if op_number else None,
                "station_name": station,
                "defect_code": defect_code,
                "defect_description": defect_desc or "",
                # La causa NO se infiere automáticamente del origen FactoryLogix;
                # queda "Causa sin confirmar" hasta que ingeniería la clasifique,
                # para no atribuir responsabilidad de forma automática.
                "cause_category": "Causa sin confirmar",
                "quantity": int(quantity or 1),
                "event_date": event_date,
            }
        )
    return NormalizationResult(records=records, warnings=warnings)


def normalize_work_orders(raw_records: list[dict]) -> NormalizationResult:
    records, warnings = [], []
    for r in raw_records:
        code = _get_first(r, "WorkOrderNumber", "JobNumber")
        product = _get_first(r, "PartNumber", "ProductCode")
        planned_qty = _get_first(r, "PlannedQuantity", "OrderQuantity")
        if code is None:
            warnings.append(f"Orden de trabajo omitida por falta de número: {r}")
            continue
        records.append(
            {
                "code": code,
                "product_code": product,
                "planned_quantity": int(planned_qty or 0),
                "opened_at": _get_first(r, "OpenedDate", "StartDate"),
                "closed_at": _get_first(r, "ClosedDate", "EndDate"),
            }
        )
    return NormalizationResult(records=records, warnings=warnings)


def normalize_user_certification(raw_records: list[dict]) -> NormalizationResult:
    records, warnings = [], []
    for r in raw_records:
        op_number = _get_first(r, "OperatorNumber", "EmployeeNumber")
        station = _get_first(r, "StationName", "ProcessName")
        level = _get_first(r, "CertificationLevel", "SkillLevel")
        expires_at = _get_first(r, "ExpirationDate", "ExpiresAt")
        if op_number is None or station is None:
            warnings.append(f"Certificación omitida por datos incompletos: {r}")
            continue
        records.append(
            {
                "operator_employee_number": str(op_number),
                "station_name": station,
                "level": level or "No capacitado",
                "expires_at": expires_at,
            }
        )
    return NormalizationResult(records=records, warnings=warnings)


# Entidades adicionales del alcance (WIP, Active Product Tracking Detail,
# Test and Measurement, Stations, Products, Users) siguen el mismo patrón:
# reciben registros crudos, devuelven `NormalizationResult` con el esquema
# interno correspondiente. Se agregan bajo demanda cuando FactoryLogix esté
# disponible y autorizado, siguiendo esta misma convención.
