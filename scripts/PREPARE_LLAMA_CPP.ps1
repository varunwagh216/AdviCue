# Prepare ONLY the portable llama.cpp text-generation runtime and GGUF model.
# This explicit preparation script is never allowed to download during operation.
# The llama.cpp GitHub /releases/latest endpoint may point to a stable release
# without CPU binaries. Use a known numbered release with a verified Win x64 CPU artifact.
param([switch]$OfflineOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin = Join-Path $root 'local_ai\bin'
$models = Join-Path $root 'local_ai\models'
$exe = Join-Path $bin 'llama-server.exe'
$model = Join-Path $models 'Llama-3.2-1B-Instruct-Q4_K_M.gguf'
New-Item -ItemType Directory -Force -Path $bin, $models | Out-Null

function Test-ValidGGUF([string]$File) {
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $File).Length -lt 600MB) { return $false }
    $stream = [System.IO.File]::OpenRead($File)
    try {
        $head = New-Object byte[] 4
        if ($stream.Read($head, 0, 4) -ne 4) { return $false }
        return ([System.Text.Encoding]::ASCII.GetString($head) -eq 'GGUF')
    } finally { $stream.Dispose() }
}

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    if ($OfflineOnly) { throw "Portable llama.cpp runtime missing: $exe" }

    # Official numbered release binary. The GitHub 'latest' stable release may
    # contain no CPU artifacts; this fixed tag avoids that broken discovery path.
    # Release SHA256 from the project's GitHub build attestation for b11429.
    $tag = 'b11429'
    $fileName = 'llama-b11429-bin-win-cpu-x64.zip'
    $url = "https://github.com/ggml-org/llama.cpp/releases/download/$tag/$fileName"
    $expectedSha256 = '1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe'
    Write-Host "[llama.cpp] Downloading official Windows x64 CPU runtime ($tag)..." -ForegroundColor Cyan

    $temp = Join-Path $env:TEMP ('advicue-llamacpp-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    try {
        $archive = Join-Path $temp $fileName
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -OutFile $archive -TimeoutSec 600
        } catch {
            throw "Runtime download failed: $($_.Exception.Message). You can download $fileName manually from https://github.com/ggml-org/llama.cpp/releases/tag/$tag and extract the directory containing llama-server.exe and its DLLs into local_ai\bin."
        }
        $actual = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expectedSha256) {
            throw "Runtime SHA256 mismatch. Expected $expectedSha256, got $actual. The ZIP was not installed."
        }
        $unpack = Join-Path $temp 'unpacked'
        Expand-Archive -LiteralPath $archive -DestinationPath $unpack -Force
        $server = Get-ChildItem -LiteralPath $unpack -Recurse -File -Filter 'llama-server.exe' |
            Select-Object -First 1
        if (-not $server) { throw 'Official CPU ZIP did not contain llama-server.exe.' }
        # Copy the executable AND neighboring DLL files, keeping relative paths.
        Copy-Item -Path (Join-Path $server.Directory.FullName '*') -Destination $bin -Recurse -Force
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'llama-server.exe was not copied.' }
        Write-Host '[llama.cpp] Portable runtime ready.' -ForegroundColor Green
    } finally {
        $resolvedTemp = [IO.Path]::GetFullPath($temp)
        $allowedTempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
        if ($resolvedTemp.StartsWith($allowedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and ([IO.Path]::GetFileName($resolvedTemp) -like 'advicue-llamacpp-*')) {
            Remove-Item -LiteralPath $resolvedTemp -Force -Recurse -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host '[llama.cpp] Portable runtime present; skipping runtime download.' -ForegroundColor Green
}

if (-not (Test-ValidGGUF $model)) {
    if (Test-Path -LiteralPath $model) {
        throw "Model file exists but is incomplete or invalid: $model. Verify it before deleting/re-downloading."
    }
    if ($OfflineOnly) { throw "Quantized Llama 3.2 1B model missing: $model" }
    Write-Host '[llama.cpp] Downloading ~808 MB 1B GGUF model one time...' -ForegroundColor Cyan
    Write-Host '[llama.cpp] Model license: Meta Llama 3.2 Community License. Check redistribution conditions before sharing.' -ForegroundColor Yellow
    $uri = 'https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf?download=true'
    $part = "$model.partial"
    try {
        Invoke-WebRequest -Uri $uri -UseBasicParsing -OutFile $part -TimeoutSec 3600
        if (-not (Test-ValidGGUF $part)) { throw 'Download was not a complete GGUF file.' }
        Move-Item -LiteralPath $part -Destination $model -Force
    } catch {
        Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
        throw "Model download failed: $($_.Exception.Message). Download Llama-3.2-1B-Instruct-Q4_K_M.gguf from bartowski/Llama-3.2-1B-Instruct-GGUF to local_ai\models."
    }
    Write-Host '[llama.cpp] GGUF model ready.' -ForegroundColor Green
} else {
    Write-Host '[llama.cpp] Quantized 1B model present; skipping download.' -ForegroundColor Green
}
Write-Host '[llama.cpp] Text-generation assets ready. Speech assets are prepared separately.' -ForegroundColor Green
