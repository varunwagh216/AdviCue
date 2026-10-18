# Local llama.cpp launcher; portable model and runtime can be bundled inside project.
# No Ollama install, PATH edits, Docker, external AI APIs or system-wide AI package.
param(
    [string]$BackendPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend'),
    [switch]$SkipWhisper
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$backend = (Resolve-Path $BackendPath).Path
$project = Split-Path -Parent $backend
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Python environment is missing; run SETUP_WINDOWS.bat first.' }
$logs = Join-Path $project 'local-ai-logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Get-LocalSetting([string]$Name, [string]$DefaultValue) {
    $file = Join-Path $backend '.env'
    if (Test-Path $file) {
        foreach ($line in (Get-Content $file)) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*$' -and $matches[1] -eq $Name) {
                $value = $matches[2].Trim().Trim('"').Trim("'")
                if ($value) { return $value }
            }
        }
    }
    return $DefaultValue
}

function Test-LlamaService {
    try {
        $status = Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 3 -ErrorAction Stop
        if ($status.status -ne 'ok') { return $false }
        $models = Invoke-RestMethod 'http://127.0.0.1:8080/v1/models' -TimeoutSec 3 -ErrorAction Stop
        return (@($models.data | Where-Object { $_.id -eq 'advicue-llama-1b-q4_k_m' }).Count -gt 0)
    } catch { return $false }
}

$endpoint = Get-LocalSetting 'LLAMA_CPP_URL' 'http://127.0.0.1:8080'
if ($endpoint.TrimEnd('/') -notin @('http://127.0.0.1:8080', 'http://localhost:8080')) {
    throw "Local launcher only supports llama.cpp loopback port 8080, not: $endpoint"
}
Write-Host ''
Write-Host '========== AdviCue AI: Portable llama.cpp =============' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'PREPARE_LLAMA_CPP.ps1') -OfflineOnly

if (Test-LlamaService) {
    Write-Host '[llama.cpp] Existing AdviCue model server is ready; reusing it.' -ForegroundColor Green
} else {
    $alreadyListening = $false
    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        try { $socket.Connect('127.0.0.1', 8080); $alreadyListening = $true } finally { $socket.Close() }
    } catch { }
    if ($alreadyListening) { throw 'Port 8080 is occupied by another app/model. Stop it before launching AdviCue AI.' }
    $exe = Join-Path $project 'local_ai\bin\llama-server.exe'
    $model = Join-Path $project 'local_ai\models\Llama-3.2-1B-Instruct-Q4_K_M.gguf'
    $args = @('-m', ('"' + $model + '"'), '--host', '127.0.0.1', '--port', '8080', '--alias', 'advicue-llama-1b-q4_k_m', '--ctx-size', '8192')
    Write-Host '[llama.cpp] Loading quantized Llama 3.2 1B from the project folder...' -ForegroundColor Cyan
    Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'llama-server.stdout.log') `
        -RedirectStandardError (Join-Path $logs 'llama-server.stderr.log') | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        if (Test-LlamaService) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "llama.cpp did not become ready within 120 seconds. Read $logs\llama-server.stderr.log" }
    Write-Host '[llama.cpp] Local model endpoint is responsive and model identity verified.' -ForegroundColor Green
}


if (-not $SkipWhisper) {
 Push-Location $backend
 try {
  & $python -m app.scripts.prepare_whisper --check
  if ($LASTEXITCODE -ne 0) { throw 'Install whisper.cpp and its model before starting. No runtime download is allowed.' }
 } finally { Pop-Location }
}
Write-Host 'Local llama.cpp and whisper.cpp assets checked without downloads.' -ForegroundColor Green
