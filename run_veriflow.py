#!/usr/bin/env python3
"""
VeriFlow GUI 启动脚本

功能：
1. 自动启动 VeriFlow GUI 服务器
2. 自动检测可用端口
3. 自动打开浏览器访问 VeriFlow GUI
4. 提供优雅的终止机制

使用方法：
python run_veriflow.py
或
chmod +x run_veriflow.py
./run_veriflow.py

作者：WANNENG
版本：1.0.0
日期：2026-03-26
"""

import subprocess
import sys
import time
import webbrowser
import os
import socket
import platform

def find_free_port(start=7860, end=7900):
    """找到一个可用端口"""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start  # 回退到默认端口

def wait_for_server(host, port, timeout=30):
    """等待服务器在指定端口上就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.5)
    return False

def main():
    if sys.version_info < (3, 8):
        print("ERROR: Python 3.8+ required")
        return

    if not os.path.exists("veriflow_gui.py"):
        print("ERROR: veriflow_gui.py not found")
        print("Please run from the VeriFlow project root directory")
        return

    print("=" * 60)
    print("VeriFlow GUI Launcher")
    print("=" * 60)
    print(f"Python: {sys.version.split()[0]}")
    print(f"OS: {platform.system()} {platform.release()}")

    # 找可用端口
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Port: {port}")
    print(f"URL:  {url}")
    print("=" * 60)

    try:
        # 通过环境变量传递端口给 Gradio
        env = os.environ.copy()
        env["GRADIO_SERVER_PORT"] = str(port)
        env["GRADIO_SERVER_NAME"] = "127.0.0.1"

        print("Starting VeriFlow GUI server...")
        process = subprocess.Popen(
            [sys.executable, "veriflow_gui.py"],
            env=env,
        )

        # 等待服务器就绪（最多 30 秒）
        print("Waiting for server to be ready...")
        if wait_for_server("127.0.0.1", port, timeout=30):
            print(f"Server is ready!")
            print(f"Opening browser: {url}")
            webbrowser.open(url)
            print("Browser opened.")
        else:
            print(f"Server did not start in time, try opening manually: {url}")
            webbrowser.open(url)

        print("=" * 60)
        print("Server is running. Press Ctrl+C to stop.")
        print("=" * 60)

        process.wait()

    except KeyboardInterrupt:
        print("\nStopping server...")
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            process.kill()
        print("Server stopped.")
    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()