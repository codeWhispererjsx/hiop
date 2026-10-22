$ErrorActionPreference = 'Stop'
$agentRoot = Join-Path $env:LOCALAPPDATA 'HIOP Agent'
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'HIOP Agent.lnk'

Write-Host 'This removes the HIOP agent, its saved credential, and its local observation queue for this Windows user.'
$confirmation = Read-Host 'Type REMOVE to continue'
if ($confirmation -cne 'REMOVE') {
    Write-Host 'Removal cancelled.'
    exit 0
}

try {
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$agentRoot*" -and $_.CommandLine -like '*hiop_agent.runner*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    if (Test-Path -LiteralPath $agentRoot) {
        Remove-Item -LiteralPath $agentRoot -Recurse -Force
    }
    Write-Host 'HIOP agent removed for this Windows user. The server-side registration remains in HIOP for audit history; revoke it from Local Agents if it should no longer be authorized.' -ForegroundColor Green
} catch {
    Write-Host "Agent removal failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
