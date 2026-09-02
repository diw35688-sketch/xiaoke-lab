@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo [Project] %CD%

if exist .venv\Scripts\python.exe (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" "scripts\start_best.py"
    pause
    exit /b 0
  )
  echo [Warning] Existing .venv is invalid; trying another Python environment.
)

if exist .build-venv\Scripts\python.exe (
  ".build-venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    ".build-venv\Scripts\python.exe" "scripts\start_best.py"
    pause
    exit /b 0
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python "scripts\setup.py" --mirror https://pypi.tuna.tsinghua.edu.cn/simple
  if exist .venv\Scripts\python.exe ".venv\Scripts\python.exe" "scripts\start_best.py"
  pause
  exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "scripts\setup.py" --mirror https://pypi.tuna.tsinghua.edu.cn/simple
  if exist .venv\Scripts\python.exe ".venv\Scripts\python.exe" "scripts\start_best.py"
  pause
  exit /b 0
)

echo Python 3.10+ is required. Please install it first.
pause
exit /b 1
