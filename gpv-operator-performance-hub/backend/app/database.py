"""
Capa de acceso a base de datos. Usa SQLite para la demostración; para migrar a
SQL Server basta con cambiar `DATABASE_URL` en `.env` (por ejemplo:
`mssql+pyodbc://usuario:password@servidor/GPV_MES?driver=ODBC+Driver+17+for+SQL+Server`)
y ajustar el driver en `requirements.txt`. El resto del código (modelos, rutas,
motor de puntaje) no depende del motor de base de datos.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
