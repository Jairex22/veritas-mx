"""Motor de reglas de reproceso y bucles (auditable).

Cada alerta incluye regla, categoría, confianza, evidencia (referencias a
registros) y lo que NO puede concluirse. Categorías, de menor a mayor certeza
sobre un problema de proceso:

1. DUPLICATE_EVENT      Evento duplicado (misma operación y misma hora exacta).
2. REPEATED_OPERATION   Operación repetida (misma operación en horas distintas).
3. POSSIBLE_REWORK      Posible reproceso (repetición + reparación o defecto).
4. REPAIR_RECORDED      Reparación registrada (operación de reparación observada).
5. CONFIRMED_LOOP       Bucle de proceso confirmado (solo con flujo autorizado configurado).
"""
from __future__ import annotations

from services.timeparse import parse_odata_datetime, sort_key

RULES = {
    "R01": ("DUPLICATE_EVENT", "Evento duplicado",
            "Dos o más eventos con el mismo Identifier, OperationName y EventDate exacto."),
    "R02": ("REPEATED_OPERATION", "Operación repetida",
            "La misma OperationName aparece en momentos distintos para el mismo Identifier."),
    "R03": ("REPAIR_RECORDED", "Reparación registrada",
            "Se observó una operación cuyo nombre coincide con una palabra clave de reparación configurada."),
    "R04": ("POSSIBLE_REWORK", "Posible reproceso",
            "Operación repetida acompañada de una reparación registrada o de un defecto asociado."),
    "R05": ("POST_REPAIR_EVENTS", "Eventos posteriores a reparación",
            "Existen operaciones registradas después de la última reparación."),
    "R06": ("DEFECT_CLOSED", "Defecto cerrado",
            "El defecto tiene estado Closed. No constituye evidencia de aprobación final."),
    "R07": ("CONFIRMED_LOOP", "Bucle de proceso confirmado",
            "La secuencia regresa a un paso anterior del flujo autorizado configurado para el ensamble."),
    "R08": ("LOOP_NOT_CONFIRMABLE", "Bucle no confirmable",
            "Hay repetición de operaciones pero no existe un flujo autorizado configurado para confirmarlo."),
    "R09": ("TIME_ORDER_REVIEW", "Orden temporal a revisar",
            "Un defecto se registró antes del primer evento de su operación de origen; verificar zonas horarias."),
}


def _alert(rule: str, confidence: str, evidence: list[str], explanation: str, cannot_conclude: list[str]) -> dict:
    cat, title, definition = RULES[rule]
    return {"rule": rule, "category": cat, "title": title, "definition": definition, "confidence": confidence,
            "evidence": evidence, "explanation": explanation, "cannot_conclude": cannot_conclude}


def is_repair(op: str | None, keywords: list[str]) -> bool:
    up = (op or "").upper()
    return any(k.upper() in up for k in keywords if k)


