#!/usr/bin/env sh
# Desarrollo local (Linux/macOS): recarga automática.
cd "$(dirname "$0")/.." || exit 1
exec python3 -m uvicorn backend.app.main:create_app --factory --reload --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
