# Explicit preparation: dependency installation is offline from a local wheelhouse.
$ErrorActionPreference='Stop'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
$env:PIP_NO_INDEX='1'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend=Join-Path $root 'backend'
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.14 or 3.12 locally first.' }
$wheels=Join-Path $root 'offline-wheels'
if (-not (Test-Path -LiteralPath $wheels)) { throw 'Offline dependency wheelhouse missing. Prepare it on a connected machine first; see README. Nothing was downloaded.' }
Push-Location $backend
try {
 if (-not (Test-Path '.venv\Scripts\python.exe')) {
  $installedPython=(& py -0p 2>&1 | Out-String)
  if ($installedPython -match '3\.14') {$pythonVersion='-3.14'}
  elseif ($installedPython -match '3\.12') {$pythonVersion='-3.12'}
  else {throw 'Install Python 3.14 x64 or 3.12 x64; matching local wheels are included.'}
  & py $pythonVersion -m venv .venv
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
