"""Errores controlados de la aplicación con código, mensaje y diagnóstico."""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"


class NotAvailable(AppError):
    """Funcionalidad sin método oficial verificado o sin conexión configurada."""
    status_code = 501
    code = "NOT_AVAILABLE"


class DataSourceUnavailable(AppError):
    status_code = 503
    code = "DATA_SOURCE_UNAVAILABLE"
