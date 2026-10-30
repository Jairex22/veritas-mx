"""Label Control: impresoras, plantillas, previsualización e impresión.

Separado de las transacciones de producción: imprimir una etiqueta nunca
modifica el estado de una unidad.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..connectors.factorylogix import load_json_config, tcp_reachable
from ..core.context import get_correlation_id
from ..core.db import Database
from ..core.errors import Forbidden, NotAvailable, NotFound, ValidationFailed
from ..core.security import SessionUser, has_permission
from ..settings import Settings
from .audit import AuditService

DEMO_PRINTERS = [
    {"id": "DEMO-ZEBRA-PACK-01", "name": "Zebra ZT411 – Empaque (DEMO)", "vendor": "Zebra", "language": "ZPL",
     "area": "EMPAQUE", "simulated": True, "simulated_state": "READY"},
    {"id": "DEMO-CAB-SMT-01", "name": "CAB SQUIX 4 – SMT (DEMO)", "vendor": "CAB", "language": "JScript",
     "area": "SMT", "simulated": True, "simulated_state": "READY"},
    {"id": "DEMO-ZEBRA-FT-02", "name": "Zebra ZT230 – Prueba final (DEMO)", "vendor": "Zebra", "language": "ZPL",
     "area": "PRUEBAS", "simulated": True, "simulated_state": "OFFLINE"},
]

DEFAULT_TEMPLATES = [
    {
        "id": "unit-serial-2x1", "name": "Serial de unidad 2\"x1\"", "language": "ZPL", "width_dots": 406, "height_dots": 203,
        "fields": [
            {"name": "serial", "label": "Serial", "pattern": r"^[A-Za-z0-9._\-/]{3,64}$", "required": True},
            {"name": "assembly", "label": "Ensamble", "pattern": r"^[A-Za-z0-9._\-]{1,40}$", "required": True},
            {"name": "revision", "label": "Revisión", "pattern": r"^[A-Za-z0-9]{1,4}$", "required": True},
        ],
        "body": "^XA^CI28^FO20,20^A0N,28,28^FD{{assembly}} REV {{revision}}^FS^FO20,60^BCN,80,Y,N,N^FD{{serial}}^FS^XZ",
        "layout": [
            {"type": "text", "x": 20, "y": 20, "size": 28, "value": "{{assembly}} REV {{revision}}"},
            {"type": "barcode", "x": 20, "y": 60, "height": 80, "value": "{{serial}}"},
        ],
    },
    {
        "id": "box-label-4x3", "name": "Etiqueta de caja 4\"x3\"", "language": "ZPL", "width_dots": 812, "height_dots": 609,
        "fields": [
            {"name": "box_id", "label": "Caja", "pattern": r"^[A-Za-z0-9\-]{3,40}$", "required": True},
            {"name": "assembly", "label": "Ensamble", "pattern": r"^[A-Za-z0-9._\-]{1,40}$", "required": True},
            {"name": "revision", "label": "Revisión", "pattern": r"^[A-Za-z0-9]{1,4}$", "required": True},
            {"name": "quantity", "label": "Cantidad", "pattern": r"^[0-9]{1,4}$", "required": True},
            {"name": "work_order", "label": "Orden", "pattern": r"^[A-Za-z0-9\-]{3,40}$", "required": True},
        ],
        "body": "^XA^CI28^FO30,30^A0N,40,40^FDGPV AMERICAS^FS^FO30,90^A0N,30,30^FD{{assembly}} REV {{revision}}^FS"
                "^FO30,140^A0N,30,30^FDQTY {{quantity}}  WO {{work_order}}^FS^FO30,200^BCN,120,Y,N,N^FD{{box_id}}^FS^XZ",
        "layout": [
            {"type": "text", "x": 30, "y": 30, "size": 40, "value": "GPV AMERICAS"},
            {"type": "text", "x": 30, "y": 90, "size": 30, "value": "{{assembly}} REV {{revision}}"},
            {"type": "text", "x": 30, "y": 140, "size": 30, "value": "QTY {{quantity}}  WO {{work_order}}"},
            {"type": "barcode", "x": 30, "y": 200, "height": 120, "value": "{{box_id}}"},
        ],
    },
    {
        "id": "bartender-packing", "name": "Plantilla BarTender de empaque", "language": "BTW", "width_dots": 812,
        "height_dots": 609, "fields": [], "body": "", "layout": [],
        "unavailable_reason": "NO DISPONIBLE: requiere BarTender Integration Builder / REST API configurado y aprobado por TI.",
    },
]

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def zpl_escape(value: str) -> str:
    """Evita inyección de comandos ZPL eliminando prefijos de comando."""
    return value.replace("^", "").replace("~", "")


class LabelService:
    def __init__(self, settings: Settings, db: Database, audit: AuditService):
        self.settings = settings
        self.db = db
        self.audit = audit

    def printers(self) -> list[dict]:
        configured = load_json_config(self.settings.config_dir, "printers.json") or []
        real = [dict(p, simulated=False) for p in configured if isinstance(p, dict) and p.get("id")]
        return (DEMO_PRINTERS + real) if self.settings.is_demo else real

    def _printer(self, pid: str) -> dict:
        for p in self.printers():
            if p["id"] == pid:
                return p
        raise NotFound(f"Impresora '{pid}' no autorizada o inexistente.")

    def templates(self) -> list[dict]:
        extra = load_json_config(self.settings.config_dir, "label_templates.json") or []
        return DEFAULT_TEMPLATES + [t for t in extra if isinstance(t, dict) and t.get("id")]

    def _template(self, tid: str) -> dict:
        for t in self.templates():
            if t["id"] == tid:
                return t
        raise NotFound(f"Plantilla '{tid}' no encontrada.")

    def check_printer(self, pid: str) -> dict:
        p = self._printer(pid)
        if p.get("simulated"):
            state = p.get("simulated_state", "READY")
            return {"printer_id": pid, "simulated": True, "state": state,
                    "message": "Estado simulado (DEMO)." if state == "READY" else "Simulación DEMO: impresora sin comunicación."}
        host, port = p.get("host"), int(p.get("port", 9100))
        if not host:
            return {"printer_id": pid, "simulated": False, "state": "NOT_CONFIGURED", "message": "Host no configurado."}
        ok, msg = tcp_reachable(host, port)
        return {"printer_id": pid, "simulated": False, "state": "REACHABLE" if ok else "UNREACHABLE",
                "message": msg + (" Nota: accesible no significa lista para imprimir (consulta ~HS no implementada en v1.0)."
                                  if ok else "")}

    def preview(self, tid: str, data: dict[str, Any]) -> dict:
        t = self._template(tid)
        if t.get("unavailable_reason"):
            raise NotAvailable(t["unavailable_reason"], code="TEMPLATE_NOT_AVAILABLE")
        errors, clean = {}, {}
        for f in t["fields"]:
            v = str(data.get(f["name"], "") or "").strip()
            if not v and f.get("required"):
                errors[f["name"]] = "Requerido."
            elif v and f.get("pattern") and not re.match(f["pattern"], v):
                errors[f["name"]] = "Formato inválido."
            clean[f["name"]] = zpl_escape(v)
        if errors:
            raise ValidationFailed("Datos de etiqueta inválidos.", details={"fields": errors})
        render = lambda s: _PLACEHOLDER.sub(lambda m: clean.get(m.group(1), ""), s)  # noqa: E731
        return {"template": {k: t[k] for k in ("id", "name", "language", "width_dots", "height_dots")},
                "data": clean, "zpl": render(t["body"]),
                "layout": [dict(el, value=render(el["value"])) for el in t["layout"]],
                "note": "Previsualización esquemática generada por la aplicación; no es el render del firmware de la impresora."}

    def is_reprint(self, tid: str, key: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM print_jobs WHERE template_id=? AND serial=? AND outcome LIKE '%SUCCESS%'",
                                  (tid, key)))

    def print(self, pid: str, tid: str, data: dict, reason: str, user: SessionUser) -> dict:
        user.require("labels.print")
        printer = self._printer(pid)
        prev = self.preview(tid, data)
        key = prev["data"].get("serial") or prev["data"].get("box_id") or ""
        reprint = self.is_reprint(tid, key)
        if reprint:
            if not has_permission(user.role, "labels.reprint"):
                self._job(user, pid, tid, key, True, reason, "DENIED", "Reimpresión sin permiso.")
                self.audit.record(category="PRINT", action="label.reprint", outcome="DENIED", username=user.username,
                                  role=user.role.value, target=key, details={"printer": pid, "template": tid})
                raise Forbidden("La reimpresión requiere rol de Calidad o Administrador.", code="REPRINT_NOT_ALLOWED")
            if len((reason or "").strip()) < 10:
                raise ValidationFailed("La reimpresión requiere una justificación (mín. 10 caracteres).")
        if not printer.get("simulated"):
            raise NotAvailable("NO DISPONIBLE: la impresión real no está habilitada en v1.0. Requiere validación de "
                               "impresoras autorizadas, prueba en ambiente controlado y aprobación.",
                               code="REAL_PRINT_NOT_AVAILABLE")
        if printer.get("simulated_state") != "READY":
            outcome, msg = "SIMULATED_FAILED", "Fallo de comunicación con la impresora (simulación DEMO)."
        else:
            outcome, msg = "SIMULATED_SUCCESS", "Trabajo enviado al spooler simulado (DEMO). No se imprimió físicamente."
        job_id = self._job(user, pid, tid, key, reprint, reason, outcome, msg)
        self.audit.record(category="PRINT", action="label.reprint" if reprint else "label.print", outcome=outcome,
                          username=user.username, role=user.role.value, target=key,
                          details={"printer": pid, "template": tid, "job_id": job_id, "reason": reason})
        return {"job_id": job_id, "outcome": outcome, "message": msg, "reprint": reprint, "simulated": True,
                "zpl": prev["zpl"]}

    def _job(self, user: SessionUser, pid: str, tid: str, key: str, reprint: bool, reason: str, outcome: str, msg: str) -> int:
        cur = self.db.execute(
            "INSERT INTO print_jobs (ts, username, printer_id, template_id, serial, is_reprint, reason, mode, outcome,"
            " message, correlation_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), user.username, pid, tid, key, int(reprint),
             reason, self.settings.mode.value, outcome, msg, get_correlation_id()))
        return cur.lastrowid

    def jobs(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM print_jobs ORDER BY id DESC LIMIT ?", (limit,))]
