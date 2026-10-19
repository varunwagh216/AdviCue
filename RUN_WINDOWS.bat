@echo off
cd /d "%~dp0"
title AdviCue AI - Offline Advisor Launcher
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\LAUNCH_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Launch failed. See the message above.
  pause
  exit /b 1
)
echo.
echo You can close this launcher window. The local server runs in the background.
pause
