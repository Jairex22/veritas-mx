"""Dependencias comunes de la API."""
from __future__ import annotations

from fastapi import Request

from ..container import Container
from ..core.errors import Unauthorized
from ..core.security import SessionUser, verify_csrf

SESSION_COOKIE = "gpv_session"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def container(request: Request) -> Container:
    return request.app.state.container


def current_user(request: Request) -> SessionUser:
    c: Container = request.app.state.container
    user = c.sessions.get(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise Unauthorized("Sesión no válida o expirada. Inicie sesión.")
    request.state.username = user.username
    if request.method in UNSAFE_METHODS:
        verify_csrf(user, request.headers.get("X-CSRF-Token"))
    return user
