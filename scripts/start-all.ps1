$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$napcatRuntime = Join-Path $projectRoot "work\napcat-shell\runtime"
$napcatLauncher = Join-Path $napcatRuntime "launcher-user.bat"
$stdoutPath = Join-Path $projectRoot "work\bot.stdout.log"
$stderrPath = Join-Path $projectRoot "work\bot.stderr.log"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project virtual environment not found: $pythonPath"
}

if (-not (Test-Path -LiteralPath $napcatLauncher)) {
    throw "NapCat launcher not found: $napcatLauncher"
}

$botListener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $botListener) {
    Start-Process `
        -FilePath $pythonPath `
        -ArgumentList "bot.py" `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

$botListener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if (-not $botListener) {
    throw "NoneBot failed to listen on port 8080. Check work\bot.stderr.log."
}

$napcatRunning = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "NapCatWinBootMain.exe" -and
    $_.ExecutablePath -and
    $_.ExecutablePath.StartsWith($napcatRuntime, [StringComparison]::OrdinalIgnoreCase)
}

if (-not $napcatRunning) {
    Start-Process `
        -FilePath $napcatLauncher `
        -WorkingDirectory $napcatRuntime `
        -WindowStyle Normal
}

Write-Host "NoneBot is listening on 127.0.0.1:8080."
Write-Host "NapCat launcher is running or has been started."
