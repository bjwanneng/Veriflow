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
import platform
import signal

def main():
    # 检查 Python 版本
    if sys.version_info < (3, 8):
        print("❌ 需要 Python 3.8 或更高版本")
        return

    # 检查是否在 VeriFlow 项目目录中
    if not os.path.exists("veriflow_gui.py"):
        print("❌ 错误：未找到 veriflow_gui.py 文件")
        print("请在 VeriFlow 项目根目录中运行此脚本")
        return

    print("=" * 60)
    print("🚀 VeriFlow GUI 启动脚本")
    print("=" * 60)
    print(f"Python 版本: {sys.version}")
    print(f"系统: {platform.system()} {platform.release()}")
    print("=" * 60)

    try:
        # 启动 VeriFlow GUI
        print("正在启动 VeriFlow GUI 服务器...")

        # 在后台启动服务器
        process = subprocess.Popen(
            [sys.executable, "veriflow_gui.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        print("✅ 服务器已启动")

        # 等待服务器启动并获取输出
        server_ready = False
        url = None

        for _ in range(10):
            time.sleep(1)
            # 读取输出
            if process.stdout and not process.stdout.closed:
                line = process.stdout.readline()
                if line:
                    print(line.strip())
                    if "Running on" in line or "请在浏览器中访问:" in line:
                        # 提取 URL
                        if "请在浏览器中访问:" in line:
                            url = line.strip().split(": ")[-1]
                        elif "Running on" in line:
                            url = line.strip().split(" ")[-1]

                        if url and ("http://" in url or "https://" in url):
                            server_ready = True
                            break

        if not server_ready:
            print("⚠️  无法自动检测服务器地址")
            url = "http://127.0.0.1:7860"
            print(f"请尝试访问: {url}")

        # 自动打开浏览器
        if server_ready:
            print(f"正在打开浏览器访问: {url}")
            webbrowser.open(url)
            print("✅ 浏览器已打开")
        else:
            print("⚠️  服务器未完全启动，但将继续运行")
            print("您可以手动在浏览器中访问:", url)

        print("=" * 60)
        print("服务器正在运行中...")
        print("按 Ctrl+C 停止服务器")
        print("=" * 60)

        # 保持脚本运行直到用户按下 Ctrl+C
        while True:
            time.sleep(0.5)
            if process.poll() is not None:
                print(f"\n服务器已终止，退出码: {process.returncode}")
                break

    except KeyboardInterrupt:
        print("\n\n接收到停止信号")
        print("正在停止服务器...")
        try:
            process.terminate()
            time.sleep(2)
            if process.poll() is None:
                process.kill()
            print("✅ 服务器已停止")
        except Exception as e:
            print(f"❌ 停止服务器时出错: {e}")
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        print(f"详细错误: {type(e).__name__}: {e}")
        import traceback
        print("\n堆栈跟踪:")
        print(traceback.format_exc())
    finally:
        try:
            if 'process' in locals() and process.poll() is None:
                process.terminate()
                time.sleep(0.5)
                if process.poll() is None:
                    process.kill()
        except Exception:
            pass
        print("\n✅ VeriFlow GUI 启动脚本已结束")

if __name__ == "__main__":
    main()