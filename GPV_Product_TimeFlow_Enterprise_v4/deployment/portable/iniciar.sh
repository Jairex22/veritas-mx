#!/usr/bin/env bash
# Lanzador portátil (Linux/macOS). No requiere .NET instalado.
cd "$(dirname "$0")"
export ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS=http://localhost:5101 TimeFlow__DataRoot=App_Data TimeFlow__PublicBaseUrl=http://localhost:5101 Serilog__MinimumLevel__Default=Warning
echo "GPV Product TimeFlow (DEMO) → http://localhost:5101  (Ctrl+C para detener)"
( sleep 15; (xdg-open http://localhost:5101 || open http://localhost:5101) >/dev/null 2>&1 ) &
./GPV.ProductTimeFlow.Web
