# Start the voice browser: the backend, then (CONSOLE_MODE=overlay) the floating orb. Bind this to a shortcut key (docs/START_KEY.md).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$envFile = Join-Path $root ".env"
$mode = "browser"
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^\s*CONSOLE_MODE\s*=\s*(\w+)' | Select-Object -First 1
    if ($line) { $mode = $line.Matches[0].Groups[1].Value.ToLower() }
}
if ($env:CONSOLE_MODE) { $mode = $env:CONSOLE_MODE.ToLower() }

$port = if ($env:PORT) { $env:PORT } else { "8080" }
$up = $false
try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 1 | Out-Null; $up = $true } catch {}
if (-not $up) { Start-Process -FilePath $py -ArgumentList "-m", "app.main" -WorkingDirectory $root -WindowStyle Minimized }

if ($mode -eq "overlay") {
    & $py -m app.overlay
} else {
    Start-Process "http://127.0.0.1:$port/console"
}
