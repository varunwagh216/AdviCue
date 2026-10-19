# Explicit one-time connected setup. RUN_WINDOWS remains offline.
$ErrorActionPreference='Stop'
Write-Host 'AdviCue AI: first-time preparation requires internet for AI runtimes and model files.' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'SETUP_WINDOWS.ps1')
$backend=Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'
$python=Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try {
 Write-Host 'Checking the local advisor account...' -ForegroundColor Cyan
 & $python -m app.scripts.prepare_sample_database --download
 if ($LASTEXITCODE -ne 0) { throw 'Sample account preparation failed. Read the error above; existing records are preserved.' }
 & $python -m alembic upgrade head
 if ($LASTEXITCODE -ne 0) { throw 'Sample database migration failed.' }
} finally { Pop-Location }
Write-Host 'Preparing local llama.cpp and text model...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'PREPARE_LLAMA_CPP.ps1')
Write-Host 'Preparing local whisper.cpp and speech model...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'PREPARE_WHISPER_BUNDLE.ps1')
Write-Host 'Preparation finished. Run RUN_WINDOWS.bat. Normal operation needs no internet.' -ForegroundColor Green

$marker=Join-Path (Split-Path -Parent $PSScriptRoot) 'app-logs/setup-complete.txt'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $marker) | Out-Null
Set-Content -LiteralPath $marker -Value 'Local dependencies prepared successfully.'
