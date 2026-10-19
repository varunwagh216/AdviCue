@echo off
cd /d "%~dp0backend"
echo AdviCue AI - local login check (no records or passwords are changed)
if not exist ".venv\Scripts\python.exe" (
 echo Python setup is missing. Run SETUP_WINDOWS.bat first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m app.scripts.check_login
echo.
echo Send a photo of this window if login still fails.
pause
