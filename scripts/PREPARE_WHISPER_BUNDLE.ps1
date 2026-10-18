# Explicit connected-machine preparation, never called by the launcher.
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target=Join-Path $root 'local_ai\whisper'
$models=Join-Path $root 'local_ai\models'
New-Item -ItemType Directory -Force -Path $target,$models | Out-Null
$archive=Join-Path $target 'whisper-v1.7.6.zip'
Invoke-WebRequest 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.7.6/whisper-bin-x64.zip' -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne '0d2eca299c248f965bd0341bcb219db4b433c7f0c0ce2200d4df85765e8156a9') {throw 'whisper.cpp archive hash mismatch'}
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $target 'unpacked') -Force
$exe=Get-ChildItem -LiteralPath (Join-Path $target 'unpacked') -Recurse -Filter 'whisper-cli.exe' | Select-Object -First 1
if (-not $exe) {throw 'whisper-cli missing'}
Copy-Item -Path (Join-Path $exe.Directory.FullName '*') -Destination $target -Recurse -Force
$model=Join-Path $models 'ggml-base.bin'
if (-not (Test-Path -LiteralPath $model)) {Invoke-WebRequest 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin' -OutFile $model}
Write-Host 'Speech assets prepared. Normal startup never downloads models.'
