$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=Join-Path $root 'backend/.venv/Scripts/python.exe'
$marker=Join-Path $root 'app-logs/setup-complete.txt'
$prepared=(Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $marker)
if ($prepared) {
 Push-Location (Join-Path $root 'backend')
 try { & $python -c "import fastapi,uvicorn,sqlalchemy,alembic,httpx; import importlib.metadata as m,re; from pathlib import Path; [m.version(re.split(r'[<>=!~\[]',x.strip())[0]) for x in Path('requirements.txt').read_text().splitlines() if x.strip() and not x.startswith('#')]" 2>$null; $prepared=($LASTEXITCODE -eq 0) } catch { $prepared=$false } finally { Pop-Location }
}
foreach ($relative in @('local_ai/bin/llama-server.exe','local_ai/whisper/whisper-cli.exe','local_ai/models/ggml-base.bin')) { if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) { $prepared=$false } }
if (-not (Get-ChildItem -LiteralPath (Join-Path $root 'local_ai/models') -Filter '*.gguf' -ErrorAction SilentlyContinue)) { $prepared=$false }
if (-not $prepared) {
 Write-Host 'First launch or incomplete setup: preparing Python, project dependencies and local AI assets. Internet is required.' -ForegroundColor Cyan
 & (Join-Path $PSScriptRoot 'PREPARE_FIRST_RUN.ps1')
}
& (Join-Path $PSScriptRoot 'START_WINDOWS.ps1')
