@echo off
REM VeriFlow GUI 启动脚本 (Windows 批处理版本)
REM
REM 功能：
REM 1. 检查 Python 是否安装
REM 2. 检查是否在 VeriFlow 项目目录中
REM 3. 启动 VeriFlow GUI
REM 4. 自动打开浏览器
REM
REM 使用方法：双击此文件或在命令行中运行 run_veriflow.bat

echo ============================================================
echo 🚀 VeriFlow GUI 启动脚本
echo ============================================================

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到 Python
    echo 请先安装 Python 3.8 或更高版本
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python 已安装
python --version

REM 检查是否在 VeriFlow 项目目录中
if not exist "veriflow_gui.py" (
    echo ❌ 错误：未找到 veriflow_gui.py 文件
    echo 请在 VeriFlow 项目根目录中运行此脚本
    pause
    exit /b 1
)

echo ✅ VeriFlow 项目目录已确认
echo ============================================================
echo 正在启动 VeriFlow GUI...
echo ============================================================

REM 使用 Python 脚本启动
python run_veriflow.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo 脚本已停止，按任意键退出...
    pause >nul
)
