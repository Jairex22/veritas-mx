"""Excepciones de dominio. Los mensajes son seguros para mostrarse al usuario."""
from __future__ import annotations


class CopilotError(Exception):
    """Error base con mensaje apto para usuario (sin rutas internas ni secretos)."""

    user_message = "Ocurrió un error. Consulta a Soporte MES."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class ValidationError(CopilotError):
    user_message = "Datos inválidos."


class PermissionDenied(CopilotError):
    user_message = "No tienes permiso para realizar esta acción."


class AuthenticationError(CopilotError):
    user_message = "Usuario o contraseña inválidos."


class AccountLocked(AuthenticationError):
    user_message = "Usuario o contraseña inválidos, o la cuenta está bloqueada temporalmente."


class RateLimitExceeded(CopilotError):
    user_message = "Demasiadas solicitudes. Espera un momento e inténtalo de nuevo."


class FileRejected(CopilotError):
    user_message = "Archivo rechazado por las políticas de seguridad."


class ExtractionError(CopilotError):
    user_message = "No fue posible extraer el texto del archivo."


class WorkflowError(CopilotError):
    user_message = "Transición de estado no permitida."


class NotFound(CopilotError):
    user_message = "Elemento no encontrado."


class ConnectorError(CopilotError):
    user_message = "El conector no está disponible."
