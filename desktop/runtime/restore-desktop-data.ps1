param([Parameter(Mandatory=$true)][string]$ArchivePath)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $ArchivePath)) { throw "Backup archive not found: $ArchivePath" }
$desktopData = Join-Path $env:LOCALAPPDATA "HIOP Desktop"
$databaseData = Join-Path $desktopData "postgres-data"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$restoreRoot = Join-Path $env:TEMP "hiop-desktop-restore-$stamp"
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $restoreRoot -Force
$restoredData = Join-Path $restoreRoot "postgres-data"
if (-not (Test-Path (Join-Path $restoredData "PG_VERSION"))) { throw "This archive does not contain a HIOP desktop database backup." }
if (Test-Path $databaseData) { Rename-Item -LiteralPath $databaseData -NewName "postgres-data.before-restore-$stamp" }
New-Item -ItemType Directory -Force $desktopData | Out-Null
Move-Item -LiteralPath $restoredData -Destination $databaseData
Remove-Item -LiteralPath $restoreRoot -Recurse -Force
Write-Host "Restore completed. Restart HIOP Desktop."
