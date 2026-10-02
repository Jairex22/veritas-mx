"""Utilidades compartidas por los repositorios."""
from __future__ import annotations

from typing import Any, Iterable

from core.errors import ValidationError
from database.connection import Database


class BaseRepository:
    table: str = ""
    updatable: frozenset[str] = frozenset()

    def __init__(self, db: Database):
        self.db = db

    def _update(self, record_id: str, fields: dict[str, Any], conn=None) -> None:
        """UPDATE dinámico con nombres de columna en allowlist y valores parametrizados."""
        if not fields:
            return
        unknown = set(fields) - set(self.updatable)
        if unknown:
            raise ValidationError(f"Campos no permitidos: {', '.join(sorted(unknown))}")
        assignments = ", ".join(f"{col} = ?" for col in fields)
        sql = f"UPDATE {self.table} SET {assignments} WHERE id = ?"  # noqa: S608 - columnas en allowlist
        params = [*fields.values(), record_id]
        if conn is not None:
            conn.execute(sql, params)
        else:
            self.db.execute(sql, params)

    @staticmethod
    def placeholders(values: Iterable[Any]) -> str:
        count = len(list(values))
        return ",".join("?" for _ in range(count)) if count else "NULL"
