"""Salud del sistema: base de datos, índice, embeddings, LLM, OCR, conectores, auditoría y disco."""
from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from core.config import Settings
from database.connection import Database
from ingestion.extractors import ocr_available
from rag.embeddings import Embedder
from rag.llm import LLMProvider
from repositories.audit import AuditRepository
from repositories.chunks import ChunkRepository
from services.connector_service import ConnectorService

_PACKAGES = ["streamlit", "numpy", "pandas", "pypdf", "python-docx", "openpyxl", "PyYAML", "requests"]


@dataclass
class HealthCheck:
    component: str
    status: str  # OK | WARN | FAIL | OFF
    detail: str


class HealthService:
    def __init__(self, settings: Settings, db: Database, chunks: ChunkRepository, audit: AuditRepository,
                 embedder: Embedder, llm: LLMProvider, connectors: ConnectorService, startup_warnings: list[str]):
        self.settings = settings
        self.db = db
        self.chunks = chunks
        self.audit = audit
        self.embedder = embedder
        self.llm = llm
        self.connectors = connectors
        self.startup_warnings = startup_warnings

    def checks(self) -> list[HealthCheck]:
        results: list[HealthCheck] = []
        try:
            ok = self.db.integrity_ok()
            results.append(HealthCheck("Base de datos SQLite", "OK" if ok else "FAIL",
                                       "integridad verificada" if ok else "quick_check falló"))
        except Exception as exc:  # noqa: BLE001
            results.append(HealthCheck("Base de datos SQLite", "FAIL", type(exc).__name__))
        results.append(HealthCheck("Búsqueda léxica", "OK", "SQLite FTS5 (BM25)" if self.db.has_fts5
                                   else "BM25 en Python (respaldo, FTS5 no disponible)"))
        counts = self.chunks.counts()
        index_status = "OK" if counts["chunks"] else "WARN"
        if self.db.has_fts5 and counts["fts_rows"] != counts["chunks"]:
            index_status = "WARN"
        stale = int(self.db.scalar("SELECT COUNT(*) FROM chunks WHERE embedding_model <> ?", (self.embedder.name,),
                                   default=0))
        if stale:
            index_status = "WARN"
        results.append(HealthCheck("Índice", index_status,
                                   f"{counts['chunks']} fragmentos, {counts['embedded']} con vector, "
                                   f"{counts['fts_rows']} en FTS; {stale} con modelo distinto (reindexar)"))
        results.append(HealthCheck("Embeddings", "OK", self.embedder.name))
        provider = self.settings.get("llm.provider", "none")
        if provider == "none":
            results.append(HealthCheck("LLM local", "OFF", "Modo extractivo sin LLM (respaldo seguro)"))
        else:
            available = self.llm.available()
            results.append(HealthCheck("LLM local", "OK" if available else "WARN",
                                       f"{self.llm.name}: {'disponible' if available else 'no responde; se usa modo extractivo'}"))
        results.append(HealthCheck("OCR", "OK" if ocr_available() else "OFF",
                                   "Tesseract disponible" if ocr_available() else "No instalado (opcional)"))
        odata = self.connectors.status()["odata"]
        results.append(HealthCheck("Conector OData", "OK" if odata["enabled"] and odata["configured"] else "OFF",
                                   f"habilitado={odata['enabled']} configurado={odata['configured']} "
                                   f"circuito={odata['circuit']}"))
        ok, count, broken = self.audit.verify_chain()
        results.append(HealthCheck("Cadena de auditoría", "OK" if ok else "FAIL",
                                   f"{count} eventos verificados" if ok else f"alteración detectada en {broken}"))
        usage = shutil.disk_usage(self.settings.path("paths.data_dir"))
        free_gb = usage.free / 1024 ** 3
        results.append(HealthCheck("Espacio en disco", "OK" if free_gb > 1 else "WARN", f"{free_gb:.1f} GB libres"))
        log_file = self.settings.path("paths.logs_dir") / "app.log"
        size = log_file.stat().st_size / 1024 if log_file.is_file() else 0
        results.append(HealthCheck("Log técnico", "OK", f"{size:.0f} KB"))
        for warning in self.startup_warnings:
            results.append(HealthCheck("Arranque", "WARN", warning))
        return results

    def environment(self) -> dict[str, Any]:
        versions = {}
        for pkg in _PACKAGES:
            try:
                versions[pkg] = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                versions[pkg] = "no instalado"
        return {"python": sys.version.split()[0], "platform": platform.platform(), "packages": versions,
                "environment": self.settings.get("app.environment"), "app_version": self.settings.get("app.version")}
