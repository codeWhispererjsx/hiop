param([string]$OutputDirectory = "")
$ErrorActionPreference = "Stop"
$desktopData = Join-Path $env:LOCALAPPDATA "HIOP Desktop"
$backupRoot = if ($OutputDirectory) { $OutputDirectory } else { Join-Path $desktopData "backups" }
New-Item -ItemType Directory -Force $backupRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archive = Join-Path $backupRoot "hiop-desktop-$stamp.zip"
$databaseData = Join-Path $desktopData "postgres-data"
if (-not (Test-Path $databaseData)) { throw "HIOP desktop database has not been initialized yet." }
$temp = Join-Path $env:TEMP "hiop-desktop-backup-$stamp"
New-Item -ItemType Directory -Force $temp | Out-Null
Copy-Item -LiteralPath $databaseData -Destination (Join-Path $temp "postgres-data") -Recurse -Force
if (Test-Path (Join-Path $desktopData "logs")) { Copy-Item -LiteralPath (Join-Path $desktopData "logs") -Destination (Join-Path $temp "logs") -Recurse -Force }
Set-Content -LiteralPath (Join-Path $temp "backup.json") -Value (@{created_at=(Get-Date).ToString("o"); product="HIOP Desktop"; kind="local-data"} | ConvertTo-Json)
Compress-Archive -LiteralPath (Join-Path $temp "*") -DestinationPath $archive -Force
Remove-Item -LiteralPath $temp -Recurse -Force
Write-Host $archive
