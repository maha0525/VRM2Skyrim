@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" wizard.py %*
) else (
  python wizard.py %*
)
if errorlevel 1 (
  echo VRM2Skyrim stopped. Run Setup.cmd for first-time setup, or see the error above.
  pause
)
