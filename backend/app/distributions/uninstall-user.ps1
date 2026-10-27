$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    exit $process.ExitCode
}

Write-Host 'This removes the HIOP Windows service, tray app, saved credential, and local observation queue.'
Write-Host 'The server-side registration remains in HIOP for audit history. Revoke it there if it should no longer be authorized.'
$confirmation = Read-Host 'Type REMOVE to continue'
if ($confirmation -cne 'REMOVE') {
    Write-Host 'Removal cancelled.'
    exit 0
}

try {
    $serviceName = 'HIOPAgent'
    foreach ($name in @('HIOPAgentCommandBroker', $serviceName)) {
        $service = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($service) {
            if ($service.Status -ne 'Stopped') {
                Stop-Service -Name $name -Force
                $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
            }
            & sc.exe delete $name | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not remove the HIOP Windows service $name."
            }
        }
    }

    Remove-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'HIOP Agent' -ErrorAction SilentlyContinue
    $installRoot = Join-Path $env:ProgramFiles 'HIOP\Agent'
    $dataRoot = Join-Path $env:ProgramData 'HIOP\Agent'
    if (Test-Path -LiteralPath $installRoot) {
        Remove-Item -LiteralPath $installRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $dataRoot) {
        Remove-Item -LiteralPath $dataRoot -Recurse -Force
    }
    Write-Host 'HIOP Agent removed from this computer.' -ForegroundColor Green
} catch {
    Write-Host "Agent removal failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
