Set-Location (Join-Path $PSScriptRoot "..")
dotnet restore GPV.ProductTimeFlow.sln; if ($LASTEXITCODE) { exit 1 }
dotnet build GPV.ProductTimeFlow.sln --no-restore; if ($LASTEXITCODE) { exit 1 }
dotnet test tests/UnitTests --no-build; if ($LASTEXITCODE) { exit 1 }
dotnet test tests/IntegrationTests --no-build; if ($LASTEXITCODE) { exit 1 }
# Primera vez: pwsh tests/EndToEndTests/bin/Debug/net10.0/playwright.ps1 install chromium
dotnet test tests/EndToEndTests --no-build
