#!/usr/bin/env bash
# Genera dist/GPV_Product_TimeFlow_Enterprise_v4.0.0.zip (junto a la carpeta del proyecto) sin binarios, bases de datos ni secretos.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$(basename "$ROOT")"
OUT="$(dirname "$ROOT")/dist"; mkdir -p "$OUT"
ZIP="$OUT/GPV_Product_TimeFlow_Enterprise_v4.0.0.zip"
rm -f "$ZIP"
cd "$(dirname "$ROOT")"
zip -rq "$ZIP" "$NAME" -x '*/bin/*' '*/obj/*' "$NAME/App_Data/*" '*.db' '*.db-shm' '*.db-wal' '*/TestResults/*' '*/.vs/*' '*.pfx' '*.keystore' '*.jks' '*/.env' '*/load-result-*.md'
echo "ZIP: $ZIP ($(du -h "$ZIP" | cut -f1))"
