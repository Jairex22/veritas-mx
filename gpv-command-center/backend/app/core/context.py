"""Contexto por petición: identificador de correlación."""
from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_VALID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def new_correlation_id(incoming: str | None = None) -> str:
    cid = incoming if incoming and _VALID.match(incoming) else uuid.uuid4().hex
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _correlation_id.get()
