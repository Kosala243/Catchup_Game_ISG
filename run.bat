@echo off
setlocal
rem Run relative to the batch file, regardless of the caller's current folder.
cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: Unable to open the Catchup folder.
  exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python was not found on PATH. Python 3.10.7 is expected.
  exit /b 1
)
python tools\check_environment.py --require-python-310
if errorlevel 1 exit /b 1
python main.py %*
exit /b %errorlevel%
