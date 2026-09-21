"""
Local read-only FastAPI service for GPV XML Cleaner & Diagnostics.

Runs on 127.0.0.1:<api_port> (default 8765) in a background thread owned
by the Tkinter GUI. Every endpoint is GET-only and read-only: the API can
never trigger a file move or delete, it only ever reports the results of
the most recent scan performed from the GUI.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query

from app.cleanup import analyze_cleanup
from app.config import APP_NAME, get_logger
from app.models import ScanResult, XMLFileInfo

logger = get_logger()


class SharedState:
    """Thread-safe holder for the latest scan result, read by the API and
    written by the GUI after every scan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.folder: str = ""
        self.scan_result: Optional[ScanResult] = None
        self.settings: Dict[str, Any] = {}
        self.scanning: bool = False

    def update(self, folder: str, scan_result: Optional[ScanResult], settings: Dict[str, Any]) -> None:
        with self._lock:
            self.folder = folder
            self.scan_result = scan_result
            self.settings = dict(settings)

    def set_scanning(self, value: bool) -> None:
        with self._lock:
            self.scanning = value

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "folder": self.folder,
                "scan_result": self.scan_result,
                "settings": dict(self.settings),
                "scanning": self.scanning,
            }


state = SharedState()


def _file_to_dict(f: XMLFileInfo) -> Dict[str, Any]:
    return {
        "name": f.name,
        "path": f.path,
        "folder": f.folder,
        "size_bytes": f.size_bytes,
        "created": f.created.isoformat(),
        "modified": f.modified.isoformat(),
        "age_days": round(f.age_days, 2),
        "status": f.status,
        "recommendation": f.recommendation,
    }


def _require_scan() -> ScanResult:
    snap = state.snapshot()
    result: Optional[ScanResult] = snap["scan_result"]
    if result is None:
        raise HTTPException(status_code=404, detail="No scan has been performed yet.")
    return result


def create_api_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, description="Read-only local diagnostics API.")

    @app.get("/")
    def root() -> Dict[str, str]:
        return {"application": APP_NAME, "status": "running"}

    @app.get("/status")
    def status() -> Dict[str, Any]:
        snap = state.snapshot()
        result: Optional[ScanResult] = snap["scan_result"]
        return {
            "application": APP_NAME,
            "status": "running",
            "scanning": snap["scanning"],
            "folder": snap["folder"],
            "has_scan_result": result is not None,
            "last_scanned_at": result.scanned_at.isoformat() if result else None,
        }

    @app.get("/folder")
    def folder() -> Dict[str, Any]:
        snap = state.snapshot()
        result: Optional[ScanResult] = snap["scan_result"]
        return {
            "folder": snap["folder"],
            "total_xml": result.total_count if result else 0,
            "total_size_bytes": result.total_size_bytes if result else 0,
        }

    @app.get("/stats")
    def stats() -> Dict[str, Any]:
        result = _require_scan()
        older_30 = result.age_groups.get("30", 0)
        older_90 = result.age_groups.get("90", 0)
        oldest_days = int(result.oldest.age_days) if result.oldest else 0
        return {
            "total_xml": result.total_count,
            "total_size_bytes": result.total_size_bytes,
            "oldest_days": oldest_days,
            "older_than_30_days": older_30,
            "older_than_90_days": older_90,
            "age_groups": result.age_groups,
        }

    @app.get("/oldest")
    def oldest() -> Dict[str, Any]:
        result = _require_scan()
        if result.oldest is None:
            raise HTTPException(status_code=404, detail="No XML files found.")
        return _file_to_dict(result.oldest)

    @app.get("/newest")
    def newest() -> Dict[str, Any]:
        result = _require_scan()
        if result.newest is None:
            raise HTTPException(status_code=404, detail="No XML files found.")
        return _file_to_dict(result.newest)

    @app.get("/files")
    def files(
        limit: int = Query(default=500, ge=1, le=20000),
        offset: int = Query(default=0, ge=0),
    ) -> Dict[str, Any]:
        result = _require_scan()
        page = result.files[offset: offset + limit]
        return {
            "total": len(result.files),
            "limit": limit,
            "offset": offset,
            "files": [_file_to_dict(f) for f in page],
        }

    @app.get("/cleanup-analysis")
    def cleanup_analysis() -> Dict[str, Any]:
        snap = state.snapshot()
        result = _require_scan()
        retention_days = int(snap["settings"].get("retention_days", 30))
        return analyze_cleanup(result.files, retention_days)

    return app


api_app = create_api_app()


def run_api_server(host: str, port: int) -> None:
    """Blocking call - intended to run inside a daemon thread."""
    try:
        config = uvicorn.Config(api_app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        server.run()
    except Exception as exc:  # noqa: BLE001 - API must never crash the GUI process
        logger.error("Local API server failed to start: %s", exc)


def start_api_server_thread(host: str, port: int) -> threading.Thread:
    thread = threading.Thread(target=run_api_server, args=(host, port), daemon=True, name="gpv-api-server")
    thread.start()
    logger.info("Local API server starting on http://%s:%d", host, port)
    return thread
