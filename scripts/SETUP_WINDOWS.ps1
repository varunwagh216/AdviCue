# Explicit preparation: dependency installation is offline from a local wheelhouse.
$ErrorActionPreference='Stop'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
$env:PIP_NO_INDEX='1'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend=Join-Path $root 'backend'
$basePython=& (Join-Path $PSScriptRoot 'ENSURE_PYTHON.ps1')
$wheels=Join-Path $root 'offline-wheels'
if (-not (Test-Path -LiteralPath $wheels)) { throw 'Offline dependency wheelhouse missing. Prepare it on a connected machine first; see README. Nothing was downloaded.' }
Push-Location $backend
try {
 if (-not (Test-Path '.venv\Scripts\python.exe')) {
  & $basePython -m venv .venv
  if ($LASTEXITCODE -ne 0) {throw 'Could not create the Python environment.'}
 }
 $python=Join-Path $backend '.venv\Scripts\python.exe'
 & $python -m pip install --no-index --find-links $wheels -r requirements.txt
 if ($LASTEXITCODE -ne 0) { throw 'Local wheels do not match this Python version. Prepare compatible wheels; no internet fallback was attempted.' }
 if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
 & $python -m app.scripts.backup_sqlite_before_upgrade
 if ($LASTEXITCODE -ne 0) {throw 'Database backup failed.'}
 & $python -m alembic upgrade head
 if ($LASTEXITCODE -ne 0) {throw 'Migration failed.'}
} finally {Pop-Location}
Write-Host 'Offline Python preparation complete. Run RUN_WINDOWS.bat.' -ForegroundColor Green
