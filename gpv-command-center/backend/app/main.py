"""Punto de entrada FastAPI de GPV FactoryLogix Command Center."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import auth_routes, data_routes, explorer_routes, odata_routes, ops_routes, system_routes
from .api.deps import SESSION_COOKIE
from .container import Container
from .core.context import get_correlation_id, new_correlation_id
from .core.errors import AppError
from .core.logging_config import configure_logging
from .data.demo import DemoDataSource
from .settings import APP_VERSION, Settings

log = logging.getLogger("gpv.app")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or {}, "correlation_id": get_correlation_id()}})


def create_app(settings: Settings | None = None, *, db_path: str | Path | None = None,
               http_transport: httpx.BaseTransport | None = None, demo_source: DemoDataSource | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.data_dir / "logs")
    container = Container(settings, db_path=db_path, http_transport=http_transport, demo_source=demo_source)

    app = FastAPI(title="GPV FactoryLogix Command Center", version=APP_VERSION,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.state.container = container

    @app.middleware("http")
    async def correlation_and_access(request: Request, call_next):
        cid = new_correlation_id(request.headers.get("X-Correlation-ID"))
        start = time.perf_counter()
        request.state.username = None
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - cubierto por el manejador global
            log.exception("Error no controlado")
            response = _error(500, "INTERNAL_ERROR", "Error interno. Consulte el identificador de correlación.")
        duration = (time.perf_counter() - start) * 1000
        response.headers["X-Correlation-ID"] = cid
        for k, v in SECURITY_HEADERS.items():
            if k == "Cache-Control" and not request.url.path.startswith("/api"):
                continue
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            user = getattr(request.state, "username", None)
            if user is None:
                sess = container.sessions.get(request.cookies.get(SESSION_COOKIE)) if request.cookies.get(SESSION_COOKIE) else None
                user = sess.username if sess else None
            try:
                container.audit.log_access(username=user, method=request.method, path=request.url.path,
                                           status=response.status_code, duration_ms=duration,
                                           client_ip=request.client.host if request.client else None)
            except Exception:  # pragma: no cover
                log.exception("No se pudo registrar acceso")
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        level = logging.WARNING if exc.status_code < 500 or exc.status_code in (501, 503) else logging.ERROR
        log.log(level, exc.message, extra={"data": {"code": exc.code, "path": request.url.path}})
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = {".".join(str(p) for p in e["loc"][1:]) or "body": e["msg"] for e in exc.errors()}
        return _error(422, "VALIDATION_FAILED", "Solicitud inválida.", {"fields": fields})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Error no controlado", extra={"data": {"path": request.url.path}})
        return _error(500, "INTERNAL_ERROR", "Error interno. Consulte el identificador de correlación.")

    for r in (auth_routes.router, data_routes.router, ops_routes.router, odata_routes.router, explorer_routes.router,
              system_routes.router):
        app.include_router(r)

    @app.get("/api/health", tags=["sistema"])
    def health() -> dict:
        return {"status": "ok", "version": APP_VERSION, "mode": settings.mode.value}

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(rest: str):
        return _error(404, "NOT_FOUND", f"Ruta API inexistente: /api/{rest}")

    frontend = settings.frontend_dir
    if frontend.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(frontend / "index.html")

    container.audit.record(category="SYSTEM", action="startup", outcome="SUCCESS",
                           details={"version": APP_VERSION, "mode": settings.mode.value,
                                    "data_source": container.source.provenance()})
    return app
