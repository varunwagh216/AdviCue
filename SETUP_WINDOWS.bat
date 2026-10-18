@echo off
cd /d "%~dp0"
title AdviCue AI - First-Time Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\PREPARE_FIRST_RUN.ps1"
if errorlevel 1 (
 echo Setup failed. Read the error above and retry after fixing it.
 pause
 exit /b 1
)
echo Setup complete. Run RUN_WINDOWS.bat to open AdviCue AI.
pause
