"""Centro de Operaciones Controladas.

Flujo obligatorio para TODA acción:
  1. Usuario autenticado y rol autorizado.
  2. PREPARE: validación de parámetros, lectura del estado previo y validación
     del flujo de proceso. Emite un token de confirmación firmado (HMAC) atado
     al usuario, la acción, los parámetros y la versión del estado.
  3. EXECUTE: confirmación explícita, verificación del token, idempotencia,
     control de concurrencia (versión del estado), ejecución, comprobación
     posterior del estado y registro de auditoría.

Ejecutores:
  - DEMO: simulador en memoria. Bloqueado por diseño fuera de modo DEMO.
  - REAL: registro VACÍO en v1.0. Ninguna acción tiene método oficial
    verificado, por lo que todas responden NO DISPONIBLE con los requisitos
    faltantes. No existe código que escriba en FactoryLogix ni en sus tablas.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..core.context import get_correlation_id
from ..core.db import Database
from ..core.errors import AppError, Conflict, Forbidden, NotAvailable, ValidationFailed
from ..core.security import Role, SessionUser
from ..data.demo import ROUTE, TEST_STATIONS, DemoDataSource
from ..data.models import Unit
from ..data.source import ProductionDataSource
from ..settings import Settings
from .audit import AuditService

TOKEN_TTL_SECONDS = 180
_SAFE_TEXT = re.compile(r"^[^\x00-\x1f<>]*$")


class ProductionWriteBlocked(RuntimeError):
    """Se lanza si algo intenta usar el simulador DEMO fuera de modo DEMO."""


@dataclass
class ParamSpec:
    name: str
    label: str
    kind: str = "text"  # text | enum | list
    required: bool = True
    options: list[str] | None = None
    pattern: str | None = None
    min_len: int = 1
    max_len: int = 120
    help: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


SERIAL_PATTERN = r"^[A-Za-z0-9._\-/]{3,64}$"
COMMON_MISSING = [
    "Método oficial de FactoryLogix identificado en documentación vigente (xTend API) para esta versión instalada.",
    "Licencia del módulo/interfaz correspondiente confirmada por AEGIS/GPV.",
    "Cuenta de servicio con privilegios mínimos aprobada por el responsable del sistema.",
    "Pruebas en ambiente de validación (no productivo) con evidencia documentada.",
    "Autorización explícita y firmada del responsable de FactoryLogix en GPV.",
]


@dataclass
class ActionSpec:
    id: str
    name: str
    category: str
    description: str
    roles: set[Role]
    params: list[ParamSpec]
    consequences: str
    reversibility: str
    privileges: str
    target: str = "serial"  # serial | box
    destructive: bool = False
    official_method: str | None = None  # Ningún método verificado en v1.0
    endpoint: str | None = None
    license_requirement: str = "Por confirmar con AEGIS / administrador de FactoryLogix."
    authentication: str = "Por confirmar (xTend API: credenciales de servicio; documentación no accesible desde el entorno de desarrollo)."
    precheck: Callable[[Any, dict], list[tuple[str, bool, str]]] | None = None
    demo_execute: Callable[[DemoDataSource, Any, dict, str], dict] | None = None
    postcheck: Callable[[Any, dict, dict], list[tuple[str, bool, str]]] | None = None
    missing_requirements: list[str] = field(default_factory=lambda: list(COMMON_MISSING))

    def describe(self, mode: str, real_available: bool) -> dict:
        if self.destructive:
            availability, reason = "NO_DISPONIBLE", "Acción potencialmente destructiva: deshabilitada en todos los modos hasta superar pruebas y recibir autorización."
        elif mode == "DEMO":
            availability, reason = "SIMULADA_DEMO", "Se ejecuta únicamente contra datos sintéticos en memoria. No alcanza FactoryLogix."
        elif real_available:
            availability, reason = "DISPONIBLE", ""
        else:
            availability, reason = "NO_DISPONIBLE", "Sin método oficial verificado para esta instalación."
        return {
            "id": self.id, "name": self.name, "category": self.category, "description": self.description,
            "roles": sorted(r.value for r in self.roles), "params": [p.to_dict() for p in self.params],
            "target": self.target, "destructive": self.destructive,
            "availability": availability, "availability_reason": reason,
            "integration": {
                "official_method": self.official_method or "NO VERIFICADO",
                "endpoint": self.endpoint or "NO VERIFICADO",
                "license": self.license_requirement,
                "authentication": self.authentication,
                "privileges": self.privileges,
                "consequences": self.consequences,
                "reversibility": self.reversibility,
                "verification_status": "VERIFICADO" if self.official_method else "PENDIENTE",
                "missing_requirements": [] if self.official_method else self.missing_requirements,
            },
        }


# ----------------------------------------------------------------------------
# Validaciones de flujo de proceso (independientes del ejecutor)
# ----------------------------------------------------------------------------
def _check(name: str, ok: bool, msg: str) -> tuple[str, bool, str]:
    return (name, bool(ok), msg)


def _not_finished(u: Unit) -> tuple[str, bool, str]:
    return _check("Unidad activa", u.status not in ("PACKED", "COMPLETE", "SCRAPPED"),
                  f"Estado actual: {u.status}.")


def _pre_event(u: Unit, p: dict) -> list:
    return [_not_finished(u)]


def _pre_test(u: Unit, p: dict) -> list:
    return [
        _not_finished(u),
        _check("Sin HOLD activo", u.status != "HOLD", f"Estado: {u.status}."),
        _check("Sin defectos abiertos", not u.open_defects, f"{len(u.open_defects)} defecto(s) abierto(s)."),
        _check("Estación de prueba", p["station"] in TEST_STATIONS, f"{p['station']} {'es' if p['station'] in TEST_STATIONS else 'no es'} estación de prueba."),
        _check("Estación actual coincide", u.current_station == p["station"],
               f"Estación actual: {u.current_station or '-'}; solicitada: {p['station']}."),
    ]


def _pre_defect(u: Unit, p: dict) -> list:
    return [
        _not_finished(u),
        _check("Sin HOLD activo", u.status != "HOLD", f"Estado: {u.status}."),
        _check("Estación actual coincide", u.current_station == p["station"],
               f"Estación actual: {u.current_station or '-'}; solicitada: {p['station']}."),
    ]


def _pre_repair(u: Unit, p: dict) -> list:
    d = next((x for x in u.defects if x.id == p["defect_id"]), None)
    return [
        _check("Unidad en reparación", u.status == "IN_REPAIR", f"Estado: {u.status}."),
        _check("Defecto pertenece al serial", d is not None, f"Defecto {p['defect_id']}."),
        _check("Defecto abierto", d is not None and d.status == "OPEN", f"Estado del defecto: {d.status if d else '-'}."),
    ]


def _pre_hold(u: Unit, p: dict) -> list:
    return [_not_finished(u), _check("Sin HOLD previo", u.status != "HOLD", f"Estado: {u.status}.")]


def _pre_release(u: Unit, p: dict) -> list:
    unverified = [d.id for d in u.defects if d.status != "VERIFIED"]
    return [
        _check("Unidad en HOLD", u.status == "HOLD", f"Estado: {u.status}."),
        _check("Sin defectos abiertos", not u.open_defects, f"{len(u.open_defects)} defecto(s) abierto(s)."),
        _check("Defectos verificados con re-prueba", not unverified,
               "Todos verificados." if not unverified else f"Sin verificación: {', '.join(unverified)}."),
    ]


def _pre_complete(u: Unit, p: dict) -> list:
    return [
        _not_finished(u),
        _check("Sin HOLD activo", u.status != "HOLD", f"Estado: {u.status}."),
        _check("Sin defectos abiertos", not u.open_defects, f"{len(u.open_defects)} defecto(s) abierto(s)."),
        _check("Estación no es de prueba", p["station"] not in TEST_STATIONS and p["station"] != "PACK",
               "Las pruebas se registran con 'Registrar resultado de prueba'; el empaque con 'Procesar packing'."),
        _check("Estación actual coincide", u.current_station == p["station"],
               f"Estación actual: {u.current_station or '-'}; solicitada: {p['station']}."),
    ]


def packing_checks(box: dict, units: list[Unit], box_lookup: Callable[[str], str | None]) -> list:
    checks = []
    serials = [u.serial for u in units]
    dupes = sorted({s for s in serials if serials.count(s) > 1})
    checks.append(_check("Sin seriales duplicados", not dupes, ", ".join(dupes) or "OK"))
    remaining = box["capacity"] - len(box["serials"])
    checks.append(_check("Cantidad dentro de capacidad", len(set(serials)) <= remaining,
                         f"{len(set(serials))} a empacar; disponibles {remaining} de {box['capacity']}."))
    for u in units:
        problems = []
        if u.assembly != box["assembly"]:
            problems.append(f"ensamble {u.assembly} ≠ {box['assembly']}")
        if u.revision != box["revision"]:
            problems.append(f"revisión {u.revision} ≠ {box['revision']}")
        if u.status != "IN_PROCESS" or u.current_station != "PACK":
            problems.append(f"no liberada para empaque (estado {u.status}, estación {u.current_station or '-'})")
        if u.open_defects:
            problems.append("defectos abiertos")
        other = box_lookup(u.serial)
        if other:
            problems.append(f"ya empacada en {other}")
        checks.append(_check(f"Unidad {u.serial}", not problems, "; ".join(problems) or "Liberada y conforme."))
    return checks


# ----------------------------------------------------------------------------
# Comprobaciones posteriores
# ----------------------------------------------------------------------------
def _post_event_count(before: dict, after: Unit) -> list:
    return [_check("Nuevo evento en historial", len(after.events) > before["events"],
                   f"Eventos: {before['events']} → {len(after.events)}.")]


def _post_generic(u: Unit, p: dict, before: dict) -> list:
    return _post_event_count(before, u) + [_check("Versión de estado incrementada", u.version > before["version"],
                                                  f"Versión {before['version']} → {u.version}.")]


def _post_hold(u: Unit, p: dict, before: dict) -> list:
    return _post_generic(u, p, before) + [_check("Estado HOLD aplicado", u.status == "HOLD", f"Estado: {u.status}.")]


def _post_release(u: Unit, p: dict, before: dict) -> list:
    return _post_generic(u, p, before) + [_check("HOLD liberado", u.status != "HOLD", f"Estado: {u.status}.")]


def _post_repair(u: Unit, p: dict, before: dict) -> list:
    d = next((x for x in u.defects if x.id == p["defect_id"]), None)
    return _post_generic(u, p, before) + [
        _check("Defecto en estado REPARADO (pendiente de re-prueba)", d is not None and d.status == "REPAIRED",
               f"Estado: {d.status if d else '-'}. Se requiere re-prueba PASS para considerarlo resuelto.")]


STATION_OPTIONS = ROUTE + ["DEBUG"]

ACTIONS: dict[str, ActionSpec] = {a.id: a for a in [
    ActionSpec(
        "register_production_event", "Registrar evento de producción", "Tracking",
        "Registra una nota/evento informativo en el historial del serial.",
        {Role.OPERATOR, Role.ENGINEERING, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("station", "Estación", "enum", options=STATION_OPTIONS),
         ParamSpec("note", "Nota", min_len=3, max_len=240)],
        "Agrega un evento informativo al historial; no cambia la ruta.", "No reversible en MES (corrección mediante nota adicional).",
        "Operador de estación con acceso a la línea.", precheck=_pre_event,
        demo_execute=lambda s, u, p, op: s.sim_register_event(u, p["station"], p["note"], op), postcheck=_post_generic),
    ActionSpec(
        "record_test_result", "Registrar resultado de prueba", "Pruebas",
        "Registra PASS/FAIL en la estación de prueba actual del serial.",
        {Role.OPERATOR, Role.ENGINEERING, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN),
         ParamSpec("station", "Estación de prueba", "enum", options=sorted(TEST_STATIONS)),
         ParamSpec("result", "Resultado", "enum", options=["PASS", "FAIL"]),
         ParamSpec("note", "Nota", required=False, min_len=0, max_len=240)],
        "PASS avanza la unidad en la ruta; FAIL la mantiene en la estación para registro de defecto.",
        "No reversible: un resultado de prueba es un registro de calidad.", "Operador de prueba certificado.",
        precheck=_pre_test, demo_execute=lambda s, u, p, op: s.sim_record_test(u, p["station"], p["result"], op, p.get("note", "")),
        postcheck=_post_generic),
    ActionSpec(
        "record_defect", "Registrar defecto", "Defectos",
        "Registra un defecto y envía la unidad a reparación (DEBUG).",
        {Role.OPERATOR, Role.QUALITY, Role.ENGINEERING, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("station", "Estación", "enum", options=ROUTE),
         ParamSpec("code", "Código de defecto", pattern=r"^[A-Z0-9\-]{2,24}$", max_len=24),
         ParamSpec("description", "Descripción", min_len=3, max_len=160),
         ParamSpec("symptom", "Síntoma", required=False, min_len=0, max_len=160),
         ParamSpec("ref_designator", "Ref. designador", required=False, min_len=0, max_len=24)],
        "Abre un defecto y cambia el estado de la unidad a IN_REPAIR.", "Reversible sólo mediante reparación + re-prueba.",
        "Operador/Calidad con permiso de registro de defectos.", precheck=_pre_defect,
        demo_execute=lambda s, u, p, op: s.sim_record_defect(u, p["station"], p["code"], p["description"],
                                                             p.get("symptom", ""), p.get("ref_designator", ""), op),
        postcheck=_post_generic),
    ActionSpec(
        "record_repair", "Registrar reparación", "Reparación",
        "Registra la acción de reparación de un defecto abierto. El defecto queda REPARADO pendiente de re-prueba.",
        {Role.OPERATOR, Role.ENGINEERING, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN),
         ParamSpec("defect_id", "ID de defecto", pattern=r"^[A-Za-z0-9\-]{3,40}$"),
         ParamSpec("action", "Acción de reparación", min_len=5, max_len=200)],
        "Cierra el defecto como REPARADO y devuelve la unidad a la estación de detección para re-prueba.",
        "No reversible; un fallo en re-prueba abre un nuevo defecto.", "Técnico de reparación.",
        precheck=_pre_repair, demo_execute=lambda s, u, p, op: s.sim_record_repair(u, p["defect_id"], p["action"], op),
        postcheck=_post_repair),
    ActionSpec(
        "place_hold", "Aplicar HOLD (contención)", "Calidad",
        "Retiene la unidad para contención de calidad.",
        {Role.QUALITY, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("reason", "Motivo", min_len=10, max_len=240)],
        "La unidad no puede avanzar hasta su liberación.", "Reversible mediante 'Liberar HOLD' por Calidad.",
        "Calidad.", precheck=_pre_hold, demo_execute=lambda s, u, p, op: s.sim_place_hold(u, p["reason"], op),
        postcheck=_post_hold),
    ActionSpec(
        "release_hold", "Liberar HOLD", "Calidad",
        "Libera una contención cuando todos los defectos tienen evidencia de reparación y re-prueba.",
        {Role.QUALITY, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("reason", "Justificación", min_len=10, max_len=240)],
        "La unidad puede continuar en la ruta.", "Reversible aplicando un nuevo HOLD.", "Calidad.",
        precheck=_pre_release, demo_execute=lambda s, u, p, op: s.sim_release_hold(u, p["reason"], op),
        postcheck=_post_release),
    ActionSpec(
        "complete_station", "Completar estación (tracking)", "Tracking",
        "Registra el paso por una estación no-prueba (ensamble, depanel, SMT) y avanza la ruta.",
        {Role.OPERATOR, Role.ENGINEERING, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("station", "Estación", "enum",
                                                                         options=[s for s in ROUTE if s not in TEST_STATIONS and s != "PACK"])],
        "Avanza la unidad a la siguiente estación de la ruta.", "No reversible en MES.", "Operador de estación.",
        precheck=_pre_complete, demo_execute=lambda s, u, p, op: s.sim_complete_station(u, p["station"], op),
        postcheck=_post_generic),
    ActionSpec(
        "pack_box", "Procesar packing", "Packing",
        "Empaca seriales liberados en una caja abierta.",
        {Role.OPERATOR, Role.QUALITY, Role.ADMIN},
        [ParamSpec("box_id", "Caja", pattern=r"^[A-Za-z0-9\-]{3,40}$"),
         ParamSpec("serials", "Seriales", "list", pattern=SERIAL_PATTERN, max_len=50)],
        "Asocia los seriales a la caja y los marca como empacados.", "Reversible sólo mediante desempaque oficial (no implementado).",
        "Operador de empaque.", target="box"),
    ActionSpec(
        "scrap_unit", "Scrap de unidad", "Disposición",
        "Disposición final de una unidad no reparable.",
        {Role.QUALITY, Role.ADMIN},
        [ParamSpec("serial", "Serial", pattern=SERIAL_PATTERN), ParamSpec("reason", "Motivo", min_len=10, max_len=240)],
        "Irreversible: la unidad sale definitivamente del proceso.", "IRREVERSIBLE.", "Calidad + aprobación MRB.",
        destructive=True),
]}


# ----------------------------------------------------------------------------
class OperationsService:
    def __init__(self, settings: Settings, db: Database, audit: AuditService, source: ProductionDataSource,
                 secret: bytes):
        self.settings = settings
        self.db = db
        self.audit = audit
        self.source = source
        self.secret = secret
        # Registro de ejecutores REALES: intencionalmente vacío en v1.0.
        self.real_executors: dict[str, Callable] = {}

    # ---------------- catálogo ----------------
    def catalog(self) -> list[dict]:
        mode = self.settings.mode.value
        return [a.describe(mode, a.id in self.real_executors) for a in ACTIONS.values()]

    def _spec(self, action_id: str) -> ActionSpec:
        spec = ACTIONS.get(action_id)
        if not spec:
            raise AppError(f"Acción desconocida: {action_id}", code="UNKNOWN_ACTION", status_code=404)
        return spec

    def _ensure_available(self, spec: ActionSpec, user: SessionUser) -> None:
        if user.role not in spec.roles:
            raise Forbidden(f"El rol {user.role.value} no está autorizado para '{spec.name}'.",
                            details={"allowed_roles": sorted(r.value for r in spec.roles)})
        if spec.destructive:
            raise NotAvailable(f"'{spec.name}' está deshabilitada: acción potencialmente destructiva.",
                               code="ACTION_DISABLED_DESTRUCTIVE",
                               details={"missing_requirements": spec.missing_requirements})
        if self.settings.is_demo:
            return
        if spec.id not in self.real_executors:
            raise NotAvailable(
                f"NO DISPONIBLE: '{spec.name}' no tiene un método oficial de FactoryLogix verificado para esta instalación.",
                code="ACTION_NOT_AVAILABLE", details={"missing_requirements": spec.missing_requirements})
        if not self.settings.allow_production_writes:
            raise NotAvailable("Escrituras en producción deshabilitadas (GPV_ALLOW_PRODUCTION_WRITES=false).",
                               code="PRODUCTION_WRITES_DISABLED")

    # ---------------- parámetros ----------------
    @staticmethod
    def validate_params(spec: ActionSpec, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValidationFailed("Los parámetros deben ser un objeto.")
        unknown = set(raw) - {p.name for p in spec.params}
        if unknown:
            raise ValidationFailed(f"Parámetros no permitidos: {', '.join(sorted(unknown))}.")
        clean: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for p in spec.params:
            value = raw.get(p.name)
            if p.kind == "list":
                items = value if isinstance(value, list) else []
                items = [str(x).strip() for x in items if str(x).strip()]
                if p.required and not items:
                    errors[p.name] = "Requerido."
                elif len(items) > p.max_len:
                    errors[p.name] = f"Máximo {p.max_len} elementos."
                elif p.pattern and any(not re.match(p.pattern, x) for x in items):
                    errors[p.name] = "Formato inválido en uno o más elementos."
                clean[p.name] = items
                continue
            value = "" if value is None else str(value).strip()
            if not value:
                if p.required:
                    errors[p.name] = "Requerido."
                clean[p.name] = ""
                continue
            if len(value) < p.min_len or len(value) > p.max_len:
                errors[p.name] = f"Longitud entre {p.min_len} y {p.max_len}."
            elif p.kind == "enum" and value not in (p.options or []):
                errors[p.name] = f"Valor no permitido. Opciones: {', '.join(p.options or [])}."
            elif p.pattern and not re.match(p.pattern, value):
                errors[p.name] = "Formato inválido."
            elif not _SAFE_TEXT.match(value):
                errors[p.name] = "Contiene caracteres no permitidos."
            clean[p.name] = value
        if errors:
            raise ValidationFailed("Parámetros inválidos.", details={"fields": errors})
        return clean

    # ---------------- token de confirmación ----------------
    @staticmethod
    def _params_hash(params: dict) -> str:
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    def _sign(self, payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode().rstrip("=")
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def _verify(self, token: str) -> dict:
        try:
            body, sig = token.rsplit(".", 1)
        except (ValueError, AttributeError):
            raise ValidationFailed("Token de confirmación inválido.", code="INVALID_CONFIRMATION")
        expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValidationFailed("Token de confirmación inválido.", code="INVALID_CONFIRMATION")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            raise ValidationFailed("La confirmación expiró. Prepare la operación nuevamente.", code="CONFIRMATION_EXPIRED")
        return payload

    # ---------------- lectura de objetivo ----------------
    def _targets(self, spec: ActionSpec, params: dict) -> tuple[list[Unit], dict | None]:
        if spec.target == "box":
            box = self.source.find_box(params["box_id"])
            return [self.source.get_unit(s) for s in params["serials"]], box
        return [self.source.get_unit(params["serial"])], None

    def _checks(self, spec: ActionSpec, units: list[Unit], box: dict | None, params: dict) -> list[dict]:
        if spec.target == "box":
            lookup = self.source.serial_in_any_box if isinstance(self.source, DemoDataSource) else (lambda s: None)
            raw = packing_checks(box, units, lookup)
            raw.insert(0, _check("Caja abierta", box["status"] == "OPEN", f"Estado: {box['status']}."))
        else:
            raw = spec.precheck(units[0], params) if spec.precheck else []
        return [{"check": n, "ok": ok, "message": m} for n, ok, m in raw]

    # ---------------- PREPARE ----------------
    def prepare(self, action_id: str, raw_params: dict, user: SessionUser) -> dict:
        spec = self._spec(action_id)
        self._ensure_available(spec, user)
        params = self.validate_params(spec, raw_params)
        units, box = self._targets(spec, params)
        checks = self._checks(spec, units, box, params)
        allowed = all(c["ok"] for c in checks)
        versions = {u.serial: u.version for u in units}
        response = {
            "action": spec.describe(self.settings.mode.value, spec.id in self.real_executors),
            "mode": self.settings.mode.value,
            "executor": "SIMULADOR DEMO (memoria, sin conexión a FactoryLogix)" if self.settings.is_demo else "FactoryLogix",
            "params": params,
            "pre_state": [u.summary() for u in units],
            "box": box,
            "validations": checks,
            "allowed": allowed,
            "confirmation_token": None,
            "expires_in": None,
        }
        if allowed:
            response["confirmation_token"] = self._sign({
                "a": spec.id, "u": user.username, "p": self._params_hash(params), "v": versions,
                "exp": time.time() + TOKEN_TTL_SECONDS, "m": self.settings.mode.value,
            })
            response["expires_in"] = TOKEN_TTL_SECONDS
        self.audit.record(category="OPERATION", action=f"{spec.id}.prepare", outcome="READY" if allowed else "BLOCKED",
                          username=user.username, role=user.role.value, target=params.get("serial") or params.get("box_id"),
                          details={"params": params, "validations": checks})
        return response

    # ---------------- EXECUTE ----------------
    def execute(self, action_id: str, raw_params: dict, token: str, idempotency_key: str, confirm: bool,
                user: SessionUser) -> dict:
        spec = self._spec(action_id)
        self._ensure_available(spec, user)
        if confirm is not True:
            raise ValidationFailed("Se requiere confirmación explícita (confirm=true).", code="CONFIRMATION_REQUIRED")
        if not re.match(r"^[A-Za-z0-9\-]{16,64}$", idempotency_key or ""):
            raise ValidationFailed("Clave de idempotencia inválida.", code="INVALID_IDEMPOTENCY_KEY")
        params = self.validate_params(spec, raw_params)
        payload = self._verify(token)
        if (payload["a"] != spec.id or payload["u"] != user.username or payload["p"] != self._params_hash(params)
                or payload["m"] != self.settings.mode.value):
            raise ValidationFailed("La confirmación no corresponde a esta operación.", code="CONFIRMATION_MISMATCH")

        req_hash = self._params_hash({"a": spec.id, "p": params})
        replay = self._idem_begin(idempotency_key, user.username, spec.id, req_hash)
        if replay is not None:
            return {**replay, "replayed": True}
        try:
            result = self._run(spec, params, payload, user)
        except Exception as exc:
            self.db.execute("DELETE FROM idempotency WHERE key=?", (idempotency_key,))
            outcome = exc.code if isinstance(exc, AppError) else "ERROR"
            self.audit.record(category="OPERATION", action=f"{spec.id}.execute", outcome=f"FAILED:{outcome}",
                              username=user.username, role=user.role.value,
                              target=params.get("serial") or params.get("box_id"),
                              details={"params": params, "error": str(exc)})
            raise
        self.db.execute("UPDATE idempotency SET status='DONE', response=? WHERE key=?",
                        (json.dumps(result, default=str), idempotency_key))
        return {**result, "replayed": False}

    def _idem_begin(self, key: str, username: str, action_id: str, req_hash: str) -> dict | None:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM idempotency WHERE key=?", (key,)).fetchone()
            if row:
                if row["username"] != username or row["request_hash"] != req_hash:
                    raise Conflict("La clave de idempotencia ya se usó con otra solicitud.", code="IDEMPOTENCY_MISMATCH")
                if row["status"] != "DONE":
                    raise Conflict("Operación duplicada en curso.", code="DUPLICATE_IN_PROGRESS")
                return json.loads(row["response"])
            conn.execute("INSERT INTO idempotency VALUES (?,?,?,?,?,?,?)",
                         (key, username, action_id, req_hash, "IN_PROGRESS", None,
                          datetime.now(timezone.utc).isoformat()))
        return None

    def _run(self, spec: ActionSpec, params: dict, payload: dict, user: SessionUser) -> dict:
        if not self.settings.is_demo:
            # Nunca alcanzable en v1.0: _ensure_available ya lo impide. Defensa en profundidad.
            raise NotAvailable("Sin ejecutor real registrado.", code="ACTION_NOT_AVAILABLE")
        store = self.source
        if not isinstance(store, DemoDataSource) or not store.synthetic or self.settings.mode.value != "DEMO":
            raise ProductionWriteBlocked("BLOQUEO DE SEGURIDAD: el simulador DEMO sólo opera sobre datos sintéticos en modo DEMO.")
        with store.lock:
            units, box = self._targets(spec, params)
            current = {u.serial: u.version for u in units}
            if current != payload["v"]:
                raise Conflict("El estado cambió desde la preparación (otro usuario u operación). Vuelva a preparar.",
                               code="STATE_CHANGED", details={"expected": payload["v"], "current": current})
            checks = self._checks(spec, units, box, params)
            if not all(c["ok"] for c in checks):
                raise ValidationFailed("La validación del flujo de proceso ya no se cumple.", code="FLOW_VALIDATION_FAILED",
                                       details={"validations": checks})
            before = {u.serial: {"events": len(u.events), "version": u.version, "summary": u.summary()} for u in units}
            if spec.target == "box":
                server = store.sim_pack_box(params["box_id"], units, user.username)
                post = []
                for u in units:
                    post += [("Unidad empacada " + u.serial, u.status == "PACKED", f"Estado: {u.status}.")]
                box_after = store.find_box(params["box_id"])
                post.append(("Seriales en caja", all(u.serial in box_after["serials"] for u in units),
                             f"{len(box_after['serials'])}/{box_after['capacity']}."))
            else:
                u = units[0]
                server = spec.demo_execute(store, u, params, user.username)
                post = spec.postcheck(u, params, before[u.serial]) if spec.postcheck else []
            post_checks = [{"check": n, "ok": ok, "message": m} for n, ok, m in post]
            after = [x.summary() for x in units]
        entry = self.audit.record(
            category="OPERATION", action=f"{spec.id}.execute",
            outcome="SIMULATED_SUCCESS" if all(c["ok"] for c in post_checks) else "SIMULATED_POSTCHECK_FAILED",
            username=user.username, role=user.role.value, target=params.get("serial") or params.get("box_id"),
            details={"params": params, "pre_state": [b["summary"] for b in before.values()], "post_state": after,
                     "server_response": server, "post_checks": post_checks, "simulated": True})
        return {
            "status": "SIMULATED_SUCCESS" if all(c["ok"] for c in post_checks) else "SIMULATED_POSTCHECK_FAILED",
            "simulated": True,
            "mode": self.settings.mode.value,
            "server_response": {"source": "Simulador DEMO (no es una respuesta de FactoryLogix)", "body": server},
            "pre_state": [b["summary"] for b in before.values()],
            "post_state": after,
            "post_checks": post_checks,
            "audit_id": entry["id"],
            "correlation_id": get_correlation_id(),
        }


def validate_packing(source: ProductionDataSource, box_id: str, serials: list[str]) -> dict:
    """Validación en vivo para la pantalla de packing (sin efectos ni token)."""
    box = source.find_box(box_id)
    units, unknown = [], []
    for s in serials:
        try:
            units.append(source.get_unit(s))
        except AppError:
            unknown.append(s)
    lookup = source.serial_in_any_box if isinstance(source, DemoDataSource) else (lambda s: None)
    checks = [{"check": n, "ok": ok, "message": m} for n, ok, m in packing_checks(box, units, lookup)]
    checks.insert(0, {"check": "Caja abierta", "ok": box["status"] == "OPEN", "message": f"Estado: {box['status']}."})
    for s in unknown:
        checks.append({"check": f"Unidad {s}", "ok": False, "message": "Serial no encontrado en la fuente de datos."})
    return {"box": box, "units": [u.summary() for u in units], "unknown": unknown, "validations": checks,
            "ready": bool(serials) and all(c["ok"] for c in checks)}
