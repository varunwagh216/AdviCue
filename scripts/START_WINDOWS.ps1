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
$listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,8000)
try { $listener.Start() } catch {
 $listener.Stop()
 $listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0)
 $listener.Start()
}
$port=$listener.LocalEndpoint.Port
$listener.Stop()
$localUrl="http://127.0.0.1:$port"
$env:FRONTEND_ORIGIN=$localUrl
$env:ADVICUE_INSTANCE_ID=[guid]::NewGuid().ToString()
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
$process=Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$port") -WorkingDirectory $backend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'backend.stdout.log') -RedirectStandardError (Join-Path $logs 'backend.stderr.log')
$ready=$false
for ($i=0;$i -lt 40;$i++) {
 try { $health=Invoke-RestMethod "$localUrl/api/v1/health" -TimeoutSec 2; if ($health.service -eq 'advicue-ai' -and $health.instance_id -eq $env:ADVICUE_INSTANCE_ID) {$ready=$true;break} } catch {}
 Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Server did not become ready. See app-logs/backend.stderr.log.' }
Set-Content -LiteralPath (Join-Path $logs "OPEN_APP_URL.txt") -Value $localUrl
Write-Host "AdviCue Advisor is ready: $localUrl" -ForegroundColor Green
Write-Host 'All processing stays on this computer. No startup download was requested.'
Start-Process $localUrl | Out-Null
