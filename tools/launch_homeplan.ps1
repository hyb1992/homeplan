param([switch]$Check)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot

try {
    Set-Location -LiteralPath $projectRoot
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
        $uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
        & $uvPath sync --locked
        if ($LASTEXITCODE -ne 0) { throw 'Unable to prepare the Python environment.' }
    }
    if ($Check) {
        & $pythonPath -m homeplan.gui_launcher --check
    } else {
        $runtimeConfig = Join-Path $projectRoot 'data\desktop-runtime.local.json'
        if (Test-Path -LiteralPath $runtimeConfig) {
            $runtime = Get-Content -LiteralPath $runtimeConfig -Encoding UTF8 -Raw | ConvertFrom-Json
            if (Test-Path -LiteralPath $runtime.executable) {
                $env:HOMEPLAN_DATA_ROOT = $projectRoot
                Start-Process -FilePath $runtime.executable -WorkingDirectory $projectRoot -WindowStyle Hidden
                exit 0
            }
        }
        $pythonWindowPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
        Start-Process -FilePath $pythonWindowPath -ArgumentList @('-m', 'homeplan.gui_launcher') -WorkingDirectory $projectRoot -WindowStyle Hidden
        exit 0
    }
    if ($LASTEXITCODE -ne 0) { throw 'homeplan could not start. See the message above.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if (-not $Check) { Read-Host 'Press Enter to close' }
    exit 1
}
