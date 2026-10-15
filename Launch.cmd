@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" wizard.py %*
) else (
  echo Project Python environment is missing. Install Python 3.11 or 3.12 and run Setup.cmd first.
  pause
  exit /b 1
)
if errorlevel 1 (
  echo VRM2Skyrim stopped. Run Setup.cmd for first-time setup, or see the error above.
  pause
)
