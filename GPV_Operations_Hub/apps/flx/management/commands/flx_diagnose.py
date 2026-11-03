"""Diagnóstico de FactoryLogix desde un equipo autorizado de la red de GPV.

  .venv\\Scripts\\python.exe manage.py flx_diagnose
  .venv\\Scripts\\python.exe manage.py flx_diagnose --sondear --confirmar-sondeo
  .venv\\Scripts\\python.exe manage.py flx_diagnose --sondear --confirmar-sondeo --entidades WIP,Quality

Sin --sondear: configuración, métodos de autenticación ofrecidos, documento de servicio y $metadata.
Con --sondear: además una consulta GET $top=1 por EntitySet, en serie y con pausa (requiere
--confirmar-sondeo: hágalo solo con autorización del administrador MES).
El reporte (JSON + Markdown) contiene estructura y estados; NO contiene valores de registros,
credenciales ni encabezados de autorización.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.flx import discovery


class Command(BaseCommand):
    help = "Diagnóstico de conexión y esquema de FactoryLogix (OData, solo lectura)."

    def add_arguments(self, parser):
        parser.add_argument("--sondear", action="store_true", help="Consulta $top=1 a cada EntitySet (sondeo controlado).")
        parser.add_argument("--confirmar-sondeo", action="store_true", help="Confirma que el sondeo está autorizado.")
        parser.add_argument("--entidades", default="", help="Lista separada por comas para limitar el sondeo.")
        parser.add_argument("--retardo-ms", type=int, default=None, help="Pausa entre consultas del sondeo (por omisión GPV_FLX_PROBE_DELAY_MS).")
        parser.add_argument("--salida", default="", help="Carpeta del reporte (por omisión data\\diagnosticos).")
        parser.add_argument("--detalle", action="store_true", help="Muestra cada solicitud HTTP (ruta, estado, ms) en la consola.")

    def handle(self, *args, **o):
        if o["sondear"] and not o["confirmar_sondeo"]:
            raise CommandError("El sondeo consulta cada EntitySet. Agregue --confirmar-sondeo solo si está autorizado por el administrador MES.")
        import logging

        if not o["detalle"]:
            logging.getLogger("gpv.flx").setLevel(logging.WARNING)
        self.stdout.write("== FactoryLogix · diagnóstico por etapas (solo lectura) ==")
        stages, schema = discovery.test_connection(None, via="cli")
        for s in stages:
            mark = "OK " if s["ok"] else "XX "
            self.stdout.write(f"[{mark}] {s['stage']}: {s['state']} · {s['detail']}" + (f" ({s['ms']} ms)" if s.get("ms") is not None else ""))
        if o["sondear"]:
            if schema is None:
                self.stdout.write(self.style.WARNING("Sin $metadata del servidor: no se sondea."))
            else:
                names = [n.strip() for n in o["entidades"].split(",") if n.strip()] or None
                self.stdout.write(f"Sondeo controlado ({len(names) if names else schema.entity_set_count} conjuntos, $top=1)...")
                run = discovery.probe(names, None, "cli", delay_ms=o["retardo_ms"],
                                      progress=lambda pct, msg: self.stdout.write(f"  {pct:3d}% {msg}"))
                self.stdout.write(f"Resultado: {run.summary}")
        rep = discovery.report()
        out = Path(o["salida"] or (settings.DATA_DIR / "diagnosticos"))
        out.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        jpath = out / f"diagnostico_factorylogix_{stamp}.json"
        jpath.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        mpath = out / f"diagnostico_factorylogix_{stamp}.md"
        mpath.write_text(_markdown(rep, stages), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Reporte: {jpath}\n         {mpath}"))
        self.stdout.write("El reporte no contiene datos de registros ni credenciales; revíselo antes de compartirlo.")


def _markdown(rep, stages):
    L = [f"# Diagnóstico FactoryLogix · {rep['generated_at']}", "", f"Servicio: `{rep['service']}` · autenticación configurada: "
         f"`{rep['auth']['configured']}` · ofrecida por el servidor: {', '.join(rep['auth']['offered_by_server']) or 'no declarada / anónimo'}", "",
         "## Etapas", "", "| Etapa | Estado | Detalle |", "|---|---|---|"]
    L += [f"| {s['stage']} | {s['state']} | {s['detail']} |" for s in stages]
    sc = rep["schema"]
    if sc:
        L += ["", "## Esquema", "", f"OData {sc['odata_version']} · {sc['entity_sets']} EntitySets · {len(sc['function_imports'])} FunctionImports · "
              f"SHA-256 `{sc['sha256'][:16]}…`", "", "| EntitySet | Categoría | Estado | HTTP | ms | Propiedades | Claves |", "|---|---|---|---|---|---|---|"]
        for e in rep["entity_sets"]:
            L.append(f"| {e['name']} | {e['category']} | {e['status']} | {e['http_status'] or ''} | {e['latency_ms'] or ''} | {len(e['properties'])} | "
                     f"{', '.join(e['keys'])} |")
        missing = [x["name"] for x in rep["expected_from_gpv_list"] if not x["in_metadata"]]
        L += ["", "## Listados por GPV pero ausentes del $metadata", "", ", ".join(missing) or "Ninguno", "", "## FunctionImports (no se invocan)", ""]
        for f in sc["function_imports"]:
            ps = ", ".join(f"{p.get('name')}: {p.get('type')}" for p in f.get("parameters", []))
            L.append(f"* `{f['name']}` ({f.get('kind')}, {f.get('http_method')}) ({ps}) → {f.get('returns') or '—'}")
    L += ["", rep["note"], ""]
    return "\n".join(L)
