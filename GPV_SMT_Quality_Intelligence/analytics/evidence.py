"""Clasificación de evidencia: confirmada, inferencias y no verificable."""
from __future__ import annotations

from analytics.rework_rules import is_repair

FINAL_RESULT_NOT_VERIFIABLE = "NO_VERIFICABLE"
CLOSURE_DISCLAIMER = ("El cierre de un defecto no constituye por sí mismo evidencia de aprobación final "
                      "de la unidad.")


def classify(identifier: str, smt_rows: list[dict], defects: list[dict], alerts: list[dict],
             sources: dict[str, dict], repair_keywords: list[str]) -> dict:
    confirmed, inferred, unverifiable = [], [], []
    smt_ok = sources["SMT"]["ok"]
    q_ok = sources["Quality"]["ok"]
    qh = sources["QualityHistory"]

    if smt_ok:
        if smt_rows:
            ops: dict[str, int] = {}
            for r in smt_rows:
                ops[r.get("OperationName") or "(sin nombre)"] = ops.get(r.get("OperationName") or "(sin nombre)", 0) + 1
            for op, n in ops.items():
                confirmed.append(f"{n} evento(s) '{op}' registrados en la entidad SMT.")
            repairs = [r for r in smt_rows if is_repair(r.get("OperationName"), repair_keywords)]
            if repairs:
                confirmed.append(f"Reparación registrada: {len(repairs)} evento(s) de reparación.")
        else:
            confirmed.append("La entidad SMT respondió sin eventos para este Identifier.")
    else:
        unverifiable.append(f"Eventos de proceso: la fuente SMT no respondió ({sources['SMT']['status']}).")

    if q_ok:
        if defects:
            for d in defects:
                confirmed.append(f"Defecto único {d.get('description') or ''} ({d.get('comment') or 'sin comentario'}) "
                                 f"DefectID {d['defect_id']} con estado {d.get('status')}.")
                if d.get("closed_at"):
                    confirmed.append(f"Cierre histórico del defecto en {d['closed_at']}"
                                     + (f", operación {d['closed_operation']}" if d.get("closed_operation") else "")
                                     + (f", estación {d['closed_workstation']}" if d.get("closed_workstation") else "")
                                     + (f", operador {d['closed_operator']}" if d.get("closed_operator") else "") + ".")
                if d.get("line_registered"):
                    unverifiable.append(f"Que todas las operaciones ocurrieran en '{d['line_registered']}' "
                                        "(la línea está registrada solo en el defecto).")
        else:
            confirmed.append("Quality respondió sin defectos para este Identifier (no equivale a PASS).")
    else:
        unverifiable.append(f"Defectos: la fuente Quality no respondió ({sources['Quality']['status']}).")

    if qh["status"] not in ("OK", "EMPTY", "NOT_REQUESTED"):
        unverifiable.append(f"Historial de calidad: QualityHistory no respondió ({qh['status']}).")

    for a in alerts:
        if a["category"] in ("POSSIBLE_REWORK", "REPEATED_OPERATION", "TIME_ORDER_REVIEW", "LOOP_NOT_CONFIRMABLE"):
            inferred.append(f"[{a['rule']} · confianza {a['confidence']}] {a['title']}: {a['explanation']}")

    unverifiable.append("Resultado final PASS/FAIL de la unidad: ninguna de las entidades SMT, Quality o "
                        "QualityHistory registra una aprobación final.")
    if defects:
        unverifiable.append("Acción física exacta realizada por el técnico de reparación.")
        unverifiable.append(CLOSURE_DISCLAIMER)
    if any(a["category"] == "REPEATED_OPERATION" for a in alerts):
        unverifiable.append("Que eventos repetidos de una operación correspondan a tarjetas diferentes "
                            "(son del mismo Identifier).")

    return {"final_result": FINAL_RESULT_NOT_VERIFIABLE, "confirmed": confirmed, "inferred": inferred,
            "unverifiable": unverifiable}
