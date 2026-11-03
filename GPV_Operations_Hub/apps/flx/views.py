import csv
import io
import json

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.jobs import enqueue
from apps.core.permissions import has_cap, require_cap
from apps.core.utils import json_error, json_ok

from . import catalog, client, discovery, query
from . import status as st
from .models import FlxEntitySet, FlxRun, FlxState


def _base_ctx(request):
    s = FlxState.get()
    schema = discovery.current_schema()
    sets = list(schema.entity_sets.all()) if schema else []
    counts = {}
    for e in sets:
        counts[e.status] = counts.get(e.status, 0) + 1
    present = {e.name for e in sets}
    try:
        base = client.base_url()
    except client.FlxError as e:
        base = f"(configuración inválida: {e})"
    blocked = bool(s.auth_blocked_at and s.auth_fingerprint == client.auth_fingerprint())
    return {"state": s, "schema": schema, "sets": sets, "counts": counts, "base": base, "auth_mode": client.auth_mode(), "auth_blocked": blocked,
            "breaker": client.breaker_state(), "expected": [(cat, [(n, n in present) for n in names]) for cat, names in catalog.EXPECTED.items()],
            "missing": [n for names in catalog.EXPECTED.values() for n in names if schema and n not in present],
            "verified": sum(1 for e in sets if e.status in st.OK_STATES), "unavailable": sum(1 for e in sets if e.status not in st.OK_STATES and e.status != st.NOT_TESTED),
            "forbidden": counts.get(st.FORBIDDEN, 0) + counts.get(st.AUTH_REQUIRED, 0), "explain": st.EXPLAIN,
            "is_admin": has_cap(request.user, "flx.admin"), "can_query": has_cap(request.user, "flx.query"),
            "runs": FlxRun.objects.select_related("user")[:15], "status_overall": _overall(s, blocked)}


def _overall(s, blocked):
    if blocked:
        return st.AUTH_REQUIRED
    if s.last_status == st.CONNECTED and s.last_success_at and (timezone.now() - s.last_success_at).total_seconds() < 3600:
        return st.CONNECTED
    return s.last_status


@require_cap("flx.status")
def center(request):
    ctx = _base_ctx(request)
    ctx["stages"] = request.session.pop("flx_stages", None)
    cat = request.GET.get("categoria", "")
    stf = request.GET.get("estado", "")
    ctx["filtered"] = [e for e in ctx["sets"] if (not cat or e.category == cat) and (not stf or e.status == stf)]
    ctx["categories"] = list(catalog.EXPECTED) + ["Otras (solo en $metadata)"]
    ctx["status_choices"] = sorted(ctx["counts"])
    ctx["sel"] = {"categoria": cat, "estado": stf}
    return render(request, "flx/center.html", ctx)


@require_POST
@require_cap("flx.admin")
def action(request):
    a = request.POST.get("action")
    if a == "test":
        stages, schema = discovery.test_connection(request.user, fetch_schema=request.POST.get("schema") == "1")
        request.session["flx_stages"] = stages
        audit(request.user, "flx.connection_test", None, "Prueba de conexión FactoryLogix: " + (stages[-1]["state"] if stages else "?"))
    elif a == "retry_auth":
        client.clear_auth_block()
        audit(request.user, "flx.retry_auth", None, "Reintento de autenticación habilitado")
        messages.info(request, "Se permite un nuevo intento de autenticación. Ejecute «Probar conexión».")
    elif a == "reset_breaker":
        client.reset_runtime()
        messages.info(request, "Pausa por fallas (circuit breaker) restablecida.")
    elif a == "probe":
        if request.POST.get("confirm") != "1":
            return json_error("Confirme que tiene autorización para el sondeo controlado ($top=1 por conjunto, con pausa entre consultas).")
        names = request.POST.getlist("names") or None
        cat = request.POST.get("categoria")
        schema = discovery.current_schema()
        if cat and schema and not names:
            names = list(schema.entity_sets.filter(category=cat).values_list("name", flat=True))
        audit(request.user, "flx.probe", None, f"Sondeo controlado: {len(names) if names else 'todos los'} conjuntos")
        job, _ = enqueue("flx.probe", {"names": names}, request.user, idempotency_key=request.POST.get("idempotency_key"))
        return json_ok(job_id=str(job.pk))
    elif a == "upload":
        f = request.FILES.get("metadata")
        if not f or f.size > 50 * 1024 * 1024:
            messages.error(request, "Seleccione el archivo XML de $metadata (máx. 50 MB).")
        else:
            try:
                schema = discovery.load_schema_file(f.read(), request.user)
                audit(request.user, "flx.schema_file", None, f"$metadata cargado de archivo ({schema.entity_set_count} EntitySets)")
                messages.success(request, f"Esquema cargado: {schema.entity_set_count} EntitySets. Origen archivo: el acceso NO está verificado.")
            except Exception as e:
                messages.error(request, f"No se pudo leer el archivo: {e}")
    return redirect("flx:center")


