@echo off
chcp 65001 >nul 2>&1
setlocal

echo ============================================================
echo  VeriFlow GUI Launcher
echo ============================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    echo Please install Python 3.8+: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "%~dp0veriflow_gui.py" (
    echo ERROR: veriflow_gui.py not found.
    echo Please run this script from the VeriFlow project root directory.
    pause
    exit /b 1
)

cd /d "%~dp0"
echo Starting VeriFlow GUI...
echo ============================================================

python "%~dp0run_veriflow.py"

if %errorlevel% neq 0 (
    echo.
    pause
)
