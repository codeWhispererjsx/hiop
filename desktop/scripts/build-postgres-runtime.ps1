$ErrorActionPreference = "Stop"

$desktopRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeRoot = Join-Path $desktopRoot "build-runtime"
$postgresRoot = Join-Path $runtimeRoot "postgres"
$stampFile = Join-Path $runtimeRoot "postgres.version"
$archivePath = Join-Path $runtimeRoot "postgres-windows-x64.zip"
$downloadUrl = if ($env:HIOP_POSTGRES_RUNTIME_URL) { $env:HIOP_POSTGRES_RUNTIME_URL } else { "https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64-binaries.zip" }
$expectedVersion = if ($env:HIOP_POSTGRES_RUNTIME_VERSION) { $env:HIOP_POSTGRES_RUNTIME_VERSION } else { "postgresql-16.15-1-windows-x64-binaries" }
$psqlPath = Join-Path $postgresRoot "bin\psql.exe"

if ((Test-Path $psqlPath) -and (Test-Path $stampFile) -and ((Get-Content -LiteralPath $stampFile -Raw).Trim() -eq $expectedVersion)) {
  Write-Host "PostgreSQL runtime is already current at $postgresRoot"
  exit 0
}

New-Item -ItemType Directory -Force $runtimeRoot | Out-Null
if (-not (Test-Path $archivePath)) {
  Write-Host "Downloading PostgreSQL desktop runtime..."
  Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
}

$tempRoot = Join-Path $runtimeRoot "postgres-extract"
if (Test-Path $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
New-Item -ItemType Directory -Force $tempRoot | Out-Null
Expand-Archive -LiteralPath $archivePath -DestinationPath $tempRoot -Force

$extractedPg = Get-ChildItem -LiteralPath $tempRoot -Directory -Recurse | Where-Object { Test-Path (Join-Path $_.FullName "bin\pg_ctl.exe") } | Select-Object -First 1
if (-not $extractedPg) {
  throw "Downloaded PostgreSQL archive did not contain bin\pg_ctl.exe."
}

if (Test-Path $postgresRoot) { Remove-Item -LiteralPath $postgresRoot -Recurse -Force }
Move-Item -LiteralPath $extractedPg.FullName -Destination $postgresRoot
Remove-Item -LiteralPath $tempRoot -Recurse -Force
Set-Content -LiteralPath $stampFile -Value $expectedVersion

Write-Host "PostgreSQL runtime ready at $postgresRoot"
