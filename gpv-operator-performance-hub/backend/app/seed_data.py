"""
Generador de datos simulados realistas para la demostración.

Crea: 60 operadores en 3 turnos, 12 estaciones, 8 productos, 20 órdenes de
trabajo y 90 días de actividad (eventos de producción, calidad, tiempos
muertos, certificaciones, snapshots de desempeño). Incluye intencionalmente:
días sin actividad, operadores nuevos, una estación con problema de proceso
(no por culpa del operador), retrabajos y operadores con muestra insuficiente.

Ejecutar de forma independiente:  python -m app.seed_data
También se ejecuta automáticamente al iniciar el backend si la base está vacía.
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import (
    AuditLog,
    Certification,
    CertificationLevel,
    DefectCause,
    DowntimeCategory,
    DowntimeEvent,
    Operator,
    PerformanceSnapshot,
    Product,
    ProductionEvent,
    QualityEvent,
    ScoringConfig,
    Shift,
    Station,
    SupervisorNote,
    TrainingAction,
    User,
    UserRole,
    WorkOrder,
)
from .security import hash_password

settings = get_settings()

FIRST_NAMES = [
    "María", "José", "Juan", "Ana", "Luis", "Guadalupe", "Carlos", "Rosa", "Miguel", "Laura",
    "Francisco", "Elena", "Jorge", "Patricia", "Ricardo", "Sofía", "Alejandro", "Daniela", "Fernando", "Claudia",
    "Roberto", "Verónica", "Eduardo", "Gabriela", "Sergio", "Mónica", "Raúl", "Alejandra", "Arturo", "Leticia",
    "Manuel", "Beatriz", "Pedro", "Irene", "Diego", "Cecilia", "Hugo", "Teresa", "Iván", "Adriana",
    "Óscar", "Silvia", "Emmanuel", "Lorena", "Israel", "Karla", "Marco", "Yesenia", "Rubén", "Paola",
    "Víctor", "Rocío", "Gerardo", "Itzel", "Antonio", "Diana", "Salvador", "Fabiola", "Esteban", "Brenda",
]
LAST_NAMES = [
    "García", "Hernández", "Martínez", "López", "González", "Pérez", "Sánchez", "Ramírez", "Flores", "Rivera",
    "Torres", "Vázquez", "Ramos", "Reyes", "Cruz", "Morales", "Ortiz", "Gutiérrez", "Chávez", "Mendoza",
    "Jiménez", "Ruiz", "Castillo", "Romero", "Álvarez", "Vargas", "Medina", "Aguilar", "Herrera", "Guzmán",
]

STATION_DEFS = [
    ("INIT-01", "INITIALIZATION", "Preparación", 1, 25.0),
    ("THT-01", "THT AUTO INSERTION", "Inserción", 2, 18.0),
    ("HSK-01", "HEATSINK INSERTION", "Inserción", 3, 22.0),
    ("AOI-01", "AOI", "Inspección", 4, 15.0),
    ("PMM-01", "POWER MODULE MEASUREMENT", "Prueba", 5, 40.0),
    ("ICT-01", "ICT", "Prueba", 6, 35.0),
    ("FCT-01", "FCT", "Prueba", 7, 50.0),
    ("DPN-01", "DEPANEL", "Preparación", 8, 12.0),
    ("FAS-01", "FINAL ASSEMBLY", "Ensamble", 9, 60.0),
    ("FTS-01", "FINAL TEST", "Prueba", 10, 45.0),
    ("PKG-01", "PACKING", "Empaque", 11, 20.0),
    ("RWK-01", "REWORK", "Retrabajo", 12, 90.0),
]
# Estación con problema de proceso conocido (afecta a todos los operadores por igual).
PROBLEM_STATION_CODE = "ICT-01"

PRODUCT_DEFS = [
    ("PM-100", "Módulo de Potencia PM-100", "Módulos de Potencia", "Media"),
    ("PM-200", "Módulo de Potencia PM-200", "Módulos de Potencia", "Alta"),
    ("CTRL-30", "Controlador CTRL-30", "Controladores", "Media"),
    ("INV-50", "Inversor INV-50", "Inversores", "Alta"),
    ("ECU-12", "Unidad de Control ECU-12", "Controladores", "Baja"),
    ("SNS-7", "Módulo Sensor SNS-7", "Sensores", "Baja"),
    ("PWR-9", "Fuente PWR-9", "Fuentes", "Media"),
    ("CTL-LITE", "Controlador CTL-Lite", "Controladores", "Baja"),
]
COMPLEXITY_CYCLE_MULTIPLIER = {"Baja": 0.85, "Media": 1.0, "Alta": 1.25}
COMPLEXITY_DEFECT_MULTIPLIER = {"Baja": 0.8, "Media": 1.0, "Alta": 1.35}

AREAS = ["SMT", "Inserción", "Ensamble", "Prueba", "Empaque"]

DEMO_USERS = [
    ("admin", "Administradora del Sistema", "Admin#2026", UserRole.ADMIN),
    ("ingeniero.mes", "Ingeniero MES Demo", "Ingeniero#2026", UserRole.ING_MES),
    ("supervisor.t1", "Supervisor Turno 1 Demo", "Supervisor#2026", UserRole.SUPERVISOR),
    ("lider.linea1", "Líder de Línea 1 Demo", "Lider#2026", UserRole.LIDER_LINEA),
    ("consulta.calidad", "Consulta Calidad Demo", "Consulta#2026", UserRole.CONSULTA),
]

DEFECT_LIBRARY = [
    ("SOLDER-BRIDGE", "Puente de soldadura", DefectCause.PROCESO),
    ("MISSING-COMP", "Componente faltante", DefectCause.MATERIAL),
    ("MISALIGN", "Componente desalineado", DefectCause.PROCESO),
    ("PROGRAM-FAIL", "Falla de programación de prueba", DefectCause.PROGRAMA),
    ("EQUIP-DRIFT", "Desviación de calibración de equipo", DefectCause.EQUIPO),
    ("DESIGN-TOL", "Tolerancia de diseño ajustada", DefectCause.DISENO),
    ("METHOD-SEQ", "Secuencia de método no seguida", DefectCause.METODO),
    ("HANDLING", "Posible daño por manejo", DefectCause.OPERATIVO),
    ("UNKNOWN", "Falla intermitente sin causa confirmada", DefectCause.SIN_CONFIRMAR),
]

DOWNTIME_LIBRARY = [
    (DowntimeCategory.FALLA_EQUIPO, "Paro por falla de equipo, se generó ticket de mantenimiento."),
    (DowntimeCategory.MATERIAL_FALTANTE, "Espera de material del almacén."),
    (DowntimeCategory.CAMBIO_PRODUCTO, "Cambio de producto / set-up de línea."),
    (DowntimeCategory.AUTORIZADO, "Junta de turno / 5S programada."),
    (DowntimeCategory.OTRO, "Otro motivo registrado por el supervisor."),
]


def _rand_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)} {random.choice(LAST_NAMES)}"


def _initials(name: str) -> str:
    parts = name.split()
    return (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else name[:2].upper()


def run_seed(db: Session, force: bool = False) -> None:
    if not force and db.query(Operator).count() > 0:
        return

    random.seed(settings.seed_random_state)
    today = date.today()
    start_day = today - timedelta(days=89)

    # ---------------------------------------------------------------- Stations
    stations: list[Station] = []
    for code, name, area, seq, std_cycle in STATION_DEFS:
        st = Station(code=code, name=name, area=area, sequence_order=seq, standard_cycle_seconds=std_cycle, is_active=True)
        db.add(st)
        stations.append(st)
    db.flush()
    station_by_code = {s.code: s for s in stations}
    process_stations = [s for s in stations if s.code != "RWK-01"]
    rework_station = station_by_code["RWK-01"]

    # ---------------------------------------------------------------- Products
    products: list[Product] = []
    for code, name, family, complexity in PRODUCT_DEFS:
        p = Product(code=code, name=name, family=family, complexity=complexity)
        db.add(p)
        products.append(p)
    db.flush()

    # ---------------------------------------------------------------- Work Orders
    work_orders: list[WorkOrder] = []
    for i in range(1, 21):
        product = random.choice(products)
        opened = start_day + timedelta(days=random.randint(0, 60))
        small_batch = random.random() < 0.2
        planned_qty = random.randint(80, 400) if small_batch else random.randint(800, 4000)
        closed = None
        if random.random() < 0.6:
            closed = min(today, opened + timedelta(days=random.randint(5, 45)))
        wo = WorkOrder(
            code=f"WO-2026-{i:04d}",
            product_id=product.id,
            planned_quantity=planned_qty,
            is_small_batch=small_batch,
            opened_at=opened,
            closed_at=closed,
        )
        db.add(wo)
        work_orders.append(wo)
    db.flush()

    # ---------------------------------------------------------------- Operators
    shifts = [Shift.T1, Shift.T2, Shift.T3]
    operators: list[Operator] = []
    used_numbers: set[str] = set()
    skill_factor: dict[int, float] = {}
    low_sample_flags: dict[int, bool] = {}

    for i in range(60):
        while True:
            emp_number = f"EMP-{1000 + i}"
            if emp_number not in used_numbers:
                used_numbers.add(emp_number)
                break
        name = _rand_name()
        shift = shifts[i % 3]
        area = AREAS[i % len(AREAS)]

        is_new_hire = i < 5  # primeros 5 son ingresos recientes (< 30 días)
        if is_new_hire:
            hire_date = today - timedelta(days=random.randint(1, 28))
        else:
            hire_date = today - timedelta(days=random.randint(90, 2600))

        op = Operator(
            employee_number=emp_number,
            full_name=name,
            shift=shift,
            area=area,
            hire_date=hire_date,
            is_active=True,
            is_new_hire=is_new_hire,
            photo_initials=_initials(name),
        )
        db.add(op)
        operators.append(op)

        # Factor de habilidad: la mayoría cerca de 1.0; unos pocos claramente
        # sobresalientes o con dificultades para dar variedad al demo.
        if i < 6:
            skill_factor[i] = random.uniform(1.12, 1.22)  # sobresalientes
        elif i < 12:
            skill_factor[i] = random.uniform(0.70, 0.82)  # requieren apoyo
        else:
            skill_factor[i] = random.gauss(1.0, 0.08)

        # Últimos 5 operadores tendrán muy poca actividad (muestra insuficiente).
        low_sample_flags[i] = i >= 55

    db.flush()

    # ---------------------------------------------------------------- Certifications
    for idx, op in enumerate(operators):
        n_stations = random.randint(2, 4)
        assigned = random.sample(process_stations, k=min(n_stations, len(process_stations)))
        for j, st in enumerate(assigned):
            if op.is_new_hire:
                level = CertificationLevel.EN_ENTRENAMIENTO if j == 0 else CertificationLevel.SUPERVISADO
            elif skill_factor[idx] > 1.12 and random.random() < 0.3:
                level = CertificationLevel.INSTRUCTOR
            elif skill_factor[idx] < 0.85 and random.random() < 0.4:
                level = CertificationLevel.SUPERVISADO
            else:
                level = random.choices(
                    [CertificationLevel.CERTIFICADO, CertificationLevel.SUPERVISADO, CertificationLevel.EN_ENTRENAMIENTO],
                    weights=[0.75, 0.15, 0.10],
                )[0]

            certified_at = op.hire_date + timedelta(days=random.randint(10, 60)) if level != CertificationLevel.NO_CAPACITADO else None
            expires_at = None
            if level in (CertificationLevel.CERTIFICADO, CertificationLevel.INSTRUCTOR) and certified_at:
                expires_at = certified_at + timedelta(days=365 * random.choice([1, 2]))
            reinforcement = level == CertificationLevel.SUPERVISADO or skill_factor[idx] < 0.85

            db.add(
                Certification(
                    operator_id=op.id,
                    station_id=st.id,
                    level=level,
                    certified_at=certified_at,
                    expires_at=expires_at,
                    recommended_course=f"Reforzamiento {st.name.title()}" if reinforcement else "",
                    reinforcement_needed=reinforcement,
                    plan_status="En curso" if reinforcement else "Sin plan",
                )
            )

    # ---------------------------------------------------------------- Production / Quality / Snapshots
    snapshot_agg: dict[tuple, dict] = defaultdict(
        lambda: {"processed": 0, "conforming": 0, "rejected": 0, "reworked": 0, "cycle_times": []}
    )

    open_wo_by_product: dict[int, list[WorkOrder]] = defaultdict(list)
    for wo in work_orders:
        open_wo_by_product[wo.product_id].append(wo)

    current_day = start_day
    while current_day <= today:
        # Fines de semana con actividad reducida (línea corre con dotación mínima).
        is_weekend = current_day.weekday() >= 5
        for idx, op in enumerate(operators):
            if is_weekend and random.random() < 0.75:
                continue
            # Ausentismo normal entre semana.
            attendance_prob = 0.90 if not is_weekend else 0.35
            if op.is_new_hire and current_day < op.hire_date:
                continue
            if random.random() > attendance_prob:
                continue
            if low_sample_flags[idx] and random.random() > 0.12:
                continue  # operadores con muestra intencionalmente insuficiente

            n_events = random.randint(1, 3)
            op_stations = random.sample(process_stations, k=min(n_events, len(process_stations)))

            for st in op_stations:
                product = random.choice(products)
                wo_candidates = open_wo_by_product.get(product.id) or work_orders
                wo = random.choice(wo_candidates)

                complexity_mult = COMPLEXITY_CYCLE_MULTIPLIER[product.complexity]
                defect_mult = COMPLEXITY_DEFECT_MULTIPLIER[product.complexity]
                is_problem_station = st.code == PROBLEM_STATION_CODE
                station_mult = 1.35 if is_problem_station else 1.0
                station_defect_mult = 1.8 if is_problem_station else 1.0

                units = random.randint(6, 45)
                if wo.is_small_batch:
                    units = max(3, units // 2)

                noise = random.gauss(1.0, 0.10 if not is_problem_station else 0.22)
                cycle_time = max(
                    2.0,
                    st.standard_cycle_seconds * complexity_mult * station_mult * noise / max(skill_factor[idx], 0.4),
                )

                base_defect_rate = 0.015 * defect_mult * station_defect_mult / max(skill_factor[idx], 0.5)
                base_defect_rate = min(base_defect_rate, 0.35)
                rejected = sum(1 for _ in range(units) if random.random() < base_defect_rate)
                reworked = sum(1 for _ in range(max(rejected, 0)) if random.random() < 0.55)
                conforming = units - rejected

                station_was_down = random.random() < (0.05 if is_problem_station else 0.02)
                is_rework_pass = st.code == "RWK-01"

                event_hour = {"Turno 1": 7, "Turno 2": 15, "Turno 3": 23}[op.shift.value]
                event_ts = datetime.combine(current_day, time(hour=event_hour % 24)) + timedelta(
                    minutes=random.randint(0, 420)
                )

                pe = ProductionEvent(
                    operator_id=op.id,
                    station_id=st.id,
                    product_id=product.id,
                    work_order_id=wo.id,
                    shift=op.shift,
                    event_date=current_day,
                    event_timestamp=event_ts,
                    units_processed=units,
                    units_conforming=conforming,
                    units_rejected=rejected,
                    units_reworked=reworked,
                    cycle_time_seconds=round(cycle_time, 2),
                    is_rework_pass=is_rework_pass,
                    station_was_down=station_was_down,
                )
                db.add(pe)
                db.flush()

                key = (op.id, st.id, product.id, current_day)
                agg = snapshot_agg[key]
                agg["processed"] += units
                agg["conforming"] += conforming
                agg["rejected"] += rejected
                agg["reworked"] += reworked
                agg["cycle_times"].append(cycle_time)
                agg["wo_id"] = wo.id

                if rejected > 0:
                    n_defect_events = min(rejected, random.randint(1, 3))
                    remaining = rejected
                    for k in range(n_defect_events):
                        code, desc, cause = random.choice(DEFECT_LIBRARY)
                        if is_problem_station and random.random() < 0.5:
                            code, desc, cause = "EQUIP-DRIFT", "Desviación de calibración de equipo", DefectCause.EQUIPO
                        qty = remaining if k == n_defect_events - 1 else random.randint(1, max(1, remaining // 2))
                        qty = max(1, min(qty, remaining))
                        remaining -= qty
                        db.add(
                            QualityEvent(
                                production_event_id=pe.id,
                                operator_id=op.id,
                                station_id=st.id,
                                product_id=product.id,
                                event_date=current_day,
                                defect_code=code,
                                defect_description=desc,
                                cause_category=cause,
                                is_blocked_unit=random.random() < 0.15,
                                is_validation_failure=st.code in ("ICT-01", "FCT-01", "FTS-01") and random.random() < 0.3,
                                quantity=qty,
                            )
                        )
                        if remaining <= 0:
                            break

            # Tiempo muerto ocasional del operador/estación.
            if random.random() < 0.06:
                st = random.choice(op_stations)
                category, note = random.choice(DOWNTIME_LIBRARY)
                db.add(
                    DowntimeEvent(
                        station_id=st.id,
                        operator_id=op.id,
                        event_date=current_day,
                        category=category,
                        duration_minutes=round(random.uniform(5, 60), 1),
                        is_authorized=category == DowntimeCategory.AUTORIZADO or random.random() < 0.4,
                        notes=note,
                    )
                )

        current_day += timedelta(days=1)

    db.flush()

    # ---------------------------------------------------------------- Snapshots
    for (operator_id, station_id, product_id, snap_date), agg in snapshot_agg.items():
        cycle_times = agg["cycle_times"]
        mean_ct = sum(cycle_times) / len(cycle_times) if cycle_times else 0.0
        if len(cycle_times) > 1:
            variance = sum((c - mean_ct) ** 2 for c in cycle_times) / len(cycle_times)
            std_ct = variance ** 0.5
        else:
            std_ct = 0.0
        db.add(
            PerformanceSnapshot(
                operator_id=operator_id,
                station_id=station_id,
                product_id=product_id,
                work_order_id=agg.get("wo_id"),
                shift=db.get(Operator, operator_id).shift,
                snapshot_date=snap_date,
                units_processed=agg["processed"],
                units_conforming=agg["conforming"],
                units_rejected=agg["rejected"],
                units_reworked=agg["reworked"],
                avg_cycle_time_seconds=round(mean_ct, 2),
                std_cycle_time_seconds=round(std_ct, 2),
            )
        )

    # ---------------------------------------------------------------- Training / Notes
    struggling_ops = [op for idx, op in enumerate(operators) if 5 <= idx < 12]
    for op in struggling_ops[:5]:
        db.add(
            TrainingAction(
                operator_id=op.id,
                station_id=random.choice(process_stations).id,
                created_at=today - timedelta(days=random.randint(3, 20)),
                action_type="Reforzamiento en estación",
                description="Se recomienda sesión de reforzamiento práctico por variación reciente en cumplimiento de ciclo.",
                status=random.choice(["Propuesta", "En curso", "Completada"]),
                created_by="Ingeniero MES Demo",
            )
        )
        db.add(
            SupervisorNote(
                operator_id=op.id,
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 15)),
                author="Supervisor Turno 1 Demo",
                note="Revisar contexto de turno: hubo cambio de producto y orden pequeña en la semana evaluada.",
            )
        )

    # ---------------------------------------------------------------- Users (demo)
    for username, display_name, plain_password, role in DEMO_USERS:
        db.add(
            User(
                username=username,
                display_name=display_name,
                hashed_password=hash_password(plain_password),
                role=role,
                is_active=True,
            )
        )

    # ---------------------------------------------------------------- Scoring config
    db.add(
        ScoringConfig(
            weight_quality=settings.score_weight_quality,
            weight_cycle=settings.score_weight_cycle,
            weight_productivity=settings.score_weight_productivity,
            weight_consistency=settings.score_weight_consistency,
            weight_rework=settings.score_weight_rework,
            min_units_for_classification=settings.score_min_units,
            updated_at=datetime.utcnow(),
            updated_by="Sistema (valores iniciales)",
        )
    )

    # ---------------------------------------------------------------- Audit seed
    db.add(
        AuditLog(
            timestamp=datetime.utcnow(),
            username="sistema",
            role="Sistema",
            action="Carga de datos simulados",
            entity="Base de datos",
            details="Se generaron 90 días de actividad simulada para la demostración.",
        )
    )

    db.commit()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(db, force=True)
        print("Datos simulados generados correctamente.")
        print("Cuentas demo (usuario / contraseña / rol):")
        for username, _, plain_password, role in DEMO_USERS:
            print(f"  - {username} / {plain_password} / {role.value}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
