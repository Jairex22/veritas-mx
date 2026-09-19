from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse
from ..security import (
    create_access_token,
    get_current_user,
    is_locked,
    register_failed_attempt,
    register_successful_login,
    verify_password,
    CurrentUser,
)

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip().lower()).first()
    client_ip = request.client.host if request.client else ""

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    if is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Esta cuenta está bloqueada temporalmente por intentos fallidos. Intenta más tarde.",
        )

    if not verify_password(payload.password, user.hashed_password):
        register_failed_attempt(user, db)
        log_action(
            db, username=payload.username, role="-", action="Intento de inicio de sesión fallido",
            ip_address=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    register_successful_login(user, db)
    log_action(db, username=user.username, role=user.role.value, action="Inicio de sesión", ip_address=client_ip)

    token = create_access_token(user)
    return TokenResponse(
        access_token=token, display_name=user.display_name, role=user.role.value, username=user.username
    )


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role,
    }
