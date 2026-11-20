# Start HIMS backend (Django) and frontend (Vite) natively on Windows.
# Prerequisites: .venv created at repo root, PostgreSQL service running, migrations + seed done.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtualenv not found at $python. See README.md, One-time setup."
}

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
$backend = Start-Process -FilePath $python `
    -ArgumentList "manage.py", "runserver", "127.0.0.1:8000" `
    -WorkingDirectory (Join-Path $root "backend") `
    -PassThru -NoNewWindow

Write-Host "Starting frontend on http://127.0.0.1:5173 ..."
try {
    Push-Location (Join-Path $root "frontend")
    npm run dev -- --host 127.0.0.1 --port 5173
} finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
