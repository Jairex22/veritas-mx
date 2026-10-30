"""Interfaz de fuentes de datos de producción (sólo lectura)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.errors import DataSourceUnavailable, NotAvailable, NotFound
from .models import Unit, WorkOrder

SEARCH_FIELDS = ("any", "serial", "work_order", "assembly", "batch", "revision", "station", "area", "line", "panel")


class ProductionDataSource(ABC):
    kind: str = "ABSTRACT"
    label: str = ""
    synthetic: bool = False

    def provenance(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label, "synthetic": self.synthetic}

    @abstractmethod
    def list_units(self) -> list[Unit]: ...

    @abstractmethod
    def work_orders(self) -> list[WorkOrder]: ...

    def get_unit(self, serial: str) -> Unit:
        for u in self.list_units():
            if u.serial.lower() == serial.lower():
                return u
        raise NotFound(f"Serial '{serial}' no encontrado en la fuente {self.label}.")

    def get_panel(self, panel_id: str) -> list[Unit]:
        units = [u for u in self.list_units() if u.panel_id and u.panel_id.lower() == panel_id.lower()]
        if not units:
            raise NotFound(f"Panel '{panel_id}' no encontrado en la fuente {self.label}.")
        return sorted(units, key=lambda u: u.panel_position or 0)

    def search(self, q: str, field: str = "any", limit: int = 100) -> list[Unit]:
        return filter_units(self.list_units(), q, field)[:limit]

    def find_box(self, box_id: str) -> dict[str, Any]:
        raise NotAvailable(
            "La consulta de cajas no está disponible en esta fuente de datos. "
            "Requiere identificar el método oficial de packing en FactoryLogix.",
            code="BOX_LOOKUP_NOT_AVAILABLE",
        )


def filter_units(units: list[Unit], q: str, field: str = "any") -> list[Unit]:
    q = (q or "").strip().lower()
    if not q:
        return []
    if field not in SEARCH_FIELDS:
        field = "any"

    def values(u: Unit) -> dict[str, list[str]]:
        stations = {e.station for e in u.events}
        if u.current_station:
            stations.add(u.current_station)
        return {
            "serial": [u.serial], "work_order": [u.work_order], "assembly": [u.assembly],
            "batch": [u.batch], "revision": [u.revision], "station": sorted(stations),
            "area": [u.area] + sorted({e.area for e in u.events if e.area}), "line": [u.line],
            "panel": [u.panel_id or ""],
        }

    out = []
    for u in units:
        vals = values(u)
        pool = [v for vs in vals.values() for v in vs] if field == "any" else vals[field]
        exact_fields = {"station", "revision"}
        if field in exact_fields:
            hit = any(v.lower() == q for v in pool)
        else:
            hit = any(q in v.lower() for v in pool)
        if hit:
            out.append(u)
    # Coincidencias exactas de serial primero.
    out.sort(key=lambda u: (u.serial.lower() != q, u.serial))
    return out


class UnavailableDataSource(ProductionDataSource):
    """Fuente usada en modo REAL cuando no hay conexión configurada.

    No devuelve datos: cualquier consulta produce un error explícito, para que
    jamás se presente información sintética como si viniera de FactoryLogix.
    """

    kind = "NONE"
    synthetic = False

    def __init__(self, reason: str):
        self.reason = reason
        self.label = "Sin fuente de datos"

    def list_units(self) -> list[Unit]:
        raise DataSourceUnavailable(self.reason, code="NO_DATA_SOURCE")

    def work_orders(self) -> list[WorkOrder]:
        raise DataSourceUnavailable(self.reason, code="NO_DATA_SOURCE")
