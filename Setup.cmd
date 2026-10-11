@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; assert sys.version_info[:2] in ((3,11),(3,12)), 'Python 3.11 or 3.12 is required'"
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" bootstrap.py
if errorlevel 1 goto failed
echo Setup complete. Run Launch.cmd to open VRM2Skyrim.
pause
exit /b 0
:failed
echo Setup stopped. See the error above.
pause
exit /b 1
