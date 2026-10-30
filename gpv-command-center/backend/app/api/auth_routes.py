from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..container import Container
from ..core.security import SessionUser
from .deps import SESSION_COOKIE, container, current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    provider: str = Field("demo", pattern=r"^(demo|corporate)$")
    username: str = Field("", max_length=64, pattern=r"^[A-Za-z0-9._\-]*$")


@router.get("/providers")
def providers(c: Container = Depends(container)) -> dict:
    return {"mode": c.settings.mode.value, "providers": c.auth.describe()}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, c: Container = Depends(container)) -> dict:
    try:
        if body.provider == "corporate":
            username, display, role = c.auth.authenticate_corporate(
                request.client.host if request.client else None,
                request.headers.get(c.settings.proxy_auth_header) if c.settings.proxy_auth_header else None)
        else:
            username = body.username
            display, role = c.auth.authenticate_demo(username)
    except Exception as exc:
        c.audit.record(category="AUTH", action="login", outcome="DENIED", username=body.username or None,
                       details={"provider": body.provider, "reason": str(exc),
                                "client_ip": request.client.host if request.client else None})
        raise
    c.sessions.purge_expired()
    token, user = c.sessions.create(username, display, role, body.provider)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=c.settings.cookie_secure, samesite="strict",
                        max_age=c.settings.session_ttl_minutes * 60, path="/")
    c.audit.record(category="AUTH", action="login", outcome="SUCCESS", username=user.username, role=role.value,
                   details={"provider": body.provider, "client_ip": request.client.host if request.client else None})
    return {"user": user.public(), "csrf_token": user.csrf_token}


@router.get("/me")
def me(user: SessionUser = Depends(current_user)) -> dict:
    return {"user": user.public(), "csrf_token": user.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, user: SessionUser = Depends(current_user),
           c: Container = Depends(container)) -> dict:
    c.sessions.revoke(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE, path="/")
    c.audit.record(category="AUTH", action="logout", outcome="SUCCESS", username=user.username, role=user.role.value)
    return {"ok": True}
