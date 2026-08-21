# PowerShell PostgreSQL Backup Script for HIOP
# Replaces the bash backup-postgres.sh for Windows environments

param(
    [string]$PGHOST = "localhost",
    [string]$PGDATABASE = "hiop",
    [string]$PGUSER = "hiop",
    [string]$PGPASSWORD = "Admin",
    [string]$BACKUP_DIR = "./backups",
    [int]$RETENTION_DAYS = 14
)

# Set environment variables for pg_dump
$env:PGPASSWORD = $PGPASSWORD

# Create backup directory if it doesn't exist
if (-not (Test-Path $BACKUP_DIR)) {
    New-Item -ItemType Directory -Path $BACKUP_DIR -Force
}

# Generate timestamp
$STAMP = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$FILE = Join-Path $BACKUP_DIR "hiop-$STAMP.dump"

# Run pg_dump
Write-Host "Starting backup of database $PGDATABASE..."
$dumpProcess = Start-Process -FilePath "pg_dump" -ArgumentList "-h", $PGHOST, "-U", $PGUSER, "-d", $PGDATABASE, "--format=custom", "--no-owner", "--no-acl", "--file=$FILE" -Wait -PassThru -NoNewWindow

if ($dumpProcess.ExitCode -ne 0) {
    Write-Error "Backup failed with exit code $($dumpProcess.ExitCode)"
    exit $dumpProcess.ExitCode
}

# Generate SHA256 checksum
Write-Host "Generating SHA256 checksum..."
$checksum = (Get-FileHash -Path $FILE -Algorithm SHA256).Hash
$checksum | Out-File -FilePath "$FILE.sha256" -Encoding utf8

# Remove old backups based on retention policy
Write-Host "Removing backups older than $RETENTION_DAYS days..."
$cutoffDate = (Get-Date).AddDays(-$RETENTION_DAYS)
Get-ChildItem -Path $BACKUP_DIR -Filter "hiop-*.dump" | Where-Object { $_.LastWriteTime -lt $cutoffDate } | Remove-Item -Force
Get-ChildItem -Path $BACKUP_DIR -Filter "hiop-*.dump.sha256" | Where-Object { $_.LastWriteTime -lt $cutoffDate } | Remove-Item -Force

Write-Host "Backup completed: $FILE"
Write-Host "SHA256: $checksum"
