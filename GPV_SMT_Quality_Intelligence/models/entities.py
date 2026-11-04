"""Catálogo de entidades y propiedades conocidas de FactoryLogix OData.

Las propiedades listadas provienen del $metadata verificado por GPV. Los tipos
marcados como verified=False son supuestos de arranque: en modo real se
sustituyen por los tipos leídos de $metadata.
"""
from __future__ import annotations

from dataclasses import dataclass

EMPTY_GUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class PropertyInfo:
    name: str
    edm_type: str
    verified: bool = True


def _props(items: list[tuple[str, str, bool]]) -> dict[str, PropertyInfo]:
    return {n: PropertyInfo(n, t, v) for n, t, v in items}


SMT_PROPERTIES = _props([
    ("Customer", "Edm.String", True),
    ("Assembly", "Edm.String", True),
    ("AssemblyRevision", "Edm.String", True),
    ("AssemblyDescription", "Edm.String", True),
    ("Process", "Edm.String", True),
    ("ProcessRevision", "Edm.String", True),
    ("WorkOrder", "Edm.String", True),
    ("Batch", "Edm.String", True),
    ("OperationName", "Edm.String", True),
    ("Attempts", "Edm.Int32", True),
    ("Placements", "Edm.Int32", True),
    ("Identifier", "Edm.String", True),
    ("EventDate", "Edm.DateTimeOffset", True),
    ("ODataKey", "Edm.Guid", True),
])

_Q_STRINGS = [
    "CustomerName", "Assembly", "AssemblyRevision", "AssemblyDescription", "ProcessName",
    "ProcessRevision", "WorkOrder", "BatchName", "BatchStatus", "UnitOfIssue", "Identifier",
    "Lot", "SourceOperation", "CurrentOperation", "CurrentOperationAlias", "Operator",
    "DefectStatus", "AegisInspectionCode", "AegisInspectionCodeName", "AegisCategoryName",
    "InspectionCode", "DefectPartNumber", "DefectPartDescription", "DefectReference",
    "DefectFootprint", "DefectConnection", "InspectionArea", "InspectionWorkstation",
    "SourceWorkstation", "DefectComment", "SymptomCode", "SymptomCategory",
    "SymptomDescription", "SymptomStatus", "OperationGroup", "Line", "RootCauseDefect",
    "Location", "ExternalDefectID", "Source",
]
# Los nombres de Quality están verificados; los tipos no fueron entregados por
# GPV y se marcan verified=False hasta leer $metadata en la red autorizada.
QUALITY_PROPERTIES = _props(
    [(n, "Edm.String", False) for n in _Q_STRINGS]
    + [
        ("DefectID", "Edm.Guid", False),
        ("BatchQuantity", "Edm.Int32", False),
        ("CompletedQuantity", "Edm.Int32", False),
        ("DateCreated", "Edm.DateTimeOffset", False),
        ("InspectionPostedTime", "Edm.DateTimeOffset", False),
        ("Blocked", "Edm.Boolean", False),
        ("ODataKey", "Edm.Guid", False),
    ]
)

QUALITY_HISTORY_PROPERTIES = _props([
    ("Identifier", "Edm.String", False),
    ("DefectID", "Edm.Guid", False),
    ("DefectStatus", "Edm.String", False),
    ("DefectHistoryTime", "Edm.DateTimeOffset", False),
    ("DefectHistoryOperation", "Edm.String", False),
    ("DefectHistoryWorkstation", "Edm.String", False),
    ("DefectHistoryComment", "Edm.String", False),
    ("DefectHistoryOperator", "Edm.String", False),
    ("DefectHistoryStatus", "Edm.String", False),
    ("Line", "Edm.String", False),
    ("CurrentOperation", "Edm.String", False),
    ("SourceOperation", "Edm.String", False),
    ("Batch", "Edm.String", False),
    ("Assembly", "Edm.String", False),
    ("DateCreated", "Edm.DateTimeOffset", False),
    ("DefectPartNumber", "Edm.String", False),
    ("DefectReference", "Edm.String", False),
    ("ODataKey", "Edm.Guid", False),
])

KNOWN_ENTITIES: dict[str, dict[str, PropertyInfo]] = {
    "SMT": SMT_PROPERTIES,
    "Quality": QUALITY_PROPERTIES,
    "QualityHistory": QUALITY_HISTORY_PROPERTIES,
}

# Lista blanca de campos filtrables por entidad. El usuario nunca construye
# consultas arbitrarias: solo puede combinar estos campos con operadores fijos.
FILTERABLE_FIELDS: dict[str, frozenset[str]] = {
    "SMT": frozenset({"Identifier", "Batch", "Assembly", "Customer", "OperationName",
                      "WorkOrder", "EventDate"}),
    "Quality": frozenset({"Identifier", "BatchName", "Assembly", "CustomerName",
                          "DefectStatus", "Line", "DateCreated", "DefectID",
                          "SourceOperation"}),
    "QualityHistory": frozenset({"Identifier", "DefectID", "DefectHistoryTime"}),
}

# Campo de fecha principal para ventanas temporales.
DATE_FIELD = {"SMT": "EventDate", "Quality": "DateCreated", "QualityHistory": "DefectHistoryTime"}