def evaluate(identifier: str, smt_rows: list[dict], defects: list[dict], repair_keywords: list[str],
             process_flows: dict[str, list[str]]) -> list[dict]:
    events = sorted(enumerate(smt_rows, start=1),
                    key=lambda p: sort_key(parse_odata_datetime(p[1].get("EventDate"))))
    alerts: list[dict] = []

    # R01 / R02
    by_op: dict[str, list[tuple[int, dict]]] = {}
    for idx, r in events:
        by_op.setdefault(r.get("OperationName") or "(sin nombre)", []).append((idx, r))
    repeated_ops = []
    for op, lst in by_op.items():
        stamps: dict[str, list[int]] = {}
        for idx, r in lst:
            stamps.setdefault(str(r.get("EventDate")), []).append(idx)
        for ts, idxs in stamps.items():
            if len(idxs) > 1:
                alerts.append(_alert("R01", "alta", [f"SMT#{i}" for i in idxs],
                                     f"'{op}' registrada {len(idxs)} veces con EventDate {ts}.",
                                     ["Si corresponde a dos pasos físicos o a un registro duplicado en el MES."]))
        if len(stamps) > 1:
            repeated_ops.append(op)
            alerts.append(_alert("R02", "alta", [f"SMT#{i}" for i, _ in lst],
                                 f"'{op}' aparece {len(stamps)} veces en momentos distintos.",
                                 ["Que se trate de tarjetas distintas (es el mismo Identifier).",
                                  "Que la repetición sea un bucle de proceso real.",
                                  "La causa de la repetición."]))

    # R03 / R05
    repairs = [(idx, r) for idx, r in events if is_repair(r.get("OperationName"), repair_keywords)]
    if repairs:
        alerts.append(_alert("R03", "alta", [f"SMT#{i}" for i, _ in repairs],
                             f"{len(repairs)} evento(s) de reparación: " +
                             ", ".join(sorted({r.get('OperationName') for _, r in repairs})),
                             ["La acción física exacta realizada por el técnico.",
                              "Que la reparación haya sido exitosa."]))
        last_repair_dt = parse_odata_datetime(repairs[-1][1].get("EventDate"))
        after = [(i, r) for i, r in events
                 if last_repair_dt and (parse_odata_datetime(r.get("EventDate")) or last_repair_dt) > last_repair_dt]
        if after:
            alerts.append(_alert("R05", "alta", [f"SMT#{i}" for i, _ in after],
                                 "Operaciones después de la última reparación: " +
                                 ", ".join(r.get("OperationName") or "?" for _, r in after),
                                 ["Que estas operaciones hayan resultado en aprobación (PASS)."]))

    # R04
    if repeated_ops and (repairs or defects):
        reasons = []
        if repairs:
            reasons.append("reparación registrada")
        if defects:
            reasons.append(f"{len(defects)} defecto(s) único(s) asociado(s)")
        ev = [f"SMT#{i}" for op in repeated_ops for i, _ in by_op[op]] + [f"DEF:{d['defect_id']}" for d in defects]
        alerts.append(_alert("R04", "media", ev,
                             f"Operación(es) repetida(s) {', '.join(repeated_ops)} con " + " y ".join(reasons) + ".",
                             ["Que el reproceso esté confirmado: requiere el registro de la acción física.",
                              "Que la unidad haya sido aprobada al final."]))

    # R06
    for d in defects:
        if (d.get("status") or "").lower() == "closed":
            ev = [f"DEF:{d['defect_id']}"] + ([f"Cierre {d['closed_at']}"] if d.get("closed_at") else [])
            alerts.append(_alert("R06", "alta", ev,
                                 f"Defecto {d.get('description') or d['defect_id']} con estado Closed"
                                 + (f" (cierre registrado en {d['closed_operation']})" if d.get("closed_operation") else "")
                                 + ".",
                                 ["Que la PCBA esté aprobada o sea buena.", "La acción física realizada."]))

    # R07 / R08
    assembly = next((r.get("Assembly") for _, r in events if r.get("Assembly")), None)
    flow = process_flows.get(assembly or "", [])
    if flow:
        pos = {op: i for i, op in enumerate(flow)}
        max_pos, back = -1, []
        for idx, r in events:
            p = pos.get(r.get("OperationName"))
            if p is None:
                continue
            if p < max_pos:
                back.append(idx)
            max_pos = max(max_pos, p)
        if back:
            alerts.append(_alert("R07", "alta", [f"SMT#{i}" for i in back],
                                 f"La secuencia regresa a un paso anterior del flujo autorizado de {assembly}.",
                                 ["La causa raíz del bucle."]))
    elif repeated_ops:
        alerts.append(_alert("R08", "n/a", [],
                             f"No hay flujo autorizado configurado para el ensamble {assembly or '(desconocido)'}; "
                             "un bucle real no puede confirmarse solo por repetición de operaciones.",
                             ["Que exista un bucle de proceso real."]))

    # R09
    for d in defects:
        created = parse_odata_datetime(d.get("date_created"))
        src = d.get("source_operation")
        src_times = [parse_odata_datetime(r.get("EventDate")) for _, r in events if r.get("OperationName") == src]
        src_times = [t for t in src_times if t and t.tzinfo]
        if created and created.tzinfo and src_times and created < min(src_times):
            alerts.append(_alert("R09", "baja", [f"DEF:{d['defect_id']}"],
                                 f"DateCreated {d.get('date_created')} es anterior al primer evento '{src}' "
                                 f"({min(src_times).isoformat()}).",
                                 ["Si la diferencia se debe a zona horaria, reloj del equipo o a un evento previo "
                                  "no registrado en SMT."]))
    return alerts
