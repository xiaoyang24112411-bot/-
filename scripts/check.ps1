$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ruffPath = Join-Path $projectRoot ".venv\Scripts\ruff.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project virtual environment not found."
}

Set-Location -LiteralPath $projectRoot
& $pythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $ruffPath check .
exit $LASTEXITCODE
