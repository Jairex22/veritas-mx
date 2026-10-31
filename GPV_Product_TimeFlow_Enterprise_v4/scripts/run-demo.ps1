# Arranca la versión web en modo DEMO (datos sintéticos). Uso: .\scripts\run-demo.ps1 [-Reset]
param([switch]$Reset)
Set-Location (Join-Path $PSScriptRoot "..")
if ($Reset) { Remove-Item -Recurse -Force App_Data -ErrorAction SilentlyContinue; Write-Host "Base DEMO eliminada; se regenerará." }
dotnet dev-certs https --trust
dotnet run --project src/GPV.ProductTimeFlow.Web --launch-profile https
