"""
Modelo de datos interno (normalizado). Es independiente del origen: se llena tanto
por el generador de datos simulados (`seed_data.py`) como por el adaptador de
FactoryLogix (`integrations/factorylogix/adapter.py`), de modo que el resto de la
aplicación nunca sabe de dónde vinieron los datos.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Shift(str, enum.Enum):
    T1 = "Turno 1"
    T2 = "Turno 2"
    T3 = "Turno 3"


class CertificationLevel(str, enum.Enum):
    NO_CAPACITADO = "No capacitado"
    EN_ENTRENAMIENTO = "En entrenamiento"
    SUPERVISADO = "Supervisado"
    CERTIFICADO = "Certificado"
    INSTRUCTOR = "Instructor"


class UserRole(str, enum.Enum):
    ADMIN = "Administrador"
    ING_MES = "Ingeniero MES"
    SUPERVISOR = "Supervisor"
    LIDER_LINEA = "Líder de línea"
    CONSULTA = "Consulta"


class DowntimeCategory(str, enum.Enum):
    AUTORIZADO = "Tiempo no productivo autorizado"
    FALLA_EQUIPO = "Equipo con falla"
    MATERIAL_FALTANTE = "Material faltante"
    CAMBIO_PRODUCTO = "Cambio de producto"
    OTRO = "Otro"


class DefectCause(str, enum.Enum):
    PROCESO = "Error de proceso"
    MATERIAL = "Material"
    EQUIPO = "Equipo"
    PROGRAMA = "Programa"
    DISENO = "Diseño"
    METODO = "Método"
    OPERATIVO = "Posible error operativo"
    SIN_CONFIRMAR = "Causa sin confirmar"


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    shift: Mapped[Shift] = mapped_column(Enum(Shift))
    area: Mapped[str] = mapped_column(String(80))
    hire_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_new_hire: Mapped[bool] = mapped_column(Boolean, default=False)  # < 30 días
    photo_initials: Mapped[str] = mapped_column(String(4), default="")

    certifications: Mapped[list["Certification"]] = relationship(back_populates="operator")
    production_events: Mapped[list["ProductionEvent"]] = relationship(back_populates="operator")
    snapshots: Mapped[list["PerformanceSnapshot"]] = relationship(back_populates="operator")
    training_actions: Mapped[list["TrainingAction"]] = relationship(back_populates="operator")
    supervisor_notes: Mapped[list["SupervisorNote"]] = relationship(back_populates="operator")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    area: Mapped[str] = mapped_column(String(80))
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    standard_cycle_seconds: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    family: Mapped[str] = mapped_column(String(80))
    complexity: Mapped[str] = mapped_column(String(20), default="Media")  # Baja/Media/Alta


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    planned_quantity: Mapped[int] = mapped_column(Integer)
    is_small_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped["Product"] = relationship()


class ProductionEvent(Base):
    """Una unidad (o lote pequeño) procesada por un operador en una estación."""

    __tablename__ = "production_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    shift: Mapped[Shift] = mapped_column(Enum(Shift))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime)
    units_processed: Mapped[int] = mapped_column(Integer, default=1)
    units_conforming: Mapped[int] = mapped_column(Integer, default=1)
    units_rejected: Mapped[int] = mapped_column(Integer, default=0)
    units_reworked: Mapped[int] = mapped_column(Integer, default=0)
    cycle_time_seconds: Mapped[float] = mapped_column(Float)
    is_rework_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    station_was_down: Mapped[bool] = mapped_column(Boolean, default=False)

    operator: Mapped["Operator"] = relationship(back_populates="production_events")
    station: Mapped["Station"] = relationship()
    product: Mapped["Product"] = relationship()
    work_order: Mapped["WorkOrder"] = relationship()


class QualityEvent(Base):
    __tablename__ = "quality_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    production_event_id: Mapped[int | None] = mapped_column(ForeignKey("production_events.id"), nullable=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    defect_code: Mapped[str] = mapped_column(String(60))
    defect_description: Mapped[str] = mapped_column(String(200))
    cause_category: Mapped[DefectCause] = mapped_column(Enum(DefectCause))
    is_blocked_unit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_validation_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    operator: Mapped["Operator"] = relationship()
    station: Mapped["Station"] = relationship()
    product: Mapped["Product"] = relationship()


class DowntimeEvent(Base):
    __tablename__ = "downtime_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), nullable=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[DowntimeCategory] = mapped_column(Enum(DowntimeCategory))
    duration_minutes: Mapped[float] = mapped_column(Float)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String(240), default="")

    station: Mapped["Station"] = relationship()


class Certification(Base):
    __tablename__ = "certifications"
    __table_args__ = (UniqueConstraint("operator_id", "station_id", name="uq_operator_station_cert"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    level: Mapped[CertificationLevel] = mapped_column(Enum(CertificationLevel))
    certified_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    recommended_course: Mapped[str] = mapped_column(String(160), default="")
    reinforcement_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_status: Mapped[str] = mapped_column(String(40), default="Sin plan")

    operator: Mapped["Operator"] = relationship(back_populates="certifications")
    station: Mapped["Station"] = relationship()


class PerformanceSnapshot(Base):
    """Agregado diario operador+estación+producto, insumo directo del motor de puntaje."""

    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("operator_id", "station_id", "product_id", "snapshot_date", name="uq_snapshot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    shift: Mapped[Shift] = mapped_column(Enum(Shift))
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)

    units_processed: Mapped[int] = mapped_column(Integer, default=0)
    units_conforming: Mapped[int] = mapped_column(Integer, default=0)
    units_rejected: Mapped[int] = mapped_column(Integer, default=0)
    units_reworked: Mapped[int] = mapped_column(Integer, default=0)
    avg_cycle_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    std_cycle_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    operator: Mapped["Operator"] = relationship(back_populates="snapshots")
    station: Mapped["Station"] = relationship()
    product: Mapped["Product"] = relationship()


class TrainingAction(Base):
    __tablename__ = "training_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"), nullable=True)
    created_at: Mapped[date] = mapped_column(Date)
    action_type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="Propuesta")
    created_by: Mapped[str] = mapped_column(String(120), default="")

    operator: Mapped["Operator"] = relationship(back_populates="training_actions")
    station: Mapped["Station"] = relationship()


class SupervisorNote(Base):
    __tablename__ = "supervisor_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    author: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text)

    operator: Mapped["Operator"] = relationship(back_populates="supervisor_notes")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    username: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(120))
    entity: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")


class User(Base):
    """Cuentas de demostración para autenticación local. Ver README: nunca usar
    contraseñas reales aquí. Preparado para reemplazar por Active Directory
    (campo `external_directory_id`)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    external_directory_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScoringConfig(Base):
    """Fila única con los pesos vigentes del motor de puntaje (editable en Configuración)."""

    __tablename__ = "scoring_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    weight_quality: Mapped[float] = mapped_column(Float, default=0.35)
    weight_cycle: Mapped[float] = mapped_column(Float, default=0.25)
    weight_productivity: Mapped[float] = mapped_column(Float, default=0.20)
    weight_consistency: Mapped[float] = mapped_column(Float, default=0.10)
    weight_rework: Mapped[float] = mapped_column(Float, default=0.10)
    min_units_for_classification: Mapped[int] = mapped_column(Integer, default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
