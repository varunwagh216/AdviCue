# Explicit one-time connected setup. RUN_WINDOWS remains offline.
$ErrorActionPreference='Stop'
Write-Host 'AdviCue AI: first-time preparation requires internet for AI runtimes and model files.' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'SETUP_WINDOWS.ps1')
Write-Host 'Preparing local llama.cpp and text model...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'PREPARE_LLAMA_CPP.ps1')
Write-Host 'Preparing local whisper.cpp and speech model...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'PREPARE_WHISPER_BUNDLE.ps1')
Write-Host 'Preparation finished. Run RUN_WINDOWS.bat. Normal operation needs no internet.' -ForegroundColor Green
