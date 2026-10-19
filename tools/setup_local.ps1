param([switch]$Update, [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $workspaceRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv를 설치한 뒤 다시 실행하세요. https://docs.astral.sh/uv/getting-started/installation/'
}
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if ($Update -and (Test-Path -LiteralPath $pythonPath)) {
    & $pythonPath -c "from pathlib import Path; from homeplan.repository import Repository; p=Path('data/homeplan.local.sqlite'); print(Repository(p).backup() if p.exists() else 'No existing database')"
    if ($LASTEXITCODE -ne 0) { throw '업데이트 전 백업에 실패했습니다.' }
    $expectedInstance = & $pythonPath -c "from pathlib import Path; import hashlib; print(hashlib.sha256(str(Path('data/homeplan.local.sqlite').resolve()).encode()).hexdigest()[:16])"
    foreach ($serverPort in 8765..8774) {
        try { $status = Invoke-RestMethod -Uri "http://127.0.0.1:$serverPort/api/health" -TimeoutSec 1 } catch { continue }
        if ($status.service -eq 'homeplan-gui' -and $status.instance -eq $expectedInstance) {
            $listeners = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $serverPort -State Listen -ErrorAction SilentlyContinue
            foreach ($listener in $listeners) {
                $serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
                if ($serverProcess.CommandLine -match 'homeplan\.server' -and $serverProcess.CommandLine -match "--port $serverPort") {
                    Stop-Process -Id $serverProcess.ProcessId
                }
            }
        }
    }
}
uv sync --locked --dev
if ($LASTEXITCODE -ne 0) { throw '설치에 실패했습니다.' }
if ($Update) {
    uv run pytest -q
    if ($LASTEXITCODE -ne 0) { throw '검증에 실패했습니다. 이전 백업을 보관했습니다.' }
}
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktopPath '우리집 매수계획.lnk'))
$shortcut.TargetPath = Join-Path $workspaceRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '-m homeplan.gui_launcher'
$shortcut.WorkingDirectory = $workspaceRoot
$shortcut.IconLocation = Join-Path $workspaceRoot 'web\homeplan.ico'
$shortcut.Description = '이 컴퓨터에 저장하는 우리집 매수계획'
$shortcut.Save()
Write-Output '설치와 바탕화면 바로가기 준비를 마쳤습니다.'
if (-not $NoLaunch) {
    Start-Process -FilePath $shortcut.TargetPath -ArgumentList '-m','homeplan.gui_launcher' -WorkingDirectory $workspaceRoot -WindowStyle Hidden
}
