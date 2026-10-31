#!/usr/bin/env bash
# Restaura, compila y ejecuta todas las pruebas (unitarias, integración y E2E con Playwright).
set -euo pipefail
cd "$(dirname "$0")/.."
dotnet restore GPV.ProductTimeFlow.sln
dotnet build GPV.ProductTimeFlow.sln --no-restore
dotnet test tests/UnitTests --no-build
dotnet test tests/IntegrationTests --no-build
# E2E: requiere Chromium de Playwright. Primera vez: pwsh tests/EndToEndTests/bin/Debug/net10.0/playwright.ps1 install chromium
dotnet test tests/EndToEndTests --no-build
