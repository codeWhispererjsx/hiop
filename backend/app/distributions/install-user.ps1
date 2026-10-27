$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    exit $process.ExitCode
}

try {
    $setupPath = Join-Path $PSScriptRoot 'setup.json'
    if (-not (Test-Path -LiteralPath $setupPath)) {
        throw 'This download is incomplete. Download and extract the full HIOP Agent Windows package.'
    }

    $setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
    if (-not $setup.backend_url) {
        throw 'The HIOP server URL is missing from this download.'
    }

    $sourceService = Join-Path $PSScriptRoot 'service'
    $sourceTray = Join-Path $PSScriptRoot 'tray'
    if (-not (Test-Path -LiteralPath (Join-Path $sourceService 'Hiop.Agent.Service.exe')) -or
        -not (Test-Path -LiteralPath (Join-Path $sourceTray 'Hiop.Agent.Tray.exe'))) {
        throw 'The native HIOP agent files are incomplete. Download a fresh installer package.'
    }

    $installRoot = Join-Path $env:ProgramFiles 'HIOP\Agent'
    $dataRoot = Join-Path $env:ProgramData 'HIOP\Agent\State'
    $configPath = Join-Path $installRoot 'agent.json'
    $servicePath = Join-Path $installRoot 'service'
    $trayPath = Join-Path $installRoot 'tray'
    $serviceExe = Join-Path $servicePath 'Hiop.Agent.Service.exe'
    $trayExe = Join-Path $trayPath 'Hiop.Agent.Tray.exe'
    $serviceName = 'HIOPAgent'
    $brokerName = 'HIOPAgentCommandBroker'

    if (Test-Path -LiteralPath $configPath) {
        $currentConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($currentConfig.backendUrl.TrimEnd('/') -ne $setup.backend_url.TrimEnd('/')) {
            throw 'This agent is configured for a different HIOP server. Remove it from that server before installing this package.'
        }
        Write-Host 'Updating the existing HIOP agent without changing its enrollment.' -ForegroundColor Yellow
    }

    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existingService -and $existingService.Status -ne 'Stopped') {
        Stop-Service -Name $serviceName -Force
        $existingService.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }

    New-Item -ItemType Directory -Force -Path $installRoot,$dataRoot | Out-Null
    Copy-Item -LiteralPath $sourceService -Destination $installRoot -Recurse -Force
    Copy-Item -LiteralPath $sourceTray -Destination $installRoot -Recurse -Force

    if (-not (Test-Path -LiteralPath $configPath)) {
        @{
            backendUrl = $setup.backend_url.TrimEnd('/')
            agentName = $env:COMPUTERNAME
            heartbeatSeconds = 30
            pollSeconds = 5
        } | ConvertTo-Json -Compress | Set-Content -LiteralPath $configPath -Encoding UTF8
    }

    & icacls.exe $dataRoot /inheritance:r /grant:r '*S-1-5-19:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not restrict the agent credential and queue folder permissions.'
    }

    $binaryPath = '"' + $serviceExe + '" --config "' + $configPath + '"'
    if ($existingService) {
        & sc.exe config $serviceName binPath= $binaryPath start= auto obj= 'NT AUTHORITY\LocalService' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not update the HIOP Windows service configuration.'
        }
    } else {
        & sc.exe create $serviceName binPath= $binaryPath start= auto obj= 'NT AUTHORITY\LocalService' DisplayName= 'HIOP Local Agent' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not install the HIOP Windows service.'
        }
    }

    $broker = Get-Service -Name $brokerName -ErrorAction SilentlyContinue
    if ($broker -and $broker.Status -ne 'Stopped') {
        Stop-Service -Name $brokerName -Force
        $broker.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }
    $brokerBinaryPath = '"' + $serviceExe + '" --privileged-helper'
    if ($broker) {
        & sc.exe config $brokerName binPath= $brokerBinaryPath start= auto obj= LocalSystem | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not update the restricted HIOP command broker.'
        }
    } else {
        & sc.exe create $brokerName binPath= $brokerBinaryPath start= auto obj= LocalSystem DisplayName= 'HIOP Agent Command Broker' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not install the restricted HIOP command broker.'
        }
    }
    & sc.exe description $brokerName 'Allowlisted HIOP Windows actions over a LocalService-restricted named pipe' | Out-Null
    Set-Service -Name $brokerName -StartupType Automatic
    & sc.exe sidtype $serviceName unrestricted | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not assign a service-specific identity to the HIOP agent.'
    }
    Start-Service -Name $brokerName

    & sc.exe description $serviceName 'HIOP property-bound discovery and monitoring agent' | Out-Null
    & sc.exe failure $serviceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not configure automatic service recovery.'
    }

    $runKey = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $runKey -Force | Out-Null
    New-ItemProperty -Path $runKey -Name 'HIOP Agent' -PropertyType String -Value ('"' + $trayExe + '"') -Force | Out-Null
    Set-Service -Name $serviceName -StartupType Automatic
    Start-Service -Name $serviceName
    Start-Process -FilePath $trayExe

    Write-Host ''
    Write-Host 'HIOP Agent installed.' -ForegroundColor Green
    Write-Host 'The separate LocalSystem broker accepts only fixed, allowlisted Windows actions.' -ForegroundColor Yellow
    Write-Host 'Use the HIOP Agent tray icon to enter a one-time connection code, then confirm this computer appears Online in HIOP.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
