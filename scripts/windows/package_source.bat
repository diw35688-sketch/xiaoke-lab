@echo off
setlocal
cd /d "%~dp0\..\.."
".venv\Scripts\python.exe" "scripts\package.py"
set "package_exit_code=%errorlevel%"
if not "%package_exit_code%"=="0" echo [ERROR] Source package failed with exit code %package_exit_code%.
pause
exit /b %package_exit_code%
