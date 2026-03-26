#!/usr/bin/env python3
"""
VeriFlow GUI - Web Interface for VeriFlow 8.2
左侧导航栏多页面布局

启动方式:
    python veriflow_gui.py
"""

import os
import sys
import json
import subprocess
import time
import queue
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import gradio as gr
except ImportError:
    print("❌ 需要安装 Gradio: pip install gradio>=4.0")
    sys.exit(1)

# 尝试导入 rich 库（可选）
try:
    from rich.console import Console
    from rich.text import Text
    from rich.theme import Theme
    from rich.style import Style
    _rich_available = True
except ImportError:
    _rich_available = False

# ============================================================================
# 全局状态
# ============================================================================

class GlobalState:
    def __init__(self):
        self.working_dir: Path = Path.home() / "veriflow_projects"
        self.current_project: Optional[str] = None
        self.mode: str = "quick"
        self.is_running: bool = False
        self.current_stage: str = "就绪"
        self.log_queue: queue.Queue = queue.Queue()
        self.progress: float = 0.0
        self.generated_files: List[Dict[str, str]] = []
        self.process: Optional[subprocess.Popen] = None
        self.stop_requested: bool = False
        # Review gate state
        self.review_pending: bool = False    # True = waiting for user decision
        self.review_stage: int = 0           # which stage is under review
        self.review_approved: bool = False   # True = approved, False = feedback given
        self.rerun_modules: Optional[List[str]] = None  # partial Stage 3 re-run
        # Log tracking
        self.current_log_path: Optional[Path] = None
        self.current_logs: List[str] = []   # all log lines for filter support
        self.current_logs_html: List[str] = []  # HTML formatted logs for display

    def reset(self):
        self.is_running = False
        self.current_stage = "就绪"
        self.progress = 0.0
        self.log_queue = queue.Queue()
        self.process = None
        self.stop_requested = False
        self.review_pending = False
        self.review_approved = False
        self.rerun_modules = None
        self.current_log_path = None
        self.current_logs = []
        self.current_logs_html = []

app_state = GlobalState()

# ============================================================================
# 本地配置持久化
# ============================================================================

CONFIG_FILE = Path.home() / ".veriflow" / "gui_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "working_dir": str(Path.home() / "veriflow_projects"),
    "last_project": "",
    "env": {
        "iverilog_path": "", "vvp_path": "", "yosys_path": "",
        "max_retries": 3, "timeout": 600, "auto_save": True, "verbose": False
    },
    "claude": {"cli_path": "", "use_mock": True, "mock_delay": 2.0},
    "codex": {
        "api_key": "", "model": "gpt-4o",
        "endpoint": "https://api.openai.com/v1",
        "system_prompt": "", "max_tokens": 4096, "temperature": 0.2
    },
    "compat": {"endpoint": "", "api_key": "", "model": ""}
}

