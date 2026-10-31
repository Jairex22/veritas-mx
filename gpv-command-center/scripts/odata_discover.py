"""Descubrimiento OData desde la línea de comandos (sólo lectura).

Úselo en el servidor o en un equipo con acceso de red a FactoryLogix cuando
prefiera no usar el asistente de la interfaz. Lee la configuración del .env
(GPV_ODATA_BASE_URL, GPV_ODATA_AUTH, credenciales) y:

  py scripts\\odata_discover.py                      -> lista EntitySets y propiedades
  py scripts\\odata_discover.py --sample <EntitySet>  -> muestra hasta 10 filas
  py scripts\\odata_discover.py --report out.json     -> guarda el inventario completo

Nunca envía escrituras: sólo GET de $metadata y $top.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.connectors.base import HttpClientFactory  # noqa: E402
from backend.app.connectors.factorylogix import ODataConnector  # noqa: E402
from backend.app.core.errors import AppError  # noqa: E402
from backend.app.settings import Settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Inventario OData de FactoryLogix (sólo lectura)")
    ap.add_argument("--sample", metavar="ENTITYSET", help="muestra filas de un EntitySet")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--report", metavar="ARCHIVO.json", help="guarda el inventario en JSON")
    args = ap.parse_args()

    settings = Settings.from_env()
    if not settings.odata_base_url:
        print("GPV_ODATA_BASE_URL no está definido en el entorno ni en .env", file=sys.stderr)
        return 2
    conn = ODataConnector(settings, HttpClientFactory(settings.http_timeout_seconds, settings.verify_tls, settings.ca_bundle))
    print(f"Servidor: {settings.odata_base_url}")
    st = conn.probe()
    print(f"Estado: {st.state.value} ({st.message})")
    for d in st.diagnosis:
        print(f"  - {d}")
    if st.state.value != "OK":
        return 1
    try:
        meta = conn.metadata()
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    print(f"OData versión {meta.get('version')} · {len(meta['entity_sets'])} EntitySets\n")
    for es in meta["entity_sets"]:
        print(f"{es['name']}  ({es['entity_type']})")
        for p in es["properties"]:
            flag = " [clave]" if p["key"] else ""
            print(f"    {p['name']:<40} {p['type']}{flag}")
        if es["navigation"]:
            print(f"    navegación: {', '.join(es['navigation'])}")
    if args.sample:
        try:
            rows = conn.sample(args.sample, args.top)
        except AppError as exc:
            print(f"\nError al muestrear {args.sample}: {exc.message}", file=sys.stderr)
            return 1
        print(f"\nMuestra de {args.sample} ({len(rows)} filas):")
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
    if args.report:
        Path(args.report).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nInventario guardado en {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