@require_cap("flx.status")
def entity(request, name):
    schema = discovery.current_schema()
    if schema is None:
        return redirect("flx:center")
    es = get_object_or_404(FlxEntitySet, schema=schema, name=name)
    return render(request, "flx/entity.html", {"es": es, "props": sorted(es.properties.items()), "explain": st.EXPLAIN,
                                                "is_admin": has_cap(request.user, "flx.admin"), "can_query": has_cap(request.user, "flx.query"),
                                                "ops": query.OPS, "max_top": client.cfg()["MAX_TOP"], "css": st.css(es.status)})


@require_POST
@require_cap("flx.admin")
def entity_action(request, name):
    es = get_object_or_404(FlxEntitySet, schema=discovery.current_schema(), name=name)
    try:
        if request.POST.get("action") == "probe":
            s = discovery.probe_entity(es)
            messages.info(request, f"{es.name}: {s}")
        else:
            caps = discovery.test_capabilities(es, request.user)
            messages.success(request, "Capacidades verificadas: " + ", ".join(f"{k} {'sí' if v else 'no'}" for k, v in caps.items() if not k.startswith("_")))
        audit(request.user, "flx.entity_test", None, f"{es.name}: {request.POST.get('action')}")
    except client.FlxError as e:
        messages.error(request, str(e))
    return redirect("flx:entity", name=es.name)


def _spec_from(data, es):
    spec = query.QuerySpec(entity=es.name)
    spec.select = [p for p in (data.getlist("select") if hasattr(data, "getlist") else data.get("select", [])) if p]
    for i in range(5):
        p, op, v = data.get(f"f{i}_prop"), data.get(f"f{i}_op"), data.get(f"f{i}_value")
        if p and op and v not in (None, ""):
            spec.filters.append((p, op, v))
    if data.get("orderby"):
        spec.orderby = [(data.get("orderby"), data.get("dir") or "asc")]
    try:
        spec.top = int(data.get("top") or 50)
    except ValueError:
        spec.top = 0
    spec.count = data.get("count") == "1"
    return spec


@require_POST
@require_cap("flx.query")
def entity_query(request, name):
    es = get_object_or_404(FlxEntitySet, schema=discovery.current_schema(), name=name)
    spec = _spec_from(request.POST, es)
    try:
        res = query.run(spec, es)
    except query.QueryError as e:
        return json_error(str(e))
    except client.FlxError as e:
        return json_error(f"{e.state}: {e}", status=502, state=e.state)
    audit(request.user, "flx.query", None, f"Consulta {es.name} ({', '.join(res['source']['options'])}): {len(res['rows'])} filas")
    if request.POST.get("format") == "csv":
        buf = io.StringIO()
        cols = list(dict.fromkeys(k for r in res["rows"] for k in r))
        w = csv.writer(buf)
        w.writerow([f"# Fuente: {res['source']['origin']} · {es.name} · consultado {res['source']['fetched_at']}"])
        w.writerow(cols)
        for r in res["rows"]:
            w.writerow([json.dumps(r.get(c), ensure_ascii=False) if isinstance(r.get(c), (dict, list)) else r.get(c) for c in cols])
        resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="flx_{es.name}_{timezone.localtime():%Y%m%d_%H%M}.csv"'
        return resp
    return json_ok(res)


@require_cap("flx.status")
def report(request):
    data = discovery.report()
    resp = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="diagnostico_factorylogix_{timezone.localtime():%Y%m%d_%H%M}.json"'
    return resp


@require_cap("flx.status")
def api_status(request):
    s = FlxState.get()
    schema = discovery.current_schema()
    return json_ok({"status": s.last_status, "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
                    "latency_ms": s.last_latency_ms, "schema_fetched_at": schema.fetched_at.isoformat() if schema else None,
                    "breaker": client.breaker_state()})
