$ErrorActionPreference = 'Stop'
Write-Host ''
Write-Host 'HIOP Local Agent connection setup' -ForegroundColor Cyan
Write-Host '---------------------------------'
Write-Host ''
try {
    $setupPath = Join-Path $PSScriptRoot 'setup.json'
    if (-not (Test-Path $setupPath)) {
        throw 'This folder is incomplete. Extract the whole HIOP-Agent-Windows.zip first, then open Connect HIOP.cmd from the extracted folder.'
    }
    $setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
    $agentRoot = Join-Path $env:LOCALAPPDATA 'HIOP Agent'
    $agentData = Join-Path $agentRoot 'data'
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 from python.org/downloads/windows (include the Python launcher), then open Connect HIOP again.'
    }
    New-Item -ItemType Directory -Force -Path $agentRoot,$agentData | Out-Null
    $credentialPath = Join-Path $agentData 'credential.dpapi'
    if (Test-Path $credentialPath) {
        Write-Host 'This Windows account already has a saved HIOP connection.' -ForegroundColor Yellow
        Write-Host ''
        Write-Host 'Choose what to do:'
        Write-Host '  1. Keep the current connection and exit'
        Write-Host '  2. Replace it with a new HIOP connection code'
        Write-Host ''
        $choice = Read-Host 'Type 1 or 2, then press Enter'
        if ($choice -ne '2') {
            Write-Host ''
            Write-Host 'No changes made. Return to HIOP > Administration > Local Agents and check that this computer is Online.' -ForegroundColor Green
            exit 0
        }
        Write-Host ''
        Write-Host 'Replacing the saved local connection. Use a fresh code from HIOP.' -ForegroundColor Yellow
        Get-Process -Name pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $credentialPath -Force
    }
    Write-Host 'Preparing the local agent files...'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'hiop_agent') -Destination $agentRoot -Recurse -Force
    & py -3 -m venv (Join-Path $agentRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    $agentPython = Join-Path $agentRoot '.venv\Scripts\python.exe'
    Write-Host 'Installing the Windows helper dependency...'
    & $agentPython -m pip install 'pywin32==311'
    if ($LASTEXITCODE -ne 0) { throw 'Agent dependency installation failed. Check your internet connection and retry.' }
    $agentConfig = Join-Path $agentData 'agent.json'
    @{backend_url=$setup.backend_url;data_dir=$agentData;heartbeat_seconds=30;poll_seconds=5} | ConvertTo-Json | Set-Content -LiteralPath $agentConfig -Encoding UTF8
    Push-Location $agentRoot
    try {
        Write-Host ''
        Write-Host 'Paste the connection code from HIOP when asked below.' -ForegroundColor Yellow
        & $agentPython -m hiop_agent.runner --config $agentConfig --enroll-prompt
        if ($LASTEXITCODE -ne 0) { throw 'Connection failed. Generate a fresh connection code in HIOP and try again.' }
    } finally { Pop-Location }
    $agentPythonw = Join-Path $agentRoot '.venv\Scripts\pythonw.exe'
    $agentArguments = '-m hiop_agent.runner --config "' + $agentConfig + '"'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'HIOP Agent.lnk'))
    $shortcut.TargetPath = $agentPythonw
    $shortcut.Arguments = $agentArguments
    $shortcut.WorkingDirectory = $agentRoot
    $shortcut.Save()
    Start-Process -FilePath $agentPythonw -ArgumentList $agentArguments -WorkingDirectory $agentRoot -WindowStyle Hidden
    Write-Host ''
    Write-Host 'Connected.' -ForegroundColor Green
    Write-Host 'Return to HIOP Local Agents and wait for Online. Keep this computer awake and signed in. HIOP will start automatically when you sign in to Windows.'
} catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host 'If you only see "Press any key to continue", scroll or look just above it for this message.'
    exit 1
}
