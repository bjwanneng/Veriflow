#!/usr/bin/env bash
# VeriFlow GUI 启动脚本 (macOS/Linux 版本)
#
# 功能：
# 1. 检查 Python 是否安装
# 2. 检查是否在 VeriFlow 项目目录中
# 3. 启动 VeriFlow GUI
# 4. 自动打开浏览器
#
# 使用方法：
# chmod +x run_veriflow.sh
# ./run_veriflow.sh

set -e

# 彩色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

function log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

function log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

function log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

function log_error() {
    echo -e "${RED}❌ $1${NC}"
}

function check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "未找到 Python 3"
        echo "请先安装 Python 3.8 或更高版本"
        if [ "$(uname -s)" = "Darwin" ]; then
            echo "在 macOS 上安装：brew install python3"
        elif [ "$(uname -s)" = "Linux" ]; then
            if command -v apt-get &> /dev/null; then
                echo "在 Ubuntu/Debian 上安装：sudo apt-get install python3"
            elif command -v yum &> /dev/null; then
                echo "在 CentOS/RHEL 上安装：sudo yum install python3"
            elif command -v dnf &> /dev/null; then
                echo "在 Fedora 上安装：sudo dnf install python3"
            fi
        fi
        exit 1
    fi

    # 检查 Python 版本
    local python_version=$(python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1,2)
    if awk '{if ($1 < 3.8) exit 1}' <<< "$python_version"; then
        log_error "Python 版本过低 ($python_version)"
        echo "需要 Python 3.8 或更高版本"
        exit 1
    fi

    log_success "Python $python_version 已准备好"
}

function check_project_dir() {
    if [ ! -f "veriflow_gui.py" ]; then
        log_error "未找到 veriflow_gui.py 文件"
        echo "请在 VeriFlow 项目根目录中运行此脚本"
        exit 1
    fi
    log_success "VeriFlow 项目目录已确认"
}

function open_browser() {
    local url="$1"
    local os=$(uname -s)

    log_info "正在打开浏览器访问：$url"

    case "$os" in
        Darwin)
            open "$url"
            ;;
        Linux)
            if command -v xdg-open &> /dev/null; then
                xdg-open "$url"
            elif command -v gnome-open &> /dev/null; then
                gnome-open "$url"
            elif command -v kde-open &> /dev/null; then
                kde-open "$url"
            else
                log_warning "无法自动打开浏览器，请手动访问：$url"
            fi
            ;;
        *)
            log_warning "不支持的系统 ($os)，请手动访问：$url"
            ;;
    esac
}

function main() {
    echo "================================================================"
    echo -e "${BLUE}🚀 VeriFlow GUI 启动脚本${NC}"
    echo "================================================================"
    echo "系统: $(uname -s) $(uname -r)"
    echo "架构: $(uname -m)"
    echo "当前目录: $(pwd)"
    echo "================================================================"

    check_python
    check_project_dir

    echo "================================================================"
    log_info "正在启动 VeriFlow GUI 服务器..."
    echo "================================================================"

    # 启动服务器并捕获输出
    local url="http://127.0.0.1:7860"
    python3 run_veriflow.py &
    local PID=$!

    log_info "服务器 PID: $PID"
    log_info "按 Ctrl+C 停止服务器"
    echo "================================================================"

    # 等待服务器启动
    sleep 3

    # 检查服务器是否正在运行
    if ps -p $PID > /dev/null; then
        open_browser "$url"
        log_success "服务器正在运行中..."
        wait $PID
    else
        log_error "服务器启动失败"
        exit 1
    fi
}

# 清理函数
function cleanup() {
    log_info "接收到停止信号"
    log_info "正在停止服务器..."
    kill $PID 2>/dev/null || true
    log_success "服务器已停止"
}

# 设置信号处理
trap cleanup SIGINT SIGTERM

# 执行主函数
main "$@"
