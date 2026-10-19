# Returns a compatible Python executable; installs for this user only when absent.
$ErrorActionPreference='Stop'
function Test-CompatiblePython([string]$Candidate) {
 if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate)) { return $false }
 try { & $Candidate -c "import sys,struct; sys.exit(0 if sys.version_info[:2] in [(3,14),(3,12)] and struct.calcsize('P')==8 else 1)" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
$candidates=@()
$projectRoot=Split-Path -Parent $PSScriptRoot
$candidates+=(Join-Path $projectRoot 'backend/.venv/Scripts/python.exe')
foreach ($version in @('314','312')) { $candidates+=(Join-Path $env:LOCALAPPDATA "Programs/Python/Python$version/python.exe") }
$command=Get-Command python.exe -ErrorAction SilentlyContinue
if ($command -and $command.Source -notmatch 'WindowsApps') { $candidates+=$command.Source }
$launcher=Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
 foreach ($version in @('-3.14','-3.12')) {
  try { $path=(& $launcher.Source $version -c "import sys; print(sys.executable)" 2>$null); if ($LASTEXITCODE -eq 0) { $candidates+=$path } } catch {}
 }
}
foreach ($candidate in $candidates) { if (Test-CompatiblePython $candidate) { return $candidate } }
if (-not [Environment]::Is64BitOperatingSystem) { throw 'AdviCue requires 64-bit Windows.' }
Write-Host 'Python is missing. Downloading the official Python 3.14 installer; internet is required.' -ForegroundColor Cyan
$installer=Join-Path ([IO.Path]::GetTempPath()) ('advicue-python-'+[guid]::NewGuid().ToString()+'.exe')
try {
 [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
 Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.14.8/python-3.14.8-amd64.exe' -OutFile $installer
 $signature=Get-AuthenticodeSignature -LiteralPath $installer
 if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python installer signature could not be verified.' }
 $target=Join-Path $env:LOCALAPPDATA 'Programs/Python/Python314'
 $arguments='/quiet InstallAllUsers=0 Include_launcher=0 Include_test=0 PrependPath=0 TargetDir="'+$target+'"'
 $installed=Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
 if ($installed.ExitCode -notin @(0,3010)) { throw "Python installation failed (code $($installed.ExitCode)). Install Python 3.14 x64 manually and retry." }
 $pythonPath=Join-Path $target 'python.exe'
 if (-not (Test-CompatiblePython $pythonPath)) { throw 'Python was not ready after installation. Restart Windows if requested, then retry.' }
 return $pythonPath
} finally { if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force } }
