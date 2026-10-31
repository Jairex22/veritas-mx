#!/usr/bin/env bash
# Genera una versión PORTÁTIL (runtime incluido, sin instalar .NET) de la Web en modo DEMO.
# Uso: ./scripts/publish-portable.sh [win-x64|linux-x64|osx-arm64|osx-x64]   → dist/portable-<rid>/ y dist/TimeFlow_Portable_<rid>.zip
set -euo pipefail
RID="${1:-win-x64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(dirname "$ROOT")/dist/portable-$RID"
rm -rf "$OUT"
dotnet publish "$ROOT/src/GPV.ProductTimeFlow.Web" -c Release -r "$RID" --self-contained true -p:PublishTrimmed=false -p:DebugType=none -o "$OUT"
cp "$ROOT/deployment/portable/LEEME.txt" "$OUT/"
if [[ "$RID" == win-* ]]; then cp "$ROOT/deployment/portable/Iniciar.cmd" "$OUT/"; else cp "$ROOT/deployment/portable/iniciar.sh" "$OUT/"; chmod +x "$OUT/iniciar.sh"; fi
( cd "$(dirname "$OUT")" && rm -f "TimeFlow_Portable_$RID.zip" && zip -rq "TimeFlow_Portable_$RID.zip" "portable-$RID" )
echo "Listo: $(dirname "$OUT")/TimeFlow_Portable_$RID.zip"
