#!/usr/bin/env bash
# Arranca la versión web en modo DEMO (datos sintéticos). Uso: ./scripts/run-demo.sh [--reset]
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--reset" ]]; then rm -rf App_Data; echo "Base DEMO eliminada; se regenerará."; fi
dotnet dev-certs https --check >/dev/null 2>&1 || dotnet dev-certs https
dotnet run --project src/GPV.ProductTimeFlow.Web --launch-profile https
