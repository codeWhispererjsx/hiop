$ErrorActionPreference = 'Stop'
Write-Host ''
Write-Host 'HIOP Local Agent connection setup' -ForegroundColor Cyan
Write-Host '---------------------------------'
Write-Host ''
try {
    $setupPath = Join-Path $PSScriptRoot 'setup.json'
    if (-not (Test-Path -LiteralPath $setupPath)) {
        throw 'This folder is incomplete. Extract the whole HIOP-Agent-Windows.zip first, then open Connect HIOP.cmd.'
    }
    $setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
    $agentRoot = Join-Path $env:LOCALAPPDATA 'HIOP Agent'
    $agentData = Join-Path $agentRoot 'data'
    $credentialPath = Join-Path $agentData 'credential.dpapi'
    $agentConfig = Join-Path $agentData 'agent.json'
    $alreadyEnrolled = Test-Path -LiteralPath $credentialPath

    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 from python.org/downloads/windows (include the Python launcher), then open Connect HIOP again.'
    }
    if ($alreadyEnrolled -and (Test-Path -LiteralPath $agentConfig)) {
        $currentConfig = Get-Content -LiteralPath $agentConfig -Raw | ConvertFrom-Json
        if ($currentConfig.backend_url.TrimEnd('/') -ne $setup.backend_url.TrimEnd('/')) {
            throw 'This agent is enrolled with a different HIOP server. Run Remove HIOP Agent.cmd first, then connect it to this server.'
        }
    }

    New-Item -ItemType Directory -Force -Path $agentRoot,$agentData | Out-Null
    if ($alreadyEnrolled) {
        Write-Host 'Updating the existing HIOP agent without changing its enrollment.' -ForegroundColor Yellow
        Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*$agentRoot*" -and $_.CommandLine -like '*hiop_agent.runner*' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'hiop_agent') -Destination $agentRoot -Recurse -Force
    & py -3 -m venv (Join-Path $agentRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    $agentPython = Join-Path $agentRoot '.venv\Scripts\python.exe'
    Write-Host 'Installing the Windows helper dependency...'
    & $agentPython -m pip install 'pywin32==311'
    if ($LASTEXITCODE -ne 0) { throw 'Agent dependency installation failed. Check your internet connection and retry.' }

    @{backend_url=$setup.backend_url;data_dir=$agentData;heartbeat_seconds=30;poll_seconds=5} |
        ConvertTo-Json | Set-Content -LiteralPath $agentConfig -Encoding UTF8
    if (-not $alreadyEnrolled) {
        Push-Location $agentRoot
        try {
            Write-Host ''
            Write-Host 'Paste the connection code from HIOP when asked below, then press Enter.' -ForegroundColor Yellow
            & $agentPython -m hiop_agent.runner --config $agentConfig --enroll-prompt
            if ($LASTEXITCODE -ne 0) { throw 'Connection failed. Generate a fresh connection code in HIOP and try again.' }
        } finally { Pop-Location }
    }

    $agentPythonw = Join-Path $agentRoot '.venv\Scripts\pythonw.exe'
    $agentArguments = '-m hiop_agent.runner --config "' + $agentConfig + '"'
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'HIOP Agent.lnk'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $agentPythonw
    $shortcut.Arguments = $agentArguments
    $shortcut.WorkingDirectory = $agentRoot
    $shortcut.Save()
    Start-Process -FilePath $agentPythonw -ArgumentList $agentArguments -WorkingDirectory $agentRoot -WindowStyle Hidden
    Write-Host ''
    Write-Host 'Connected.' -ForegroundColor Green
    Write-Host 'Return to HIOP Local Agents and confirm this computer is Online. The agent starts when you sign in to Windows.'
} catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host 'If you only see "Press any key to continue", scroll or look just above it for this message.'
    exit 1
}
