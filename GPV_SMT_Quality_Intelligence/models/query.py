"""Especificación estructurada de consultas.

El frontend nunca envía texto OData: envía parámetros que el backend valida y
convierte en un QuerySpec. Tanto el cliente OData real como la fuente de
demostración consumen el mismo QuerySpec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_OPERATORS = frozenset({"eq", "ne", "ge", "gt", "le", "lt", "in"})


@dataclass(frozen=True)
class Filter:
    field: str
    op: str
    value: Any

    def describe(self) -> str:
        if self.op == "in":
            return f"{self.field} in [{len(self.value)} valores]"
        return f"{self.field} {self.op} {self.value!s}"


@dataclass
class QuerySpec:
    entity: str
    filters: list[Filter] = field(default_factory=list)
    select: list[str] | None = None
    orderby: list[tuple[str, str]] = field(default_factory=list)
    top: int = 50

    def describe(self) -> str:
        parts = [self.entity]
        if self.filters:
            parts.append("filtro: " + " and ".join(f.describe() for f in self.filters))
        if self.orderby:
            parts.append("orden: " + ", ".join(f"{f} {d}" for f, d in self.orderby))
        parts.append(f"top: {self.top}")
        return " | ".join(parts)