def load_config() -> Dict[str, Any]:
    """从 ~/.veriflow/gui_config.json 加载配置"""
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # 深度合并：保证新增字段有默认值
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for k, v in data.items():
                if isinstance(v, dict) and k in merged:
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception as e:
        print(f"⚠️ 加载配置失败: {e}")
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(data: Dict[str, Any]) -> str:
    """保存配置到 ~/.veriflow/gui_config.json"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"✅ 配置已保存到 {CONFIG_FILE}"
    except Exception as e:
        return f"❌ 保存失败: {e}"

def get_skill_dir() -> Path:
    return Path(__file__).parent

def scan_projects(base_dir: Path) -> List[str]:
    projects = []
    if base_dir.exists():
        for item in sorted(base_dir.iterdir()):
            if item.is_dir() and (item / "requirement.md").exists():
                projects.append(item.name)
    return projects

def create_project_structure(project_path: Path, mode: str, freq: int) -> bool:
    try:
        (project_path / ".veriflow").mkdir(parents=True, exist_ok=True)
        (project_path / "workspace" / "docs").mkdir(parents=True, exist_ok=True)
        (project_path / "workspace" / "rtl").mkdir(parents=True, exist_ok=True)
        (project_path / "workspace" / "sim").mkdir(parents=True, exist_ok=True)
        config = {
            "project": project_path.name,
            "mode": mode,
            "target_frequency_mhz": freq,
            "coding_style": {
                "reset_type": "async_active_low",
                "reset_signal": "rst_n",
                "clock_edge": "posedge"
            },
            "created_at": datetime.now().isoformat()
        }
        with open(project_path / ".veriflow" / "project_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        req_file = project_path / "requirement.md"
        if not req_file.exists():
            req_file.write_text(
                "# 设计需求\n\n## 概述\n描述您的设计需求...\n\n## 功能需求\n- 功能1\n- 功能2\n\n## 接口\n- 输入: ...\n- 输出: ...\n",
                encoding="utf-8"
            )
        return True
    except Exception as e:
        print(f"创建项目结构失败: {e}")
        return False

LOG_ICONS: Dict[str, str] = {
    "info": "ℹ️", "success": "✅", "warning": "⚠️",
    "error": "❌", "stage": "🔄", "command": "⚡"
}

# Rich 终端风格主题
RICH_THEME = Theme({
    "log.timestamp": "bright_black",
    "log.info": "cyan",
    "log.success": "green",
    "log.warning": "yellow",
    "log.error": "red bold",
    "log.stage": "blue bold",
    "log.command": "magenta",
    "log.message": "default",
})

# 全局 Rich 控制台（如果可用）
_rich_console = None
_rich_html_console = None
if _rich_available:
    try:
        _rich_console = Console(theme=RICH_THEME)
        from rich.console import Console as HTMLConsole
        _rich_html_console = HTMLConsole(theme=RICH_THEME, record=True, width=120)
    except Exception:
        _rich_available = False

def _rich_log_to_html(message: str, log_type: str = "info") -> str:
    """使用 Rich 将日志格式化为 HTML，实现终端风格显示"""
    if not _rich_available or not _rich_html_console:
        # 如果 Rich 不可用，使用简单的 HTML 格式化
        color_map = {
            "info": "#58a6ff", "success": "#3fb950", "warning": "#d29922",
            "error": "#f85149", "stage": "#809fff", "command": "#d2a8ff"
        }
        color = color_map.get(log_type, "#58a6ff")
        return f'<span style="color:{color}">{message}</span>'

    try:
        from rich.text import Text
        from rich.markup import escape
        import re

        # 如果消息已经格式化，先解析它
        parsed_msg = message
        timestamp = ""
        icon = LOG_ICONS.get(log_type, "ℹ️")
        level_str = log_type.upper().ljust(7)

        # 尝试从消息中提取时间戳、图标和级别
        match = re.match(r'^\[(\d{2}:\d{2}:\d{2}\.\d{3})\]\s+(\S+)\s+(\S+)\s*(.*)$', message)
        if match:
            timestamp = match.group(1)
            icon = match.group(2)
            level_str = match.group(3)
            parsed_msg = match.group(4)
        else:
            # 没有格式化的消息，添加当前时间戳
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # 构建 Rich 格式化文本
        rich_text = Text()
        rich_text.append(f"[{timestamp}] ", style="log.timestamp")
        rich_text.append(f"{icon} ", style=f"log.{log_type}")
        rich_text.append(f"{level_str} ", style=f"log.{log_type}")
        rich_text.append(escape(parsed_msg), style="log.message")

        # 清除之前的记录
        _rich_html_console.clear()
        # 输出并捕获 HTML
        _rich_html_console.print(rich_text)
        html_output = _rich_html_console.export_html(inline_styles=True)

        # 简化 HTML，只保留 body 内容
        body_match = re.search(r'<body>(.*?)</body>', html_output, re.DOTALL)
        if body_match:
            content = body_match.group(1).strip()
            # 替换所有可能的黑色/白色背景为深色主题
            content = content.replace('background-color: white', 'background-color: #0d1117')
            content = content.replace('background-color:#ffffff', 'background-color:#0d1117')
            content = content.replace('background-color: #ffffff', 'background-color: #0d1117')
            content = content.replace('color: black', 'color: #f0f6fc')
            content = content.replace('color:#000000', 'color:#f0f6fc')
            content = content.replace('color: #000000', 'color:#f0f6fc')
            # 去掉 pre 标签的 margin/padding，避免行间空格
            content = re.sub(
                r'<pre\s+style="([^"]*)"',
                lambda m: f'<pre style="{m.group(1)};margin:0;padding:0;line-height:1.4"',
                content
            )
            return content
        return f'<span style="color:#58a6ff">{message}</span>'

    except Exception:
        # 回退到简单的 HTML 格式化
        color_map = {
            "info": "#58a6ff", "success": "#3fb950", "warning": "#d29922",
            "error": "#f85149", "stage": "#809fff", "command": "#d2a8ff"
        }
        color = color_map.get(log_type, "#58a6ff")
        return f'<span style="color:{color}">{message}</span>'

def add_log(message: str, log_type: str = "info") -> str:
    """Generate structured log line for GUI display (matches veriflow_ctl.py format).

    If the message is already formatted (starts with [HH:MM:SS.mmm]),
    it's returned as-is to avoid double-formatting.
    """
    # Check if already formatted (starts with [HH:MM:SS.mmm])
    import re
    if re.match(r'^\[\d{2}:\d{2}:\d{2}\.\d{3}\]', message):
        return message

    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    icon = LOG_ICONS.get(log_type, "ℹ️")

    # 优化格式：添加适当的间距和对齐，使用更清晰的结构
    level_map = {
        "info": "INFO", "success": "SUCCESS", "warning": "WARNING",
        "error": "ERROR", "stage": "STAGE", "command": "COMMAND"
    }
    level_str = level_map.get(log_type, "INFO").ljust(7)

    return f"[{timestamp}] {icon} {level_str} {message}"

def scan_generated_files(project_path: Path) -> List[Dict[str, str]]:
    """扫描 workspace 下所有子目录（rtl/sim/docs）的生成文件"""
    files = []
    subdirs = [("rtl", "RTL"), ("sim", "仿真"), ("docs", "文档")]
    for subdir, label in subdirs:
        d = project_path / "workspace" / subdir
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    size = f.stat().st_size
                    size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB"
                    files.append({
                        "文件": f.name,
                        "类型": f.suffix[1:].upper() or f.suffix or "-",
                        "大小": size_str,
                        "修改时间": datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M"),
                        "目录": label,
                    })
    return files

def find_workspace_file(project_path: Path, filename: str) -> Optional[Path]:
    """在 workspace 各子目录中查找文件"""
    for subdir in ["rtl", "sim", "docs"]:
        p = project_path / "workspace" / subdir / filename
        if p.exists():
            return p
    return None

# ============================================================================
# 项目状态持久化
# ============================================================================

def save_project_state(project_path: Path, state: dict) -> None:
    """保存运行状态到 <project>/.veriflow/project_state.json，
    同时把 mode 同步写回 project_config.json。"""
    try:
        vf_dir = project_path / ".veriflow"
        vf_dir.mkdir(parents=True, exist_ok=True)
        (vf_dir / "project_state.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # 同步 mode 到 project_config.json
        if "mode" in state:
            cfg_file = vf_dir / "project_config.json"
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
                cfg["mode"] = state["mode"]
                cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
    except Exception as e:
        print(f"保存项目状态失败: {e}")

def load_project_state(project_path: Path) -> dict:
    """加载 <project>/.veriflow/project_state.json"""
    state_file = project_path / ".veriflow" / "project_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

# Stage 顺序定义（用于"重跑时清除后续"逻辑）
_ALL_STAGE_ORDER = [1, 1.5, 2, 2.5, 3, 3.5, 4, 5]

_STAGE_LABELS = {
    1:   "S1 架构",
    1.5: "S1.5 微架构",
    2:   "S2 时序",
    2.5: "S2.5 审查",
    3:   "S3 RTL",
    3.5: "S3.5 Lint",
    4:   "S4 仿真",
    5:   "S5 综合",
}

_MODE_STAGES = {
    "quick":      [1, 1.5, 3, 3.5],
    "standard":   [1, 1.5, 2, 3, 3.5, 4, 5],
    "enterprise": [1, 1.5, 2, 3, 3.5, 4, 5],
}

def _render_stage_status(completed_stages: list, mode: str) -> str:
    """生成 stage 状态指示器 HTML（绿圈=完成，灰圈=未完成）"""
    active = _MODE_STAGES.get(mode, _MODE_STAGES["standard"])
    completed_set = set(float(s) for s in completed_stages)
    parts = []
    for s in active:
        label = _STAGE_LABELS.get(s, f"S{s}")
        done = float(s) in completed_set
        color = "#2ea043" if done else "#484f58"
        symbol = "●" if done else "○"
        parts.append(
            f"<span style='color:{color};margin-right:12px;white-space:nowrap'>"
            f"{symbol} {label}</span>"
        )
    return (
        "<div style='font-family:Consolas,monospace;font-size:13px;"
        "padding:6px 4px;line-height:1.8'>" + "".join(parts) + "</div>"
    )

def _get_btn_states(completed_stages: list, mode: str) -> dict:
    """计算每个 stage 按钮的 interactive 和 variant。
    规则：stage 1 始终可点；其他 stage 需要前一个已完成才可点。
    已完成的 stage 按钮显示绿色（variant=primary）。
    返回 {stage_num: (interactive, variant)} 字典。
    """
    active = _MODE_STAGES.get(mode, _MODE_STAGES["standard"])
    completed_set = set(float(s) for s in completed_stages)
    result = {}
    for i, s in enumerate(active):
        done = float(s) in completed_set
        if i == 0:
            clickable = True
        else:
            prev = active[i - 1]
            clickable = float(prev) in completed_set
        result[s] = (clickable, "primary" if done else "secondary")
    for s in _ALL_STAGE_ORDER:
        if s not in result:
            result[s] = (False, "secondary")
    return result

def _clean_old_run_logs(log_base: Path, keep_n: int = 10) -> None:
    """Keep only the most recent keep_n run_*.log files."""
    logs = sorted(log_base.glob("run_*.log"), reverse=True)
    for old in logs[keep_n:]:
        try:
            old.unlink()
        except Exception:
            pass

def get_run_log_path(project_path: Path) -> Path:
    """返回带时间戳的日志文件路径，同时创建目录"""
    log_dir = project_path / ".veriflow" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _clean_old_run_logs(log_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"run_{ts}.log"

def load_latest_log(project_path: Path) -> str:
    """读取最近一次运行日志"""
    log_dir = project_path / ".veriflow" / "logs"
    if not log_dir.exists():
        return ""
    logs = sorted(log_dir.glob("run_*.log"), reverse=True)
    if not logs:
        return ""
    try:
        return logs[0].read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

# ============================================================================
# Claude 流式测试
# ============================================================================

def _format_stream_event(event) -> str:
    """把 stream-json 的一行事件格式化成可读文本，返回空串则跳过。"""
    if not isinstance(event, dict):
        return str(event)
    etype = event.get("type", "")

    if etype == "system":
        subtype = event.get("subtype", "")
        if subtype == "init":
            sid   = event.get("session_id", "")
            tools = event.get("tools", [])
            # tools 可能是字符串列表，也可能是对象列表
            tool_names = ", ".join(
                t if isinstance(t, str) else t.get("name", "?")
                for t in tools
            ) if tools else "—"
            cwd = event.get("cwd", "")
            return (f"🔧 [系统初始化]\n"
                    f"   session : {sid}\n"
                    f"   cwd     : {cwd}\n"
                    f"   工具    : {tool_names}")
        return f"🔧 [系统] {subtype}"

    elif etype == "assistant":
        msg   = event.get("message", {})
        usage = msg.get("usage", {})
        parts = []
        for block in msg.get("content", []):
            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    parts.append(f"💬 [Claude]\n{text}")
            elif btype == "tool_use":
                name = block.get("name", "?")
                tid  = block.get("id", "")
                inp  = block.get("input", {})
                inp_display = {}
                for k, v in inp.items():
                    s = str(v)
                    inp_display[k] = s if len(s) <= 400 else s[:400] + " …(截断)"
                inp_str = json.dumps(inp_display, ensure_ascii=False, indent=2)
                parts.append(f"🔨 [工具调用] {name}  (id={tid})\n{inp_str}")
        if usage:
            in_tok  = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            parts.append(f"   📊 tokens: in={in_tok} out={out_tok}")
        return "\n".join(parts)

    elif etype == "user":
        # 工具结果回传
        msg   = event.get("message", {})
        parts = []
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                tid      = block.get("tool_use_id", "")
                is_error = block.get("is_error", False)
                icon     = "❌" if is_error else "✅"
                contents = block.get("content", [])
                # content 可能是字符串或列表
                if isinstance(contents, str):
                    text = contents
                else:
                    texts = [c.get("text", "") for c in contents
                             if isinstance(c, dict) and c.get("type") == "text"]
                    text = "\n".join(texts)
                if len(text) > 600:
                    text = text[:600] + " …(截断)"
                parts.append(f"{icon} [工具结果]  (id={tid})\n{text}")
        return "\n".join(parts)

    elif etype == "result":
        subtype  = event.get("subtype", "")
        cost     = event.get("cost_usd")
        turns    = event.get("num_turns", "?")
        duration = event.get("duration_ms", 0)
        cost_str = f"  💰 ${cost:.4f}" if cost else ""
        dur_str  = f"  ⏱ {duration/1000:.1f}s" if duration else ""
        if subtype == "success":
            result = event.get("result", "")
            return (f"{'─'*40}\n"
                    f"✅ [完成]  turns={turns}{cost_str}{dur_str}\n"
                    f"{result}")
        else:
            error = event.get("error", event.get("result", ""))
            return (f"{'─'*40}\n"
                    f"❌ [失败]{cost_str}{dur_str}: {error}")

    # 其他未知事件：原样显示，方便排查新格式
    return f"[{etype}] {json.dumps(event, ensure_ascii=False)[:300]}"


def stream_claude_test(prompt_text: str, cli_path_override: str):
    """
    生成器函数：运行 claude --print --output-format stream-json，
    实时 yield 累积日志字符串给 Gradio Textbox。
    """
    import shutil

    cfg      = load_config()
    cli_path = (cli_path_override or "").strip() or cfg["claude"]["cli_path"].strip()

    # 自动检测
    if not cli_path:
        for name in ["claude", "claude.cmd", "claude.bat", "claude.exe"]:
            found = shutil.which(name)
            if found:
                cli_path = found
                break

    if not cli_path:
        yield "❌ 未找到 Claude CLI。\n请在「Agent 配置 → Claude」页填入路径后再试。"
        return

    if not prompt_text.strip():
        yield "⚠️ 请先输入测试 Prompt。"
        return

    cmd = [
        cli_path,
        "--print",
        "--dangerously-skip-permissions",
        "--verbose",
        "--output-format", "stream-json",
    ]

    log = f"▶ 命令: {' '.join(cmd)}\n{'─'*60}\n"
    yield log

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        proc.stdin.write(prompt_text)
        proc.stdin.close()

        for raw in proc.stdout:
            raw = raw.rstrip()
            if not raw:
                continue
            try:
                event     = json.loads(raw)
                formatted = _format_stream_event(event)
                if formatted:
                    log += formatted + "\n\n"
                    yield log
            except json.JSONDecodeError:
                log += raw + "\n"
                yield log
            except Exception as e:
                log += f"[解析错误 {e}] {raw[:200]}\n"
                yield log

        proc.wait()
        log += f"{'─'*60}\n⏹ 进程退出，exit code = {proc.returncode}"
        yield log

    except FileNotFoundError:
        yield log + f"\n❌ 找不到可执行文件: {cli_path}"
    except Exception as exc:
        yield log + f"\n❌ 异常: {exc}"


# ============================================================================
# UI 构建
# ============================================================================

def create_ui() -> gr.Blocks:

    cfg = load_config()
    # 用配置初始化 app_state 的工作目录
    app_state.working_dir = Path(cfg["working_dir"])

    # 恢复上次项目
    _init_projects = scan_projects(app_state.working_dir)
    _last_project   = cfg.get("last_project", "")
    _init_project_value = _last_project if _last_project in _init_projects else "(新建项目)"

    custom_css = """
    .sidebar-col {
        background: #f4f5f7;
        border-right: 1px solid #dde1e7;
        padding: 8px !important;
        min-height: 92vh;
    }
    .nav-btn button {
        width: 100%;
        text-align: left !important;
        justify-content: flex-start !important;
        border-radius: 6px !important;
        margin: 2px 0 !important;
        padding: 9px 14px !important;
        font-size: 14px !important;
        border: none !important;
        background: transparent !important;
        color: #444 !important;
    }
    .nav-btn button:hover {
        background: #e2e6ea !important;
    }
    .nav-active button {
        background: linear-gradient(135deg, #667eea, #764ba2) !important;
        color: white !important;
    }
    .page-title {
        font-size: 20px;
        font-weight: 700;
        color: #2d3748;
        border-bottom: 2px solid #667eea;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }

    #log_output textarea {
        font-family: "Consolas", "Courier New", monospace !important;
        font-size: 14px !important;
        line-height: 1.6 !important;
        background-color: #f8fafc !important;
        color: #1e293b !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06) !important;
    }

    #log_output textarea::placeholder {
        color: #94a3b8 !important;
    }

    /* 优化日志过滤效果 */
    .gr-dataset {
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    """

    PAGE_COUNT = 6

    with gr.Blocks(title="VeriFlow 8.2") as demo:

        # ── 顶部横幅 ──────────────────────────────────────────────────────────
        gr.HTML("""
        <div style="background:linear-gradient(135deg,#667eea,#764ba2);
                    color:white;padding:12px 20px;border-radius:8px;
                    margin-bottom:10px;display:flex;align-items:center;gap:12px;">
            <span style="font-size:26px">🚀</span>
            <div>
                <div style="font-size:18px;font-weight:700">VeriFlow 8.2</div>
                <div style="font-size:12px;opacity:.85">工业级 Verilog RTL 设计流水线 — 控制权反转架构</div>
            </div>
        </div>
        """)

        with gr.Row(equal_height=False):

            # ══════════════════════════════════════════════════════════════════
            # 左侧导航栏（始终可见）
            # ══════════════════════════════════════════════════════════════════
            with gr.Column(scale=1, elem_classes=["sidebar-col"]):

                # 工作目录（全局，所有页面共用）
                gr.Markdown("**📁 工作目录**", container=False)
                working_dir_input = gr.Textbox(
                    value=cfg["working_dir"],
                    placeholder="项目根目录路径",
                    show_label=False,
                    lines=1
                )
                with gr.Row():
                    browse_btn  = gr.Button("📂 浏览", size="sm", scale=2)
                    refresh_btn = gr.Button("🔄",      size="sm", scale=1)

                project_dropdown = gr.Dropdown(
                    label="当前项目",
                    choices=["(新建项目)"] + _init_projects,
                    value=_init_project_value
                )

                gr.HTML("<hr style='margin:8px 0;border-color:#dde1e7'>")
                gr.Markdown("**导航**", container=False)

                btn_project  = gr.Button("🏠 项目管理",  elem_classes=["nav-btn", "nav-active"], size="sm")
                btn_req      = gr.Button("📝 设计需求",  elem_classes=["nav-btn"], size="sm")
                btn_env      = gr.Button("⚙️ 环境配置",  elem_classes=["nav-btn"], size="sm")
                btn_agent    = gr.Button("🤖 Agent配置", elem_classes=["nav-btn"], size="sm")
                btn_pipeline = gr.Button("▶️ 运行流水线", elem_classes=["nav-btn"], size="sm")
                btn_files    = gr.Button("📁 生成文件",  elem_classes=["nav-btn"], size="sm")

                gr.HTML("<hr style='margin:8px 0;border-color:#dde1e7'>")
                gr.Markdown("**流水线控制**", container=False)

                with gr.Row():
                    run_btn  = gr.Button("🚀 全部执行", variant="primary", size="sm", scale=2)
                    stop_btn = gr.Button("⏹️ 停止", variant="stop",    size="sm", scale=1, visible=False)

                progress_bar  = gr.Slider(label="进度", minimum=0, maximum=100, value=0, step=1, interactive=False)
                current_stage = gr.Textbox(label="当前阶段", value="就绪", interactive=False, lines=1)

            # ══════════════════════════════════════════════════════════════════
            # 右侧内容区（多页面，互斥显示）
            # ══════════════════════════════════════════════════════════════════
            with gr.Column(scale=4):

                # ─── 页面 0：项目管理 ────────────────────────────────────────
                with gr.Column(visible=True) as page_project:
                    gr.HTML('<div class="page-title">🏠 项目管理</div>')

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 新建 / 初始化项目")
                            new_project_name = gr.Textbox(label="项目名称", placeholder="如: my_counter")
                            with gr.Row():
                                mode_dropdown = gr.Dropdown(
                                    label="执行模式",
                                    choices=["quick", "standard", "enterprise"],
                                    value="quick"
                                )
                                target_freq = gr.Number(
                                    label="目标频率 (MHz)", value=300, minimum=10, maximum=1000
                                )
                            create_btn     = gr.Button("📂 创建项目", variant="primary")
                            project_status = gr.Textbox(label="状态", value="就绪", interactive=False)

                        with gr.Column(scale=1):
                            gr.Markdown("### 工作目录说明")
                            gr.Markdown("""
在左侧**工作目录**输入框修改路径后按 **Enter** 或点击 🔄，
即可切换到不同的项目根目录。

**项目目录结构：**
```
<project>/
├── requirement.md     ← 设计需求
├── .veriflow/         ← 配置文件
└── workspace/
    ├── docs/          ← 当前工作文档（spec / timing / report）
    ├── rtl/           ← 当前 RTL
    ├── tb/            ← 当前测试台
    ├── sim/           ← 当前仿真输出
    └── stages/        ← 按 stage 归档的扁平结果目录
```
                            """)

                # ─── 页面 1：设计需求 ────────────────────────────────────────
                with gr.Column(visible=False) as page_req:
                    gr.HTML('<div class="page-title">📝 设计需求</div>')

                    with gr.Tabs():
                        with gr.TabItem("📝 文本输入"):
                            requirement_text = gr.TextArea(
                                label="需求描述 (Markdown 格式)",
                                placeholder=(
                                    "# 设计需求\n\n## 概述\n...\n\n"
                                    "## 功能需求\n- 功能1\n\n"
                                    "## 接口定义\n- 输入：...\n- 输出：..."
                                ),
                                lines=20
                            )

                        with gr.TabItem("📤 文件上传"):
                            file_upload = gr.File(
                                label="上传需求文档",
                                file_types=[".md", ".txt", ".docx", ".pdf"]
                            )
                            uploaded_content = gr.TextArea(
                                label="文件内容预览", lines=14, interactive=False
                            )

                        with gr.TabItem("📋 模板"):
                            template_dropdown = gr.Dropdown(
                                label="选择模板",
                                choices=[
                                    "计数器 (Counter)", "移位寄存器 (Shift Register)",
                                    "简单状态机 (FSM)", "FIFO 缓冲区",
                                    "加法器/乘法器", "UART 收发器"
                                ],
                                value="计数器 (Counter)"
                            )
                            template_preview = gr.TextArea(
                                label="模板预览",
                                value="# 4-bit Counter\n\n## Overview\nDesign a 4-bit synchronous counter with:\n- Active-high synchronous reset\n- Count enable\n- Carry output\n\n## Requirements\n- Width: 4 bits\n- Max count: 15\n- Wrap around: Yes\n",
                                lines=12, interactive=False
                            )
                            apply_template_btn = gr.Button("应用模板", size="sm")

                    with gr.Row():
                        save_req_btn  = gr.Button("💾 保存需求", variant="primary")
                        clear_req_btn = gr.Button("🗑️ 清空")
                    req_status = gr.Textbox(label="状态", value="", interactive=False)

                # ─── 页面 2：环境配置 ────────────────────────────────────────
                with gr.Column(visible=False) as page_env:
                    gr.HTML('<div class="page-title">⚙️ 环境配置</div>')

                    gr.Markdown("### 🔧 EDA 工具路径")
                    with gr.Row():
                        iverilog_path = gr.Textbox(label="iverilog 路径", placeholder="自动检测或手动输入", value=cfg["env"]["iverilog_path"])
                        vvp_path      = gr.Textbox(label="vvp 路径",      placeholder="自动检测或手动输入", value=cfg["env"]["vvp_path"])
                        yosys_path    = gr.Textbox(label="yosys 路径 (可选)", placeholder="自动检测或手动输入", value=cfg["env"]["yosys_path"])

                    with gr.Row():
                        auto_detect_btn = gr.Button("🔍 自动检测", variant="secondary")
                        check_tools_btn = gr.Button("✅ 验证工具",  variant="primary")

                    tools_status = gr.TextArea(
                        label="工具检测报告",
                        value="点击「验证工具」开始检测",
                        lines=8, interactive=False
                    )

                    gr.Markdown("### 📊 高级选项")
                    with gr.Row():
                        max_retries = gr.Number(label="最大重试次数", value=cfg["env"]["max_retries"],   minimum=1,  maximum=10,   step=1)
                        timeout     = gr.Number(label="超时 (秒)",    value=cfg["env"]["timeout"], minimum=60, maximum=3600, step=60)
                        auto_save   = gr.Checkbox(label="自动保存", value=cfg["env"]["auto_save"])
                        verbose     = gr.Checkbox(label="详细输出",  value=cfg["env"]["verbose"])

                    with gr.Row():
                        save_env_btn    = gr.Button("💾 保存环境配置", variant="primary")
                        env_save_status = gr.Textbox(label="", value="", interactive=False, scale=3)

                # ─── 页面 3：Agent 配置 ──────────────────────────────────────
                with gr.Column(visible=False) as page_agent:
                    gr.HTML('<div class="page-title">🤖 Agent 配置</div>')

                    with gr.Tabs():

                        with gr.TabItem("🤖 Claude"):
                            gr.Markdown("### Claude CLI 配置")
                            with gr.Row():
                                claude_cli_path = gr.Textbox(
                                    label="Claude CLI 路径",
                                    placeholder="自动检测或手动输入 claude 命令路径",
                                    value=cfg["claude"]["cli_path"],
                                    scale=3
                                )
                                claude_browse_btn  = gr.Button("📂 浏览",   size="sm", scale=1)
                                claude_detect_btn  = gr.Button("🔍 自动检测", size="sm", scale=1)
                            claude_detect_status = gr.Textbox(label="检测结果", value="", interactive=False, lines=3)
                            use_mock = gr.Checkbox(
                                label="使用模拟模式 (无需 Claude CLI)", value=cfg["claude"]["use_mock"]
                            )
                            mock_delay = gr.Slider(
                                label="模拟延迟 (秒)", minimum=0, maximum=10, value=cfg["claude"]["mock_delay"], step=0.5
                            )
                            gr.Markdown("""
**说明：**
- **生产模式**：取消勾选「模拟模式」，确保 `claude` 命令可用
- **模拟模式**：用于测试 GUI 流程，不调用真实 LLM
                            """)
                            with gr.Row():
                                save_claude_btn    = gr.Button("💾 保存 Claude 配置", variant="primary")
                                claude_save_status = gr.Textbox(label="", value="", interactive=False, scale=3)

                        with gr.TabItem("🧠 Codex (OpenAI)"):
                            gr.Markdown("### OpenAI Codex / GPT 配置")
                            codex_api_key = gr.Textbox(
                                label="API Key", placeholder="sk-...", type="password",
                                value=cfg["codex"]["api_key"]
                            )
                            with gr.Row():
                                codex_model = gr.Dropdown(
                                    label="模型",
                                    choices=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o3-mini", "codex-mini-latest"],
                                    value=cfg["codex"]["model"]
                                )
                                codex_endpoint = gr.Textbox(
                                    label="API Endpoint", value=cfg["codex"]["endpoint"]
                                )
                            codex_system_prompt = gr.TextArea(
                                label="System Prompt (可选，留空使用 VeriFlow 默认)",
                                placeholder="覆盖默认 system prompt...",
                                lines=5, value=cfg["codex"]["system_prompt"]
                            )
                            with gr.Row():
                                codex_max_tokens  = gr.Number(
                                    label="Max Tokens", value=cfg["codex"]["max_tokens"], minimum=256, maximum=128000, step=256
                                )
                                codex_temperature = gr.Slider(
                                    label="Temperature", minimum=0, maximum=2, value=cfg["codex"]["temperature"], step=0.05
                                )
                            with gr.Row():
                                save_codex_btn = gr.Button("💾 保存 Codex 配置", variant="primary")
                                codex_status   = gr.Textbox(label="", value="", interactive=False, scale=3)

                        with gr.TabItem("🔗 OpenAI 兼容接口"):
                            gr.Markdown("### 任意 OpenAI 兼容推理服务")
                            compat_endpoint = gr.Textbox(
                                label="Endpoint URL",
                                placeholder="http://localhost:11434/v1",
                                value=cfg["compat"]["endpoint"]
                            )
                            compat_api_key = gr.Textbox(
                                label="API Key (Ollama/LM Studio 留空)",
                                type="password",
                                value=cfg["compat"]["api_key"]
                            )
                            compat_model = gr.Textbox(
                                label="Model Name",
                                placeholder="如: llama3, deepseek-coder, qwen2.5-coder",
                                value=cfg["compat"]["model"]
                            )
                            gr.Markdown("_适用于 Ollama、LM Studio、vLLM、LocalAI 等本地推理服务_")
                            with gr.Row():
                                save_compat_btn    = gr.Button("💾 保存兼容接口配置", variant="primary")
                                compat_save_status = gr.Textbox(label="", value="", interactive=False, scale=3)

                        with gr.TabItem("🧪 流式测试"):
                            gr.Markdown(
                                "### Claude stream-json 流式测试\n"
                                "验证 `--output-format stream-json` 模式下工具调用是否实时可见。"
                            )
                            test_cli_path = gr.Textbox(
                                label="Claude CLI 路径（留空则自动检测）",
                                placeholder="留空 = 使用 Agent 配置中的路径",
                                value="",
                            )
                            test_prompt = gr.TextArea(
                                label="测试 Prompt",
                                value="请用 Write 工具在当前目录创建一个名为 hello.txt 的文件，内容为 'hello from stream-json test'，然后用 Read 工具读取并确认内容。",
                                lines=4,
                            )
                            with gr.Row():
                                test_run_btn   = gr.Button("▶ 运行测试", variant="primary", scale=2)
                                test_clear_btn = gr.Button("🗑 清空", scale=1)
                            test_log = gr.Textbox(
                                label="实时输出（工具调用可见）",
                                value="",
                                lines=25,
                                max_lines=50,
                                interactive=False,
                            )

                # ─── 页面 4：运行流水线 ──────────────────────────────────────
                with gr.Column(visible=False) as page_pipeline:
                    gr.HTML('<div class="page-title">▶️ 运行流水线</div>')

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 运行参数")
                            run_mode_display = gr.Textbox(
                                label="执行模式（在「项目管理」中设置）",
                                value="quick", interactive=False
                            )
                            max_workers_slider = gr.Slider(
                                label="S3 并行 Worker 数",
                                minimum=1, maximum=8, step=1, value=4,
                                info="Stage 3 同时启动的 Claude 子进程数量"
                            )
                            with gr.Row():
                                pause_btn  = gr.Button("⏸️ 暂停", visible=False)
                                resume_btn = gr.Button("▶️ 继续", visible=False)
                            eta_display = gr.Textbox(label="预计剩余时间", value="--:--", interactive=False)

                            gr.HTML("<hr style='margin:8px 0'>")
                            gr.Markdown("### 按阶段执行")
                            stage_status_html = gr.HTML(
                                value=_render_stage_status([], "standard"),
                                label=""
                            )
                            with gr.Row():
                                stage1_btn  = gr.Button("S1: 架构规格", size="sm", variant="secondary")
                                stage15_btn = gr.Button("S1.5: 微架构", size="sm", variant="secondary")
                            with gr.Row(visible=False) as stage2_row:
                                stage2_btn  = gr.Button("S2: 时序模型", size="sm", variant="secondary")
                            with gr.Row():
                                stage3_btn  = gr.Button("S3: RTL生成",  size="sm", variant="secondary")
                                stage35_btn = gr.Button("S3.5: Lint+分析", size="sm", variant="secondary")
                            with gr.Row(visible=False) as stage45_row:
                                stage4_btn  = gr.Button("S4: 仿真验证", size="sm", variant="secondary")
                                stage5_btn  = gr.Button("S5: 综合KPI",  size="sm", variant="secondary")

                        with gr.Column(scale=3):
                            gr.Markdown("### 📝 实时日志")
                            with gr.Row():
                                log_filter = gr.Dropdown(
                                    label="日志级别",
                                    choices=["全部", "信息", "成功", "警告", "错误", "阶段"],
                                    value="全部", scale=3
                                )
                                clear_logs_btn = gr.Button("🗑️ 清除", size="sm", scale=1)
                            log_output = gr.HTML(
                                label="",
                                value="<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
                                       "<div style='color:#8b949e'>等待启动流水线...</div></div>",
                                elem_id="log_output"
                            )

                            # ── Review Gate Panel (hidden until stage completes) ──
                            with gr.Group(visible=False) as review_panel:
                                gr.Markdown("---")
                                review_title = gr.Markdown("## ⏸ 审查生成结果")
                                review_preview = gr.Code(
                                    label="生成内容预览",
                                    language="json",
                                    lines=20,
                                    interactive=False,
                                )
                                review_feedback = gr.Textbox(
                                    label="📝 反馈意见（如无修改意见请留空，直接点「批准并继续」）",
                                    placeholder="例如：stage3 中 uart_tx 模块的 FSM 状态转换有误，应在 i_valid=1 时从 IDLE 进入 WORK...",
                                    lines=4,
                                )
                                # Stage 3 专属：勾选哪些模块需要重新生成
                                with gr.Group(visible=False) as modules_group:
                                    modules_checkboxes = gr.CheckboxGroup(
                                        label="🔁 选择需要重新生成的模块（留空 = 全部重新生成）",
                                        choices=[],
                                        value=[],
                                        interactive=True,
                                    )
                                with gr.Row():
                                    approve_btn = gr.Button("✅ 批准并继续下一 Stage", variant="primary", scale=2)
                                    reject_btn  = gr.Button("🔄 提交反馈并重新生成", variant="secondary", scale=1)

                # ─── 页面 5：生成文件 ────────────────────────────────────────
                with gr.Column(visible=False) as page_files:
                    gr.HTML('<div class="page-title">📁 生成文件</div>')

                    with gr.Row():
                        refresh_files_btn = gr.Button("🔄 刷新文件列表", variant="secondary")
                        open_dir_btn      = gr.Button("📂 打开目录")

                    with gr.Row():
                        with gr.Column(scale=1):
                            file_list = gr.Dataframe(
                                headers=["文件", "类型", "大小", "修改时间", "目录"],
                                value=[],
                                interactive=False,
                                wrap=True
                            )
                            file_selector = gr.Dropdown(
                                label="选择预览文件", choices=[], value=None
                            )

                        with gr.Column(scale=2):
                            preview_file = gr.TextArea(
                                label="文件预览", lines=28, interactive=False
                            )

        # ======================================================================
        # 导航切换逻辑
        # ======================================================================
        all_pages = [page_project, page_req, page_env, page_agent, page_pipeline, page_files]

        def _show(idx):
            return [gr.update(visible=(i == idx)) for i in range(PAGE_COUNT)]

        btn_project .click(fn=lambda: _show(0), outputs=all_pages)
        btn_req     .click(fn=lambda: _show(1), outputs=all_pages)
        btn_env     .click(fn=lambda: _show(2), outputs=all_pages)
        btn_agent   .click(fn=lambda: _show(3), outputs=all_pages)
        btn_pipeline.click(fn=lambda: _show(4), outputs=all_pages)
        btn_files   .click(fn=lambda: _show(5), outputs=all_pages)

        # ======================================================================
        # 工作目录变更 → 刷新项目列表
        # ======================================================================
        def browse_folder():
            """打开系统文件夹选择对话框（本地运行专用）"""
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes("-topmost", 1)
                folder = filedialog.askdirectory(title="选择工作目录")
                root.destroy()
                if folder:
                    p = Path(folder)
                    app_state.working_dir = p
                    c = load_config()
                    c["working_dir"] = str(p)
                    save_config(c)
                    projects = scan_projects(p)
                    return str(p), gr.Dropdown(choices=["(新建项目)"] + projects, value="(新建项目)")
            except Exception:
                pass
            return gr.update(), gr.update()

        browse_btn.click(fn=browse_folder, outputs=[working_dir_input, project_dropdown])

        def on_working_dir_change(working_dir):
            try:
                p = Path(working_dir)
                app_state.working_dir = p
                c = load_config()
                c["working_dir"] = str(p)
                save_config(c)
                projects = scan_projects(p)
                return gr.Dropdown(choices=["(新建项目)"] + projects, value="(新建项目)")
            except Exception:
                return gr.Dropdown(choices=["(新建项目)"], value="(新建项目)")

        working_dir_input.submit(fn=on_working_dir_change, inputs=[working_dir_input], outputs=[project_dropdown])
        refresh_btn.click(fn=on_working_dir_change, inputs=[working_dir_input], outputs=[project_dropdown])

        # ======================================================================
        # 创建项目
        # ======================================================================
        def create_project(working_dir, project_name, mode, freq_val):
            if not project_name or project_name == "(新建项目)":
                return "❌ 请输入有效的项目名称", gr.update()
            try:
                project_path = Path(working_dir) / project_name
                if create_project_structure(project_path, mode, int(freq_val)):
                    app_state.current_project = project_name
                    app_state.working_dir = Path(working_dir)
                    projects = scan_projects(Path(working_dir))
                    # 保存 last_project
                    c = load_config()
                    c["working_dir"] = working_dir
                    c["last_project"] = project_name
                    save_config(c)
                    return f"✅ 项目 '{project_name}' 创建成功！", gr.Dropdown(choices=["(新建项目)"] + projects, value=project_name)
                return "❌ 创建项目结构失败", gr.update()
            except Exception as e:
                return f"❌ 创建失败: {str(e)}", gr.update()

        create_btn.click(
            fn=create_project,
            inputs=[working_dir_input, new_project_name, mode_dropdown, target_freq],
            outputs=[project_status, project_dropdown]
        )

        # ======================================================================
        # 切换项目 → 自动恢复上次会话（日志 + 进度 + 文件列表）
        # ======================================================================
        def on_project_select(working_dir, project_name):
            if not project_name or project_name == "(新建项目)":
                empty_btns = [gr.update(interactive=True)] + [gr.update(interactive=False)] * 6
                return ("", "就绪", 0, [], gr.Dropdown(choices=[], value=None), "",
                        gr.update(), gr.update(), _render_stage_status([], "standard"), *empty_btns)
            project_path = Path(working_dir) / project_name
            # 恢复状态
            state = load_project_state(project_path)
            restored_stage    = state.get("current_stage", "就绪")
            restored_progress = int(state.get("progress", 0))
            completed_stages  = state.get("completed_stages", [])
            # 恢复模式：优先 project_state，其次 project_config
            restored_mode = state.get("mode", "")
            if not restored_mode:
                try:
                    cfg_file = project_path / ".veriflow" / "project_config.json"
                    if cfg_file.exists():
                        restored_mode = json.loads(cfg_file.read_text(encoding="utf-8")).get("mode", "standard")
                except Exception:
                    pass
            if not restored_mode:
                restored_mode = "standard"
            # 恢复日志
            restored_logs = load_latest_log(project_path)
            if not restored_logs and state:
                ts = state.get("last_run", "")
                mode_info = state.get("mode", "")
                restored_logs = (
                    f"[上次会话] 时间: {ts}  模式: {mode_info}  状态: {state.get('status','')}\n"
                    f"[上次会话] 进度: {restored_progress}%  阶段: {restored_stage}\n"
                )
            # 恢复文件列表
            files = scan_generated_files(project_path)
            names = [f["文件"] for f in files]
            # 加载 requirement.md
            req_content = ""
            req_file = project_path / "requirement.md"
            if req_file.exists():
                try:
                    req_content = req_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            # 保存 last_project
            _c = load_config()
            _c["last_project"] = project_name
            save_config(_c)
            # 计算按钮状态
            btn_states = _get_btn_states(completed_stages, restored_mode)
            stage_order = [1, 1.5, 2, 3, 3.5, 4, 5]
            btn_updates = [
                gr.update(interactive=btn_states.get(float(s), (False, "secondary"))[0],
                          variant=btn_states.get(float(s), (False, "secondary"))[1])
                for s in stage_order
            ]
            return (
                restored_logs,
                restored_stage,
                restored_progress,
                files,
                gr.Dropdown(choices=names, value=names[0] if names else None),
                req_content,
                gr.update(value=restored_mode),
                gr.update(value=restored_mode),
                _render_stage_status(completed_stages, restored_mode),
                *btn_updates,
            )

        project_dropdown.change(
            fn=on_project_select,
            inputs=[working_dir_input, project_dropdown],
            outputs=[log_output, current_stage, progress_bar, file_list, file_selector, requirement_text,
                     mode_dropdown, run_mode_display, stage_status_html,
                     stage1_btn, stage15_btn, stage2_btn, stage3_btn, stage35_btn, stage4_btn, stage5_btn]
        )

        # ======================================================================
        # 保存需求
        # ======================================================================
        def save_req(working_dir, project_name, content):
            if not project_name or project_name == "(新建项目)":
                return "❌ 请先选择或创建项目"
            try:
                req_file = Path(working_dir) / project_name / "requirement.md"
                req_file.write_text(content, encoding="utf-8")
                return f"✅ 已保存到 {req_file}"
            except Exception as e:
                return f"❌ 保存失败: {str(e)}"

        save_req_btn .click(fn=save_req, inputs=[working_dir_input, project_dropdown, requirement_text], outputs=[req_status])
        clear_req_btn.click(fn=lambda: "", outputs=[requirement_text])

        # 模板下拉切换 → 更新预览
        TEMPLATES = {
            "计数器 (Counter)": "# 4-bit Counter\n\n## Overview\nDesign a 4-bit synchronous counter with:\n- Active-high synchronous reset\n- Count enable\n- Carry output\n\n## Requirements\n- Width: 4 bits\n- Max count: 15\n- Wrap around: Yes\n",
            "移位寄存器 (Shift Register)": "# Shift Register\n\n## Overview\nDesign an 8-bit shift register with:\n- Serial/Parallel input\n- Serial/Parallel output\n- Left/Right shift control\n\n## Requirements\n- Width: 8 bits\n- Synchronous load\n- Active-low reset\n",
            "简单状态机 (FSM)": "# Traffic Light FSM\n\n## Overview\nDesign a 3-state traffic light controller:\n- States: RED, GREEN, YELLOW\n- Fixed timing for each state\n\n## Requirements\n- Clock: 1 Hz\n- Output: 3-bit one-hot\n- Async reset to RED\n",
            "FIFO 缓冲区": "# Synchronous FIFO\n\n## Overview\nDesign a 16-deep x 8-bit synchronous FIFO:\n- Full/Empty flags\n- Write/Read pointers\n\n## Requirements\n- Depth: 16\n- Width: 8 bits\n- Single clock domain\n- Gray-code pointers\n",
            "加法器/乘法器": "# 32-bit Adder/Multiplier\n\n## Overview\nDesign a 32-bit arithmetic unit:\n- Ripple-carry adder\n- Optional pipelined multiplier\n\n## Requirements\n- Width: 32 bits\n- Signed/Unsigned support\n- Overflow flag\n",
            "UART 收发器": "# UART Transceiver\n\n## Overview\nDesign a full-duplex UART with:\n- Configurable baud rate\n- 8N1 frame format\n- TX/RX FIFOs\n\n## Requirements\n- Baud: 115200\n- Clock: 50 MHz\n- FIFO depth: 16\n",
        }

        template_dropdown.change(
            fn=lambda name: TEMPLATES.get(name, ""),
            inputs=[template_dropdown],
            outputs=[template_preview]
        )
        # 应用模板 → 写入编辑器
        apply_template_btn.click(
            fn=lambda name: TEMPLATES.get(name, ""),
            inputs=[template_dropdown],
            outputs=[requirement_text]
        )

        # 文件上传 → 同步到编辑器 + 预览
        def handle_file_upload(file_obj):
            if file_obj is None:
                return "", ""
            try:
                content = Path(file_obj.name).read_text(encoding="utf-8", errors="replace")[:20000]
                return content, content   # → requirement_text, uploaded_content
            except Exception as e:
                err = f"读取文件失败: {str(e)}"
                return err, err

        file_upload.change(
            fn=handle_file_upload,
            inputs=[file_upload],
            outputs=[requirement_text, uploaded_content]
        )

        # ======================================================================
        # 工具检测（修复：同时检查 stdout + stderr）
        # ======================================================================
        def _run_tool_check(cmd_path: str, tool_name: str, flag: str = "-V") -> str:
            cmd = cmd_path.strip() if cmd_path and cmd_path.strip() else tool_name
            try:
                r = subprocess.run(
                    [cmd, flag], capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="replace"
                )
                # iverilog → stdout；vvp/yosys 有时输出到 stderr
                out = (r.stdout or r.stderr or "").strip()
                ver = out.split('\n')[0][:100] if out else "已找到（无法获取版本号）"
                return f"✅ {tool_name}: {ver}"
            except FileNotFoundError:
                return f"❌ {tool_name}: 未找到，请检查路径或 PATH 环境变量"
            except Exception as e:
                return f"❌ {tool_name}: {str(e)[:80]}"

        def check_tools(iverilog, vvp, yosys):
            lines = ["🔍 工具检查报告", "=" * 50]
            lines.append(_run_tool_check(iverilog, "iverilog", "-V"))
            lines.append(_run_tool_check(vvp,      "vvp",      "-V"))
            if yosys and yosys.strip():
                lines.append(_run_tool_check(yosys, "yosys", "-V"))
            else:
                lines.append("ℹ️ yosys: 未配置（可选工具）")
            lines.append("=" * 50)
            return "\n".join(lines)

        check_tools_btn.click(fn=check_tools, inputs=[iverilog_path, vvp_path, yosys_path], outputs=[tools_status])

        # 自动检测工具
        def auto_detect_tools():
            search_paths = os.environ.get("PATH", "").split(os.pathsep)
            search_paths += [
                "/usr/bin", "/usr/local/bin",
                "/opt/oss-cad-suite/bin", "/opt/homebrew/bin",
                "C:/oss-cad-suite/bin",
                str(Path.home() / "oss-cad-suite" / "bin")
            ]
            found = {}
            for tool in ["iverilog", "vvp", "yosys"]:
                for path in search_paths:
                    for suffix in ["", ".exe"]:
                        exe = Path(path) / (tool + suffix)
                        if exe.exists():
                            found[tool] = str(exe)
                            break
                    if tool in found:
                        break
            return found.get("iverilog", ""), found.get("vvp", ""), found.get("yosys", "")

        auto_detect_btn.click(fn=auto_detect_tools, outputs=[iverilog_path, vvp_path, yosys_path])

        # ======================================================================
        # 配置保存事件
        # ======================================================================

        def _current_cfg(working_dir):
            """读取当前配置文件，注入最新 working_dir 后返回"""
            c = load_config()
            c["working_dir"] = working_dir
            return c

        # 工作目录变更时自动保存
        def _save_working_dir(working_dir):
            c = load_config()
            c["working_dir"] = working_dir
            return save_config(c)

        # 保存环境配置
        def do_save_env(working_dir, iv, vv, yo, retries, tout, asave, verb):
            c = _current_cfg(working_dir)
            c["env"] = {
                "iverilog_path": iv, "vvp_path": vv, "yosys_path": yo,
                "max_retries": int(retries), "timeout": int(tout),
                "auto_save": asave, "verbose": verb
            }
            return save_config(c)

        save_env_btn.click(
            fn=do_save_env,
            inputs=[working_dir_input, iverilog_path, vvp_path, yosys_path,
                    max_retries, timeout, auto_save, verbose],
            outputs=[env_save_status]
        )

        # 保存 Claude 配置
        def do_save_claude(working_dir, cli_path, mock, delay):
            c = _current_cfg(working_dir)
            c["claude"] = {"cli_path": cli_path, "use_mock": mock, "mock_delay": float(delay)}
            return save_config(c)

        save_claude_btn.click(
            fn=do_save_claude,
            inputs=[working_dir_input, claude_cli_path, use_mock, mock_delay],
            outputs=[claude_save_status]
        )

        # Claude CLI 浏览
        def browse_claude_cli():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes("-topmost", 1)
                path = filedialog.askopenfilename(
                    title="选择 Claude CLI 可执行文件",
                    filetypes=[("可执行文件", "*.exe *.cmd *.bat *"), ("所有文件", "*.*")]
                )
                root.destroy()
                if path:
                    return path, f"✅ 已选择: {path}"
            except Exception as e:
                return gr.update(), f"❌ 打开文件对话框失败: {e}"
            return gr.update(), ""

        claude_browse_btn.click(fn=browse_claude_cli, outputs=[claude_cli_path, claude_detect_status])

        # Claude CLI 自动检测
        def detect_claude_cli():
            lines = ["🔍 自动检测 Claude CLI...", ""]
            candidates = []

            # 1. PATH 中搜索
            import shutil
            for name in ["claude", "claude.exe", "claude.cmd"]:
                found = shutil.which(name)
                if found:
                    candidates.append(found)

            # 2. 常见安装位置
            common = [
                Path.home() / ".claude" / "local" / "claude",
                Path.home() / ".claude" / "local" / "claude.exe",
                Path.home() / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
                Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
                Path.home() / "AppData" / "Roaming" / "npm" / "claude",
                Path("/usr/local/bin/claude"),
                Path("/opt/homebrew/bin/claude"),
            ]
            for p in common:
                if p.exists() and str(p) not in candidates:
                    candidates.append(str(p))

            if candidates:
                best = candidates[0]
                # 验证可执行（.cmd/.bat 在 Windows 需要 cmd /c）
                try:
                    import platform as _platform
                    if _platform.system() == "Windows" and best.lower().endswith((".cmd", ".bat")):
                        ver_cmd = ["cmd", "/c", best, "--version"]
                    else:
                        ver_cmd = [best, "--version"]
                    r = subprocess.run(
                        ver_cmd, capture_output=True, text=True, timeout=5,
                        encoding="utf-8", errors="replace"
                    )
                    ver = (r.stdout or r.stderr or "").strip().split('\n')[0][:80]
                    lines.append(f"✅ 找到: {best}")
                    lines.append(f"   版本: {ver}")
                    if len(candidates) > 1:
                        lines.append(f"   其他候选: {', '.join(candidates[1:])}")
                    return best, "\n".join(lines)
                except Exception as e:
                    lines.append(f"⚠️ 找到路径但验证失败: {best}")
                    lines.append(f"   错误: {str(e)[:60]}")
                    return best, "\n".join(lines)
            else:
                lines.append("❌ 未找到 Claude CLI")
                lines.append("   请确认已安装：npm install -g @anthropic-ai/claude-code")
                lines.append("   或手动点击「📂 浏览」指定路径")
                return gr.update(), "\n".join(lines)

        claude_detect_btn.click(fn=detect_claude_cli, outputs=[claude_cli_path, claude_detect_status])

        # 保存 Codex 配置
        def do_save_codex(working_dir, api_key, model, endpoint, sys_prompt, max_tok, temp):
            c = _current_cfg(working_dir)
            c["codex"] = {
                "api_key": api_key, "model": model, "endpoint": endpoint,
                "system_prompt": sys_prompt, "max_tokens": int(max_tok), "temperature": float(temp)
            }
            return save_config(c)

        save_codex_btn.click(
            fn=do_save_codex,
            inputs=[working_dir_input, codex_api_key, codex_model, codex_endpoint,
                    codex_system_prompt, codex_max_tokens, codex_temperature],
            outputs=[codex_status]
        )

        # 保存兼容接口配置
        def do_save_compat(working_dir, ep, key, model):
            c = _current_cfg(working_dir)
            c["compat"] = {"endpoint": ep, "api_key": key, "model": model}
            return save_config(c)

        save_compat_btn.click(
            fn=do_save_compat,
            inputs=[working_dir_input, compat_endpoint, compat_api_key, compat_model],
            outputs=[compat_save_status]
        )

        # ── 流式测试 ──────────────────────────────────────────────────────────
        test_run_btn.click(
            fn=stream_claude_test,
            inputs=[test_prompt, test_cli_path],
            outputs=[test_log],
        )
        test_clear_btn.click(fn=lambda: "", outputs=[test_log])

        # ======================================================================
        # ======================================================================
        # 辅助：获取 stage 审查内容（文件预览）
        # ======================================================================
        def _get_review_content(project_path: Path, stage_num: int) -> str:
            """Return a short preview string shown in the review panel."""
            try:
                if stage_num == 1:
                    spec = project_path / "workspace" / "docs" / "spec.json"
                    if spec.exists():
                        return spec.read_text(encoding="utf-8", errors="replace")[:6000]
                    return "(spec.json 未找到)"
                elif stage_num == 3:
                    rtl_dir = project_path / "workspace" / "rtl"
                    files = sorted(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
                    if not files:
                        return "(无 .v 文件)"
                    preview = f"# 共生成 {len(files)} 个 RTL 文件:\n"
                    for f in files:
                        preview += f"\n## {f.name}\n"
                        preview += f.read_text(encoding="utf-8", errors="replace")[:1500]
                        preview += "\n...\n"
                    return preview[:8000]
                elif stage_num == 4:
                    for name in ["sim_results.log", "sim.log"]:
                        p = project_path / "workspace" / "sim" / name
                        if p.exists():
                            return p.read_text(encoding="utf-8", errors="replace")[:4000]
                    return "(仿真日志未找到)"
            except Exception as e:
                return f"(读取预览失败: {e})"
            return ""

        # ======================================================================
        # 运行流水线（Generator 流式）— 逐 stage + Review Gate
        # ======================================================================
        def run_pipeline_stream(working_dir, project_name, mode, use_mock_val, max_workers_val=4, stage_to_run=None):
            """
            Yields 8 items per update:
              (log_text, stage_label, progress, run_btn, stop_btn,
               review_panel, review_preview, modules_checkboxes)
            """
            _NO_CHANGE = gr.update()

            def _yield(log, stage, prog, run_vis=None, stop_vis=None,
                        review_vis=None, preview_val=None,
                        modules_choices=None, modules_vis=None,
                        stage_status=None, btn_states=None):
                modules_upd = _NO_CHANGE
                if modules_choices is not None or modules_vis is not None:
                    kw = {}
                    if modules_choices is not None:
                        kw["choices"] = modules_choices
                        kw["value"]   = []
                    if modules_vis is not None:
                        kw["visible"] = modules_vis
                    modules_upd = gr.update(**kw)
                def _btn(s):
                    if btn_states is None:
                        return _NO_CHANGE
                    interactive, variant = btn_states.get(float(s), (False, "secondary"))
                    return gr.update(interactive=interactive, variant=variant)
                return (
                    log,
                    stage,
                    prog,
                    gr.update(visible=run_vis)    if run_vis    is not None else _NO_CHANGE,
                    gr.update(visible=stop_vis)   if stop_vis   is not None else _NO_CHANGE,
                    gr.update(visible=review_vis) if review_vis is not None else _NO_CHANGE,
                    gr.update(value=preview_val)  if preview_val is not None else _NO_CHANGE,
                    modules_upd,
                    gr.update(value=stage_status) if stage_status is not None else _NO_CHANGE,
                    _btn(1), _btn(1.5), _btn(2), _btn(3), _btn(3.5), _btn(4), _btn(5),
                )

            if not project_name or project_name == "(新建项目)":
                yield _yield("❌ 请先选择或创建项目", "等待中", 0,
                             run_vis=True, stop_vis=False, review_vis=False)
                return
            if app_state.is_running:
                yield _yield("⚠️ 流水线已在运行中", "运行中", int(app_state.progress),
                             run_vis=False, stop_vis=True, review_vis=False)
                return

            app_state.reset()
            app_state.is_running = True
            app_state.current_project = project_name

            # 保存 last_project
            _c = load_config()
            _c["last_project"] = project_name
            _c["working_dir"]  = working_dir
            save_config(_c)

            project_path = Path(working_dir) / project_name
            log_path = get_run_log_path(project_path)
            app_state.current_log_path = log_path
            app_state.current_logs = []

            _log_file = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
            _display_buf: deque = deque(maxlen=2000)

            def emit(msg, log_type="info"):
                line = add_log(msg, log_type)
                html_line = _rich_log_to_html(line, log_type)
                app_state.current_logs.append(line)
                app_state.current_logs_html.append(html_line)
                try:
                    _log_file.write(line + "\n")
                except Exception:
                    pass
                # 构建完整的 HTML 日志显示
                html_output = "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
                if len(app_state.current_logs_html) > 0:
                    for html_line in app_state.current_logs_html:
                        html_output += f"<div style='margin:0;padding:0'>{html_line}</div>"
                else:
                    html_output += "<div style='color:#8b949e'>等待启动流水线...</div>"
                html_output += "</div>"
                return html_output

            def _close_log_file():
                try:
                    _log_file.close()
                except Exception:
                    pass

            def _save_state(status, progress, stage, completed_stage_num=None, invalidate_from=None):
                """保存状态，合并 completed_stages。
                completed_stage_num: 刚完成的 stage，追加到 completed_stages。
                invalidate_from: 重跑该 stage 时，清除该 stage 及之后的 completed_stages。
                """
                existing = load_project_state(project_path)
                completed = list(existing.get("completed_stages", []))
                if invalidate_from is not None:
                    order = _ALL_STAGE_ORDER
                    try:
                        idx = order.index(float(invalidate_from))
                        completed = [s for s in completed if float(s) < order[idx]]
                    except ValueError:
                        pass
                if completed_stage_num is not None:
                    key = float(completed_stage_num)
                    if key not in [float(s) for s in completed]:
                        completed.append(completed_stage_num)
                save_project_state(project_path, {
                    "last_run": datetime.now().isoformat(),
                    "mode": mode,
                    "status": status,
                    "progress": progress,
                    "current_stage": stage,
                    "log_file": log_path.name,
                    "completed_stages": completed,
                })
                return completed

            # Stage 进度映射
            stage_progress = {
                1:   {"start": 5,  "done": 18, "label": "Stage 1: 架构规格"},
                1.5: {"start": 18, "done": 22, "label": "Stage 1.5: 微架构设计"},
                2:   {"start": 22, "done": 38, "label": "Stage 2: 时序模型"},
                2.5: {"start": 38, "done": 42, "label": "Stage 2.5: 人工审查"},
                3:   {"start": 42, "done": 65, "label": "Stage 3: RTL生成"},
                3.5: {"start": 65, "done": 75, "label": "Stage 3.5: 静态分析"},
                4:   {"start": 75, "done": 90, "label": "Stage 4: 仿真验证"},
                5:   {"start": 90, "done": 99, "label": "Stage 5: 综合KPI"},
            }
            stage_keywords = {
                "Executing Stage 1":          (10,  "Stage 1: 架构规格"),
                "stage 1 complete":           (20,  "Stage 1: 完成"),
                "Executing Stage 2":          (22,  "Stage 2: 时序模型"),
                "stage 2 complete":           (38,  "Stage 2: 完成"),
                "Executing Stage 3 Module":   (None, None),   # dynamic
                "stage 3 module":             (None, None),   # dynamic
                "stage 3 complete":           (65,  "Stage 3: 完成"),
                "Executing Stage 3.5":        (66,  "Stage 3.5: Lint + 静态分析"),
                "── Phase 1: Lint":           (67,  "Stage 3.5: Lint 检查"),
                "── Phase 2: Static":         (72,  "Stage 3.5: 静态分析"),
                "stage 35 complete":          (75,  "Stage 3.5: 完成"),
                "stage 3.5 complete":         (75,  "Stage 3.5: 完成"),
                "Executing Stage 3.6":        (38,  "Stage 3.6: 人工审查"),
                "Executing Stage 36":         (38,  "Stage 36: 人工审查"),
                "stage 36 complete":          (42,  "Stage 36: 完成"),
                "Executing Stage 4":          (76,  "Stage 4: 仿真验证"),
                "stage 4 complete":           (90,  "Stage 4: 完成"),
                "Executing Stage 5":          (91,  "Stage 5: 综合KPI"),
                "stage 5 complete":           (99,  "Stage 5: 完成"),
                "PIPELINE COMPLETED":         (100, "✅ 完成"),
                "PIPELINE FAILED":            (None, "❌ 失败"),
            }

            cur_prog, cur_stage = 0, "启动中..."
            if stage_to_run is not None:
                yield _yield(emit(f"▶ 单独执行 Stage {stage_to_run} (模式: {mode})", "stage"),
                             cur_stage, cur_prog,
                             run_vis=False, stop_vis=True, review_vis=False)
            else:
                yield _yield(emit("🚀 启动流水线 (模式: {})".format(mode), "stage"),
                             cur_stage, cur_prog,
                             run_vis=False, stop_vis=True, review_vis=False)

            # 确定要执行的 stage 列表
            mode_stages_map = {
                "quick":      [1, 1.5, 3, 3.5],
                "standard":   [1, 1.5, 2, 3, 3.5, 4, 5],
                "enterprise": [1, 1.5, 2, 3, 3.5, 4, 5],
            }
            if stage_to_run is not None:
                all_stages = [stage_to_run]
            else:
                all_stages = mode_stages_map.get(mode, [1, 3, 4])

            ctl_script  = str(get_skill_dir() / "veriflow_ctl.py")
            project_dir = str(project_path)
            feedback_path = project_path / ".veriflow" / "feedback.md"

            stage_i = 0
            while stage_i < len(all_stages):
                if not app_state.is_running:
                    break

                stage_num = all_stages[stage_i]
                s_info = stage_progress.get(stage_num, {"start": cur_prog, "done": cur_prog, "label": f"Stage {stage_num}"})
                cur_prog  = s_info["start"]
                cur_stage = s_info["label"]
                # 重跑该 stage 时清除该 stage 及后续的 completed_stages
                completed = _save_state("in_progress", cur_prog, cur_stage, invalidate_from=stage_num)
                yield _yield(emit(f"▶ Stage {stage_num} 开始", "stage"), cur_stage, cur_prog,
                             stage_status=_render_stage_status(completed, mode),
                             btn_states=_get_btn_states(completed, mode))

                # Build command
                cmd = [sys.executable, "-u", ctl_script, "run",
                       "--mode", mode, "-d", project_dir,
                       "--stages", str(stage_num),
                       "--workers", str(int(max_workers_val))]
                if feedback_path.exists():
                    cmd.extend(["--feedback", str(feedback_path)])
                    yield _yield(emit(f"📝 使用反馈: {feedback_path.name}", "info"),
                                 cur_stage, cur_prog)
                # Partial module re-generation
                if stage_num == 3 and app_state.rerun_modules:
                    cmd.extend(["--modules", ",".join(app_state.rerun_modules)])
                    yield _yield(emit(f"🔁 局部重生成: {app_state.rerun_modules}", "info"),
                                 cur_stage, cur_prog)
                    app_state.rerun_modules = None  # consumed

                yield _yield(emit(f"⚡ 执行 Stage {stage_num}: {' '.join(cmd[:4])}...", "command"),
                             cur_stage, cur_prog, stop_vis=True, review_vis=False)

                if use_mock_val:
                    # Mock mode
                    mock_map = {
                        1:   ["Executing Stage 1", "  Building spec...", "stage 1 complete"],
                        2:   ["Executing Stage 2", "  Generating timing model...", "stage 2 complete"],
                        2.5: ["Executing Stage 2.5", "  Human review gate...", "stage 2.5 complete"],
                        3:   ["Executing Stage 3 Module 1/2: top", "stage 3 module top complete",
                              "Executing Stage 3 Module 2/2: core", "stage 3 module core complete",
                              "stage 3 complete"],
                        3.5: ["Executing Stage 3.5", "  Running static analysis...", "stage 3.5 complete"],
                        4:   ["Executing Stage 4", "  Simulation...", "stage 4 complete", "PIPELINE COMPLETED"],
                        5:   ["Executing Stage 5", "  Synthesizing...", "stage 5 complete", "PIPELINE COMPLETED"],
                    }
                    for line in mock_map.get(stage_num, []):
                        time.sleep(0.3)
                        for kw, (prog, lbl) in stage_keywords.items():
                            if kw.lower() in line.lower() and prog is not None:
                                cur_prog, cur_stage = prog, lbl
                                break
                        log_type = ("stage" if "Executing" in line else
                                    "success" if "complete" in line.lower() else "info")
                        yield _yield(emit(line, log_type), cur_stage, cur_prog)
                    stage_failed = False
                else:
                    # Real execution
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace"
                        )
                        app_state.process = proc

                        for line in proc.stdout:
                            if not app_state.is_running:
                                break
                            line = line.rstrip()
                            if not line:
                                continue
                            for kw, (prog, lbl) in stage_keywords.items():
                                if kw.lower() in line.lower() and prog is not None:
                                    cur_prog, cur_stage = prog, lbl
                                    _save_state("in_progress", cur_prog, cur_stage)
                                    break
                            # 更精确的 log_type 判断：避免将包含 "FAILED" 但非错误的行误判
                            log_type = "info"
                            if "Executing Stage" in line:
                                log_type = "stage"
                            elif "COMPLETED" in line or "STAGE_COMPLETE" in line:
                                log_type = "success"
                            elif "❌" in line or "ERROR:" in line or "FAILED:" in line or "VALIDATE: FAIL" in line or "COMPLETE: DENIED" in line:
                                log_type = "error"
                            elif "✓" in line or "✅" in line or "PASSED" in line or "VALIDATE: PASS" in line or "COMPLETE: OK" in line:
                                log_type = "success"
                            elif "⚠️" in line or "WARNING:" in line:
                                log_type = "warning"
                            # 注意：不单独用 "FAILED" 做判断，避免误判
                            yield _yield(emit(line, log_type), cur_stage, cur_prog)

                        proc.wait()
                        app_state.process = None
                        stage_failed = proc.returncode != 0

                    except Exception as e:
                        app_state.process = None
                        yield _yield(emit(f"❌ 启动失败: {e}", "error"),
                                     "❌ 失败", cur_prog,
                                     run_vis=True, stop_vis=False, review_vis=False)
                        app_state.is_running = False
                        _close_log_file()
                        return

                if stage_failed:
                    cur_stage = "❌ 失败"
                    _save_state("failed", cur_prog, cur_stage)
                    yield _yield(emit(f"❌ Stage {stage_num} 失败", "error"),
                                 cur_stage, cur_prog,
                                 run_vis=True, stop_vis=False, review_vis=False)
                    app_state.is_running = False
                    _close_log_file()
                    return

                # ── Review Gate（只对有实质产物的 stage 弹出）────────────────
                cur_prog = s_info["done"]
                # stage 完成，追加到 completed_stages
                completed = _save_state("review", cur_prog, cur_stage, completed_stage_num=stage_num)

                # 不需要人工审查的 stage 直接推进
                REVIEW_STAGES = {1, 3}
                if stage_num not in REVIEW_STAGES:
                    stage_i += 1
                    yield _yield(emit(f"✅ Stage {stage_num} 完成", "success"), cur_stage, cur_prog,
                                 stage_status=_render_stage_status(completed, mode),
                                 btn_states=_get_btn_states(completed, mode))
                    continue

                review_content = _get_review_content(project_path, stage_num)

                # For Stage 3: read module names from spec for checkbox selection
                module_names = []
                if stage_num == 3:
                    spec_path = project_path / "workspace" / "docs" / "spec.json"
                    try:
                        spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
                        module_names = [m.get("name", "") for m in spec_data.get("modules", []) if m.get("name")]
                    except Exception:
                        pass

                yield _yield(
                    emit(f"⏸ Stage {stage_num} 完成，等待审查...", "stage"),
                    f"⏸ 审查 Stage {stage_num}", cur_prog,
                    run_vis=False, stop_vis=False,
                    review_vis=True, preview_val=review_content,
                    modules_choices=module_names if stage_num == 3 else [],
                    modules_vis=(stage_num == 3),
                )

                # Poll for user decision (yield every 0.5s to keep SSE alive)
                app_state.review_pending = True
                app_state.review_stage   = stage_num
                app_state.review_approved = False
                while app_state.review_pending:
                    if not app_state.is_running:
                        break
                    time.sleep(0.5)
                    # 构建当前 HTML 日志用于显示
                    html_output = "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
                    if len(app_state.current_logs_html) > 0:
                        for html_line in app_state.current_logs_html:
                            html_output += f"<div style='margin:0;padding:0'>{html_line}</div>"
                    else:
                        html_output += "<div style='color:#8b949e'>等待启动流水线...</div>"
                    html_output += "</div>"
                    yield _yield(html_output,
                                 f"⏸ 审查 Stage {stage_num}", cur_prog)

                # ── Review decision ──────────────────────────────────────────
                if not app_state.is_running:
                    break

                if app_state.review_approved:
                    # Cleanup feedback file and advance
                    if feedback_path.exists():
                        feedback_path.unlink()
                    stage_i += 1
                    yield _yield(emit(f"✅ Stage {stage_num} 已批准，继续...", "success"),
                                 cur_stage, cur_prog,
                                 review_vis=False,
                                 stage_status=_render_stage_status(completed, mode),
                                 btn_states=_get_btn_states(completed, mode))
                else:
                    # Re-run same stage with feedback (feedback_path written by reject handler)
                    yield _yield(emit(f"🔄 Stage {stage_num} 重新生成（含反馈）...", "stage"),
                                 f"🔄 重跑 Stage {stage_num}", cur_prog,
                                 review_vis=False)
                    # stage_i stays the same → re-runs this stage

            # ── All stages complete ──────────────────────────────────────────
            app_state.is_running = False
            app_state.process = None
            if stage_i >= len(all_stages):
                cur_prog, cur_stage = 100, "✅ 完成"
                completed = _save_state("completed", cur_prog, cur_stage)
                if stage_to_run is not None:
                    done_msg = f"✅ Stage {stage_to_run} 执行完成"
                else:
                    done_msg = "✅ 流水线全部完成！"
                yield _yield(emit(done_msg, "success"),
                             cur_stage, cur_prog,
                             run_vis=True, stop_vis=False, review_vis=False,
                             stage_status=_render_stage_status(completed, mode),
                             btn_states=_get_btn_states(completed, mode))
            else:
                _save_state("stopped", cur_prog, cur_stage)
                yield _yield(emit("⏹ 流水线已停止", "warning"),
                             cur_stage, cur_prog,
                             run_vis=True, stop_vis=False, review_vis=False)
            _close_log_file()
        run_btn.click(
            fn=run_pipeline_stream,
            inputs=[working_dir_input, project_dropdown, mode_dropdown, use_mock, max_workers_slider],
            outputs=[log_output, current_stage, progress_bar, run_btn, stop_btn,
                     review_panel, review_preview, modules_checkboxes, stage_status_html,
                     stage1_btn, stage15_btn, stage2_btn, stage3_btn, stage35_btn, stage4_btn, stage5_btn]
        )

        # ── 单 Stage 执行包装函数 ──────────────────────────────────────────────
        _stage_outputs = [log_output, current_stage, progress_bar, run_btn, stop_btn,
                          review_panel, review_preview, modules_checkboxes, stage_status_html,
                          stage1_btn, stage15_btn, stage2_btn, stage3_btn, stage35_btn, stage4_btn, stage5_btn]

        def _mk_stage_runner(s):
            def _fn(wd, proj, mode, mock, workers):
                yield from run_pipeline_stream(wd, proj, mode, mock, workers, stage_to_run=s)
            return _fn

        _stage_inputs = [working_dir_input, project_dropdown, mode_dropdown, use_mock, max_workers_slider]

        stage1_btn .click(fn=_mk_stage_runner(1),   inputs=_stage_inputs, outputs=_stage_outputs)
        stage15_btn.click(fn=_mk_stage_runner(1.5), inputs=_stage_inputs, outputs=_stage_outputs)
        stage2_btn .click(fn=_mk_stage_runner(2),   inputs=_stage_inputs, outputs=_stage_outputs)
        stage3_btn .click(fn=_mk_stage_runner(3),   inputs=_stage_inputs, outputs=_stage_outputs)
        stage35_btn.click(fn=_mk_stage_runner(3.5), inputs=_stage_inputs, outputs=_stage_outputs)
        stage4_btn .click(fn=_mk_stage_runner(4),   inputs=_stage_inputs, outputs=_stage_outputs)
        stage5_btn .click(fn=_mk_stage_runner(5),   inputs=_stage_inputs, outputs=_stage_outputs)

        # 模式切换 → 动态显示/隐藏阶段按钮
        def _update_stage_buttons(mode):
            show = mode in ("standard", "enterprise")
            return gr.update(visible=show), gr.update(visible=show)

        mode_dropdown.change(
            fn=_update_stage_buttons,
            inputs=[mode_dropdown],
            outputs=[stage2_row, stage45_row],
        )

        # 停止
        def stop_pipeline():
            if app_state.process:
                try:
                    app_state.process.kill()
                except Exception:
                    pass
                app_state.process = None
            app_state.is_running    = False
            app_state.review_pending = False
            msg_line = add_log("⏹️ 用户终止了流水线", "warning")
            html_line = _rich_log_to_html(msg_line, "warning")
            app_state.current_logs.append(msg_line)
            app_state.current_logs_html.append(html_line)
            if app_state.current_log_path:
                try:
                    with open(app_state.current_log_path, "a", encoding="utf-8") as _f:
                        _f.write(msg_line + "\n")
                except Exception:
                    pass
            # 构建完整的 HTML 日志显示
            html_output = "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
            if len(app_state.current_logs_html) > 0:
                for html_line in app_state.current_logs_html:
                    html_output += f"<div style='margin:0;padding:0'>{html_line}</div>"
            else:
                html_output += "<div style='color:#8b949e'>等待启动流水线...</div>"
            html_output += "</div>"
            return (
                html_output,
                "已停止", int(app_state.progress),
                gr.update(visible=True), gr.update(visible=False),
                gr.update(visible=False), gr.update(), gr.update(),
            )

        stop_btn.click(fn=stop_pipeline, outputs=[log_output, current_stage, progress_bar, run_btn, stop_btn,
                                                   review_panel, review_preview, modules_checkboxes])

        # ── Approve / Reject handlers ─────────────────────────────────────────
        def on_approve():
            app_state.review_approved = True
            app_state.review_pending  = False
            app_state.rerun_modules   = None
            return gr.update(visible=False), ""

        approve_btn.click(fn=on_approve, outputs=[review_panel, review_feedback])

        def on_reject(feedback_text, selected_modules, working_dir, project_name):
            if feedback_text and feedback_text.strip() and project_name and project_name != "(新建项目)":
                fb = Path(working_dir) / project_name / ".veriflow" / "feedback.md"
                fb.parent.mkdir(parents=True, exist_ok=True)
                fb.write_text(feedback_text.strip(), encoding="utf-8")
            # Save module selection for partial re-run (None / empty = all modules)
            app_state.rerun_modules   = selected_modules if selected_modules else None
            app_state.review_approved = False
            app_state.review_pending  = False
            return gr.update(visible=False), ""

        reject_btn.click(
            fn=on_reject,
            inputs=[review_feedback, modules_checkboxes, working_dir_input, project_dropdown],
            outputs=[review_panel, review_feedback]
        )

        # 软暂停 / 继续
        def pause_pipeline():
            app_state.stop_requested = True
            return gr.update(visible=False), gr.update(visible=True)

        def resume_pipeline():
            app_state.stop_requested = False
            return gr.update(visible=True), gr.update(visible=False)

        pause_btn .click(fn=pause_pipeline,  outputs=[pause_btn, resume_btn])
        resume_btn.click(fn=resume_pipeline, outputs=[pause_btn, resume_btn])

        # 清除日志
        def _clear_logs():
            app_state.current_logs = []
            app_state.current_logs_html = []
            html_output = "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
            html_output += "<div style='color:#8b949e'>日志已清除...</div>"
            html_output += "</div>"
            return html_output

        clear_logs_btn.click(fn=_clear_logs, outputs=[log_output])

        # 日志过滤器
        def _filter_logs(level: str) -> str:
            if not app_state.current_logs:
                return "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'><div style='color:#8b949e'>等待启动流水线...</div></div>"
            if level == "全部":
                filtered_indices = list(range(len(app_state.current_logs)))
            else:
                icon_map = {"信息": "ℹ️", "成功": "✅", "警告": "⚠️",
                            "错误": "❌", "阶段": "🔄"}
                icon = icon_map.get(level, "")
                filtered_indices = [i for i, l in enumerate(app_state.current_logs) if icon in l]
            # 构建过滤后的 HTML
            html_output = "<div style='font-family:Consolas,monospace;font-size:14px;line-height:1.4;padding:8px;background:#0d1117;color:#f0f6fc;min-height:400px;border-radius:8px;overflow:auto;'>"
            if filtered_indices:
                for idx in filtered_indices[-2000:]:
                    html_output += app_state.current_logs_html[idx] + "<br>"
            else:
                html_output += "<div style='color:#8b949e'>没有匹配的日志...</div>"
            html_output += "</div>"
            return html_output

        log_filter.change(
            fn=_filter_logs,
            inputs=[log_filter],
            outputs=[log_output],
        )

        # ======================================================================
        # 文件预览
        # ======================================================================
        def refresh_files_and_selector(working_dir, project_name):
            if not project_name or project_name == "(新建项目)":
                return [], gr.Dropdown(choices=[], value=None)
            files = scan_generated_files(Path(working_dir) / project_name)
            names = [f["文件"] for f in files]
            return files, gr.Dropdown(choices=names, value=names[0] if names else None)

        refresh_files_btn.click(
            fn=refresh_files_and_selector,
            inputs=[working_dir_input, project_dropdown],
            outputs=[file_list, file_selector]
        )

        def load_file_preview(working_dir, project_name, filename):
            if not filename or not project_name or project_name == "(新建项目)":
                return ""
            try:
                p = find_workspace_file(Path(working_dir) / project_name, filename)
                if p:
                    return p.read_text(encoding="utf-8", errors="replace")
                return f"// 文件未找到: {filename}"
            except Exception as e:
                return f"// 读取失败: {e}"

        file_selector.change(
            fn=load_file_preview,
            inputs=[working_dir_input, project_dropdown, file_selector],
            outputs=[preview_file]
        )

        def on_file_select(evt: gr.SelectData, working_dir, project_name, files_data):
            try:
                row_idx = evt.index[0]
                if files_data is not None and len(files_data) > row_idx:
                    filename = files_data[row_idx][0]
                    content  = load_file_preview(working_dir, project_name, filename)
                    return content, gr.Dropdown(value=filename)
            except Exception:
                pass
            return "", gr.update()

        file_list.select(
            fn=on_file_select,
            inputs=[working_dir_input, project_dropdown, file_list],
            outputs=[preview_file, file_selector]
        )

        # 启动时自动恢复上次项目会话
        if _init_project_value != "(新建项目)":
            demo.load(
                fn=on_project_select,
                inputs=[working_dir_input, project_dropdown],
                outputs=[log_output, current_stage, progress_bar, file_list, file_selector, requirement_text]
            )

    return demo

# ============================================================================
# 启动入口
# ============================================================================

def main():
    import sys
    import io
    import traceback

    print("VeriFlow GUI 正在启动...")

    try:
        # 修复 Windows 下的编码问题
        if sys.platform == "win32":
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

        print("=" * 60)
        print("VeriFlow GUI 8.2")
        print("=" * 60)
        print(f"工作目录: {app_state.working_dir}")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Python 版本: {sys.version}")
        print(f"系统: {sys.platform}")
        print("=" * 60)

        print("正在创建 UI...")
        demo = create_ui()

        print("正在启动服务器...")
        print("=" * 60)
        demo.launch(
            server_name="127.0.0.1",
            show_error=True,
            quiet=False,
            theme=gr.themes.Soft()
        )
    except Exception as e:
        print("\n=" * 60)
        print("启动错误!")
        print("=" * 60)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("\n堆栈跟踪:")
        print(traceback.format_exc())
        print("=" * 60)
        input("\n按回车键退出...")

if __name__ == "__main__":
    main()
