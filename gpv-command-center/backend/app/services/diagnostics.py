"""Motor inteligente de diagnóstico de rework.

Cada hallazgo separa:
  - facts: hechos CONFIRMADOS, cada uno con referencias a eventos de la fuente.
  - hypotheses: POSIBLES causas, explícitamente marcadas como hipótesis.
El motor nunca declara un defecto resuelto sin evidencia (reparación + re-prueba PASS).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..data.models import REPAIR_STATIONS, Event, Unit

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@dataclass
class Fact:
    statement: str
    evidence: list[str] = field(default_factory=list)  # IDs de eventos/defectos/reparaciones


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: str
    serials: list[str]
    facts: list[Fact]
    hypotheses: list[str]
    confidence: float
    confidence_basis: str
    actions: list[str]
    intervention_risk: str
    risk_level: str
    history: list[dict[str, Any]]
    work_order: str = ""
    panel_id: str | None = None
    station: str | None = None

    @property
    def id(self) -> str:
        return f"{self.rule_id}:{self.panel_id or ','.join(self.serials)}"

    def to_dict(self) -> dict[str, Any]:
        level = "ALTA" if self.confidence >= 0.8 else "MEDIA" if self.confidence >= 0.5 else "BAJA"
        return {
            "id": self.id, "rule_id": self.rule_id, "title": self.title, "severity": self.severity,
            "serials": self.serials, "work_order": self.work_order, "panel_id": self.panel_id, "station": self.station,
            "facts": [{"statement": f.statement, "evidence": f.evidence, "kind": "HECHO_CONFIRMADO"} for f in self.facts],
            "hypotheses": [{"statement": h, "kind": "HIPOTESIS"} for h in self.hypotheses],
            "confidence": {"score": round(self.confidence, 2), "level": level, "basis": self.confidence_basis},
            "recommended_actions": self.actions,
            "intervention_risk": {"level": self.risk_level, "description": self.intervention_risk},
            "history": self.history,
        }


def _hist(events: list[Event], limit: int = 25) -> list[dict]:
    return [e.to_dict() for e in events[-limit:]]


def _hours(delta) -> float:
    return round(delta.total_seconds() / 3600, 1)


class DiagnosticsEngine:
    STUCK_REPAIR_HOURS = 8.0
    DEPANEL_WAIT_HOURS = 4.0
    LOOP_MIN_CYCLES = 2
    REPEAT_MIN_VISITS = 3

    RULES = {
        "FCT_DEBUG_LOOP": "Bucle entre FCT y Debug",
        "STUCK_IN_REPAIR": "Serial atrapado en reparación",
        "REPEATED_STATION": "Retorno repetido a una estación",
        "INCONSISTENT_STATE": "Estado inconsistente entre operaciones",
        "RESOLVED_WITH_HOLD": "Defecto resuelto con bloqueo pendiente",
        "UNVERIFIED_RESOLUTION": "Defecto declarado resuelto sin evidencia",
        "MIXED_PANEL": "Panel con unidades PASS y FAIL",
        "BLOCKED_BEFORE_DEPANEL": "Producto bloqueado antes de Depanel",
    }

    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    def analyze(self, units: list[Unit]) -> list[Finding]:
        findings: list[Finding] = []
        loop_flagged: set[tuple[str, str]] = set()
        for u in units:
            f = self._loop(u)
            if f:
                findings.append(f)
                loop_flagged.add((u.serial, f.station or ""))
            for rule in (self._stuck, self._inconsistent, self._resolved_with_hold, self._unverified_resolution):
                f = rule(u)
                if f:
                    findings.append(f)
            findings.extend(self._repeated(u, loop_flagged))
        panels: dict[str, list[Unit]] = defaultdict(list)
        for u in units:
            if u.panel_id:
                panels[u.panel_id].append(u)
        for pid, members in panels.items():
            findings.extend(self._panel_rules(pid, members))
        findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), -f.confidence, f.id))
        return findings

    # ------------------------------------------------------------------
    def _loop(self, u: Unit) -> Finding | None:
        ev = u.sorted_events
        fct_fails = [e for e in ev if e.station == "FCT" and e.operation == "TEST" and e.result == "FAIL"]
        cycles = 0
        evidence = []
        for i, e in enumerate(fct_fails):
            nxt = next((x for x in ev if x.ts >= e.ts and x.station in REPAIR_STATIONS), None)
            if nxt:
                cycles += 1
                evidence += [e.id, nxt.id]
        if cycles < self.LOOP_MIN_CYCLES:
            return None
        repairs = [r for r in u.repairs]
        codes = sorted({d.code for d in u.defects if d.station == "FCT"})
        same_code = len(codes) == 1
        facts = [
            Fact(f"{len(fct_fails)} resultados FAIL en FCT, cada uno seguido de ingreso a Debug ({cycles} ciclos).", evidence),
            Fact(f"{len(repairs)} reparación(es) registradas: " + "; ".join(r.action for r in repairs) if repairs
                 else "No hay reparaciones registradas entre fallas.", [r.id for r in repairs]),
            Fact(f"Código(s) de defecto en FCT: {', '.join(codes) or 'ninguno registrado'}.",
                 [d.id for d in u.defects if d.station == "FCT"]),
        ]
        if u.current_station == "DEBUG":
            facts.append(Fact("La unidad se encuentra actualmente en DEBUG según el estado reportado.", []))
        hyps = [
            "La causa raíz no ha sido corregida: las reparaciones atienden síntomas (mismo código de defecto recurrente)." if same_code
            else "Defectos distintos en cada ciclo: posible daño colateral por retrabajo o falla intermitente.",
            "Posible falso FAIL por fixture/accesorio de prueba FCT o límites de prueba mal ajustados.",
            "Posible componente de lote defectuoso (verificar trazabilidad de componentes asociados).",
        ]
        conf = min(0.95, 0.6 + 0.15 * cycles)
        return Finding("FCT_DEBUG_LOOP", self.RULES["FCT_DEBUG_LOOP"], "HIGH" if cycles >= 3 else "MEDIUM", [u.serial],
                       facts, hyps, conf, f"Basado en {cycles} ciclos FCT→Debug observados en el historial.",
                       ["Escalar a Ingeniería de Pruebas antes de un nuevo retrabajo.",
                        "Verificar fixture FCT con una unidad dorada (golden unit).",
                        "Revisar log detallado de la prueba FCT y comparar mediciones entre ciclos.",
                        "Revisar lotes de componentes asociados al ref. designador reparado."],
                       "Cada retrabajo adicional aumenta el riesgo de daño térmico a la PCB. No retrabajar sin análisis.",
                       "ALTO", _hist(ev), u.work_order, u.panel_id, "FCT")

    def _stuck(self, u: Unit) -> Finding | None:
        if u.current_station not in REPAIR_STATIONS and u.status != "IN_REPAIR":
            return None
        ev = u.sorted_events
        entry = next((e for e in reversed(ev) if e.station in REPAIR_STATIONS and e.operation == "START"), None)
        if not entry:
            return None
        after = [e for e in ev if e.ts > entry.ts]
        hours = _hours(self._now() - entry.ts)
        if hours < self.STUCK_REPAIR_HOURS or any(e.operation == "REPAIR" for e in after):
            return None
        open_d = u.open_defects
        facts = [Fact(f"Ingreso a {entry.station} hace {hours} h sin reparación registrada posterior.", [entry.id]),
                 Fact(f"{len(open_d)} defecto(s) abierto(s): " + ", ".join(f"{d.code} ({d.station})" for d in open_d)
                      if open_d else "Sin defectos abiertos registrados.", [d.id for d in open_d])]
        return Finding("STUCK_IN_REPAIR", self.RULES["STUCK_IN_REPAIR"], "HIGH" if hours >= 24 else "MEDIUM", [u.serial],
                       facts, ["Unidad físicamente extraviada o en espera de material/componente.",
                               "Reparación realizada pero no registrada en el MES.",
                               "Falta de capacidad del técnico de Debug en el turno."],
                       0.9, f"Tiempo en reparación ({hours} h) supera el umbral de {self.STUCK_REPAIR_HOURS} h; hecho medido.",
                       ["Localizar físicamente la unidad en el área de reparación.",
                        "Confirmar con el técnico si existe reparación no registrada.",
                        "Registrar la reparación real o escalar a Ingeniería si requiere análisis."],
                       "Bajo para la consulta; registrar una reparación no realizada falsearía la trazabilidad.",
                       "BAJO", _hist(ev), u.work_order, u.panel_id, entry.station)

    def _repeated(self, u: Unit, loop_flagged: set[tuple[str, str]]) -> list[Finding]:
        out = []
        ev = u.sorted_events
        visits: dict[str, list[Event]] = defaultdict(list)
        for e in ev:
            if e.operation == "START" and e.station not in REPAIR_STATIONS:
                visits[e.station].append(e)
        for st, starts in visits.items():
            if len(starts) < self.REPEAT_MIN_VISITS or (u.serial, st) in loop_flagged:
                continue
            fails = [e for e in ev if e.station == st and e.operation == "TEST" and e.result == "FAIL"]
            out.append(Finding("REPEATED_STATION", self.RULES["REPEATED_STATION"], "MEDIUM", [u.serial],
                               [Fact(f"La unidad ingresó {len(starts)} veces a {st}.", [e.id for e in starts]),
                                Fact(f"{len(fails)} resultado(s) FAIL en {st}.", [e.id for e in fails])],
                               ["Falla intermitente no aislada por el diagnóstico de reparación.",
                                "Reparación incompleta o incorrecta en ciclos previos."],
                               0.85, "Conteo directo de ingresos a estación en el historial.",
                               ["Revisar el historial de reparaciones y síntomas antes del siguiente ingreso.",
                                "Considerar análisis de causa raíz (8D) si el patrón se repite en el lote."],
                               "Moderado: ciclos adicionales de prueba/retrabajo consumen capacidad y pueden degradar la unidad.",
                               "MEDIO", _hist(ev), u.work_order, u.panel_id, st))
        return out

    def _inconsistent(self, u: Unit) -> Finding | None:
        ev = u.sorted_events
        facts: list[Fact] = []
        tests = [e for e in ev if e.operation == "TEST"]
        if u.status in ("PACKED", "COMPLETE"):
            last_ft = next((e for e in reversed(tests) if e.station == "FINAL_TEST"), None)
            if last_ft and last_ft.result == "FAIL":
                facts.append(Fact(f"Estado reportado {u.status}, pero la última prueba FINAL_TEST es FAIL.", [last_ft.id]))
            if u.status == "PACKED" and not any(e.operation == "PACK" for e in ev):
                facts.append(Fact("Estado reportado PACKED sin evento PACK en el historial.", []))
        if u.route and u.current_station in u.route and not u.route_inferred:
            idx = u.route.index(u.current_station)
            passed = {e.station for e in ev if e.result == "PASS" and e.operation in ("TEST", "COMPLETE", "PACK")}
            skipped = [st for st in u.route[:idx] if st not in passed]
            if skipped:
                facts.append(Fact(f"Estación actual reportada {u.current_station}, pero no hay PASS registrado en: "
                                  f"{', '.join(skipped)}.", []))
        if u.reported_last_completed and u.reported_last_completed != u.last_completed_station:
            facts.append(Fact(f"Último completado reportado {u.reported_last_completed}; el historial indica "
                              f"{u.last_completed_station or 'ninguno'}.", []))
        if not facts:
            return None
        return Finding("INCONSISTENT_STATE", self.RULES["INCONSISTENT_STATE"], "CRITICAL", [u.serial], facts,
                       ["Transacción registrada fuera de flujo (p.ej. cambio manual de estado o Change Product).",
                        "Historial incompleto en la fuente consultada (eventos no replicados u OData filtrado).",
                        "Error de sincronización entre estaciones."],
                       0.75, "Contradicción directa entre estado reportado e historial; la causa es hipotética.",
                       ["Retener físicamente la unidad (contención) hasta aclarar el estado.",
                        "Validar el historial directamente en FactoryLogix con el administrador del sistema.",
                        "NO forzar el estado: corregir mediante el flujo de proceso oficial."],
                       "Alto: una unidad con prueba FAIL podría llegar al cliente.", "ALTO", _hist(ev),
                       u.work_order, u.panel_id, u.current_station)

    def _resolved_with_hold(self, u: Unit) -> Finding | None:
        if u.status != "HOLD" or not u.defects or u.open_defects:
            return None
        ev = u.sorted_events
        hold = next((e for e in reversed(ev) if e.operation == "HOLD"), None)
        if hold is None:
            return None
        released = any(e.operation == "RELEASE" and e.ts > hold.ts for e in ev)
        if released:
            return None
        verified = [d for d in u.defects if d.status == "VERIFIED"]
        hours = _hours(self._now() - hold.ts)
        return Finding("RESOLVED_WITH_HOLD", self.RULES["RESOLVED_WITH_HOLD"], "MEDIUM", [u.serial],
                       [Fact(f"Todos los defectos ({len(u.defects)}) están cerrados; {len(verified)} verificados con re-prueba.",
                             [d.id for d in u.defects] + [d.repair_id for d in u.defects if d.repair_id]),
                        Fact(f"HOLD activo desde hace {hours} h en {hold.station}: \"{hold.details}\".", [hold.id])],
                       ["El HOLD corresponde a una contención independiente del defecto (lote, auditoría, desviación).",
                        "Se omitió la liberación tras la verificación del defecto."],
                       0.8, "Hechos medidos; la relación entre HOLD y defecto es hipotética.",
                       ["Confirmar con Calidad el motivo del HOLD antes de liberar.",
                        "Liberar sólo mediante la transacción oficial y con rol de Calidad."],
                       "Medio: liberar una contención activa sin autorización puede dejar pasar producto sospechoso.",
                       "MEDIO", _hist(ev), u.work_order, u.panel_id, hold.station)

    def _unverified_resolution(self, u: Unit) -> Finding | None:
        ev = u.sorted_events
        issues = []
        for d in u.defects:
            if d.status not in ("REPAIRED", "VERIFIED"):
                continue
            repair = next((r for r in u.repairs if r.id == d.repair_id), None) if d.repair_id else None
            retest = next((e for e in ev if e.station == d.station and e.operation == "TEST" and e.result == "PASS"
                           and e.ts > d.ts), None)
            missing = []
            if repair is None:
                missing.append("reparación registrada")
            if d.status == "VERIFIED" and retest is None:
                missing.append(f"re-prueba PASS en {d.station}")
            if missing:
                issues.append((d, missing))
        if not issues:
            return None
        facts = [Fact(f"Defecto {d.id} ({d.code}) en estado {d.status} sin: {', '.join(m)}.", [d.id]) for d, m in issues]
        return Finding("UNVERIFIED_RESOLUTION", self.RULES["UNVERIFIED_RESOLUTION"], "HIGH", [u.serial], facts,
                       ["Cierre administrativo del defecto sin reparación física.",
                        "Reparación/re-prueba realizada pero no registrada en el MES."],
                       0.85, "Ausencia verificable de registros de reparación/re-prueba en la fuente consultada.",
                       ["Tratar el defecto como NO resuelto hasta contar con evidencia.",
                        "Enviar la unidad a re-prueba en la estación donde se detectó el defecto."],
                       "Alto: el defecto podría persistir en producto liberado.", "ALTO", _hist(ev),
                       u.work_order, u.panel_id, issues[0][0].station)

    def _panel_rules(self, panel_id: str, members: list[Unit]) -> list[Finding]:
        out = []
        latest: dict[str, Event] = {}
        for u in members:
            panel_tests = [e for e in u.sorted_events if e.operation == "TEST" and e.station in ("AOI", "ICT")]
            if panel_tests:
                latest[u.serial] = panel_tests[-1]
        passes = [s for s, e in latest.items() if e.result == "PASS"]
        fails = [s for s, e in latest.items() if e.result == "FAIL"]
        depaneled = any(any(e.station == "DEPANEL" and e.result == "PASS" for e in u.events) for u in members)
        wo = members[0].work_order
        if passes and fails and not depaneled:
            out.append(Finding("MIXED_PANEL", self.RULES["MIXED_PANEL"], "HIGH", sorted(passes + fails),
                               [Fact(f"Panel {panel_id}: {len(passes)} unidad(es) PASS y {len(fails)} FAIL en la última prueba de panel.",
                                     [latest[s].id for s in passes + fails]),
                                Fact("Unidades FAIL: " + ", ".join(fails), [latest[s].id for s in fails])],
                               ["Defecto localizado en una posición del panel (p.ej. pasta, colocación).",
                                "Si se repite la misma posición en varios paneles: posible problema de stencil o programa."],
                               0.9, "Resultados de prueba por unidad dentro del mismo panel.",
                               ["Reparar o disponer las unidades FAIL antes de separar el panel.",
                                "Si el proceso lo permite, marcar la posición como mala (bad mark) mediante el flujo oficial.",
                                "Revisar si la misma posición falla en otros paneles del lote."],
                               "Medio: separar el panel sin resolver la posición FAIL puede mezclar unidades no conformes.",
                               "MEDIO", [latest[s].to_dict() for s in passes + fails], wo, panel_id, "ICT"))
        waiting = [u for u in members if u.current_station == "DEPANEL" and u.status == "IN_PROCESS"]
        if waiting and not depaneled:
            last_ts = max((e.ts for u in waiting for e in u.events if e.result == "PASS"), default=None)
            hours = _hours(self._now() - last_ts) if last_ts else 0
            blockers = [u for u in members if u not in waiting]
            if hours >= self.DEPANEL_WAIT_HOURS and blockers:
                out.append(Finding("BLOCKED_BEFORE_DEPANEL", self.RULES["BLOCKED_BEFORE_DEPANEL"], "HIGH",
                                   sorted(u.serial for u in members),
                                   [Fact(f"{len(waiting)} unidad(es) esperan DEPANEL desde hace {hours} h.",
                                         [u.serial for u in waiting]),
                                    Fact("Unidades del panel que no están listas: " +
                                         ", ".join(f"{u.serial} ({u.status} en {u.current_station})" for u in blockers),
                                         [u.serial for u in blockers])],
                                   ["El panel no puede separarse mientras una unidad siga en reparación.",
                                    "La regla de proceso exige panel completo para DEPANEL."],
                                   0.85, f"Tiempo de espera medido supera el umbral de {self.DEPANEL_WAIT_HOURS} h.",
                                   ["Priorizar la reparación de la(s) unidad(es) bloqueante(s).",
                                    "Consultar con Ingeniería de Proceso el procedimiento oficial para posiciones irreparables."],
                                   "Medio: el WIP detenido afecta la entrega de la orden.", "MEDIO",
                                   [], wo, panel_id, "DEPANEL"))
        return out

