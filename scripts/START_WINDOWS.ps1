# Offline operation only. Preparation is a separate explicit step.
param([switch]$SkipLocalAI,[switch]$SkipWhisper)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend=Join-Path $root 'backend'
$python=Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Install local dependencies first using SETUP_WINDOWS.bat. Startup never downloads software.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\dist\index.html'))) { throw 'Compiled frontend missing. Build it during preparation.' }
if (-not (Test-Path -LiteralPath (Join-Path $backend 'advicue.db'))) { throw 'SQLite database missing. Restore your local database before starting.' }
if (-not (Test-Path -LiteralPath (Join-Path $backend '.env'))) { Copy-Item -LiteralPath (Join-Path $backend '.env.example') -Destination (Join-Path $backend '.env') }
$env:FRONTEND_ORIGIN='http://127.0.0.1:8000'
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:OTEL_SDK_DISABLED='true'
Push-Location $backend
try {
 & $python -m app.scripts.backup_sqlite_before_upgrade
 if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; startup stopped.' }
 & $python -m alembic upgrade head
 if ($LASTEXITCODE -ne 0) { throw 'Database migration failed; startup stopped.' }
} finally { Pop-Location }
if (-not $SkipLocalAI) { & (Join-Path $PSScriptRoot 'ENSURE_LOCAL_AI.ps1') -BackendPath $backend -SkipWhisper:$SkipWhisper }
$logs=Join-Path $root 'app-logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
try {
 $health=Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2
 if ($health.service -ne 'advicue-ai' -or $health.edition -ne 'AdviCue AI') { throw 'Port 8000 belongs to another service.' }
 Write-Host 'An AdviCue server already uses port 8000. Stop an older version before starting this release.' -ForegroundColor Yellow
} catch {
 $socket=New-Object System.Net.Sockets.TcpClient
 $occupied=$false
 try { $socket.Connect('127.0.0.1',8000);$occupied=$true } catch {} finally {$socket.Close()}
 if ($occupied) { throw 'Port 8000 is occupied. Stop that service before starting AdviCue.' }
 Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'backend.stdout.log') -RedirectStandardError (Join-Path $logs 'backend.stderr.log') | Out-Null
}
$ready=$false
for ($i=0;$i -lt 40;$i++) {
 try { $health=Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2; if ($health.service -eq 'advicue-ai') {$ready=$true;break} } catch {}
 Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Server did not become ready. See app-logs/backend.stderr.log.' }
Write-Host 'AdviCue Advisor is ready: http://127.0.0.1:8000' -ForegroundColor Green
Write-Host 'All processing stays on this computer. No startup download was requested.'
Start-Process 'http://127.0.0.1:8000' | Out-Null
