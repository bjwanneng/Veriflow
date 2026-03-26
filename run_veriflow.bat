@echo off
cd /d "%~dp0"
python run_veriflow.py
if %errorlevel% neq 0 pause
