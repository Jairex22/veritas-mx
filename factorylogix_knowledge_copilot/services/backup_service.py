"""Respaldo en caliente de SQLite (API de backup) y de los archivos de conocimiento."""
from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

from core.config import Settings
from core.utils import now_iso
from models.domain import AuthenticatedUser
from security.rbac import require
from services.audit_helper import Auditor


class BackupService:
    def __init__(self, settings: Settings, audit: Auditor):
        self.settings = settings
        self.audit = audit
        self.backup_dir = settings.path("paths.data_dir") / "backups"

    def create(self, user: AuthenticatedUser, correlation_id: str = "") -> Path:
        require(user, "settings.manage")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_iso().replace(":", "").replace("-", "")[:15]
        db_copy = self.backup_dir / f"copilot_{stamp}.db"
        src = sqlite3.connect(str(self.settings.path("paths.database")))
        dst = sqlite3.connect(str(db_copy))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        archive = self.backup_dir / f"respaldo_{stamp}.zip"
        files_dir = self.settings.path("paths.files_dir")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_copy, arcname=db_copy.name)
            if files_dir.is_dir():
                for path in files_dir.rglob("*"):
                    if path.is_file():
                        zf.write(path, arcname=str(Path("knowledge_base_files") / path.relative_to(files_dir)))
        db_copy.unlink()
        self.audit(user, "backup.create", "backup", archive.name, "success", correlation_id=correlation_id)
        return archive

    def list(self) -> list[dict[str, str]]:
        if not self.backup_dir.is_dir():
            return []
        return [{"archivo": p.name, "tamaño_MB": f"{p.stat().st_size / 1024 ** 2:.2f}"}
                for p in sorted(self.backup_dir.glob("respaldo_*.zip"), reverse=True)]

    def prune(self, keep: int = 14) -> int:
        backups = sorted(self.backup_dir.glob("respaldo_*.zip"), reverse=True) if self.backup_dir.is_dir() else []
        removed = 0
        for old in backups[keep:]:
            old.unlink()
            removed += 1
        return removed

    @staticmethod
    def restore_instructions() -> str:
        return ("1) Ejecuta DETENER_WINDOWS.bat. 2) Copia data/copilot.db a un lugar seguro. 3) Extrae el ZIP de "
                "respaldo y reemplaza data/copilot.db con copilot_*.db (renómbralo a copilot.db) y "
                "knowledge_base/files con knowledge_base_files. 4) Ejecuta INICIAR_WINDOWS.bat y revisa "
                "Salud del sistema (integridad y cadena de auditoría).")

