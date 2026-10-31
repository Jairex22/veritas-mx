#!/usr/bin/env bash
# Prueba de carga reproducible: API en Release + 200 usuarios virtuales durante 120 s.
set -euo pipefail
cd "$(dirname "$0")/.."
dotnet build src/GPV.ProductTimeFlow.API -c Release
dotnet build tests/LoadTests -c Release
( cd src/GPV.ProductTimeFlow.API && ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS=http://localhost:5201 \
  RateLimiting__LoginPermitsPerMinute=5000 RateLimiting__ApiPermitsPerMinute=5000 Serilog__MinimumLevel__Default=Warning \
  dotnet bin/Release/net10.0/GPV.ProductTimeFlow.API.dll & echo $! > /tmp/timeflow-api.pid )
until curl -s http://localhost:5201/health >/dev/null; do sleep 2; done
dotnet run --project tests/LoadTests -c Release --no-build -- http://localhost:5201 "${VUS:-200}" "${SECONDS_RUN:-120}" "$(cat /tmp/timeflow-api.pid)"
kill "$(cat /tmp/timeflow-api.pid)"
