@echo off
setlocal
cd /d "%~dp0"
set "taskPython=python"
if exist ".venv\Scripts\python.exe" set "taskPython=%~dp0.venv\Scripts\python.exe"
if "%~1"=="" (
  "%taskPython%" wizard.py
) else (
  "%taskPython%" converter.py %*
  pause
)
