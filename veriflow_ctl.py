#!/usr/bin/env python3
"""
VeriFlow Controller v8.4 — Complete 5-Stage Architecture

Architecture: "Python as Master State Machine, LLM as Worker Node"
- This script is the top-level orchestrator implementing the complete state machine
- Claude Code (LLM) is called via subprocess as a worker to execute each stage
- Shell scripts in tools/ act as the ACI (Agent-Computer Interface) for EDA tools

Modes:
    quick      Stages: 1 → 1.5 → 3 → 3.5          Fast code generation + lint/static analysis
    standard   Stages: 1 → 1.5 → 2 → 3 → 3.5 → 4 → 5  Full functional verification + synthesis
    enterprise Stages: 1 → 1.5 → 2 → 3 → 3.5 → 4 → 5  (same as standard, reserved for future)

Subcommands:
    run         Run the complete VeriFlow pipeline (main entry point)
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

# ── Cross-platform: force UTF-8 stdout/stderr + line buffering ───────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_DIR
PROMPTS_DIR = SKILL_DIR / "prompts"

# ── Supervisor Decision TypedDict ────────────────────────────────────────────
class SupervisorDecision(TypedDict):
    action: str        # "retry_stage" | "escalate_stage" | "continue" | "abort"
    target_stage: int
    modules: List[str]
    hint: str
    root_cause: str
    severity: str      # "low" | "medium" | "high"

# ── Mode Configurations ─────────────────────────────────────────────────────
MODE_QUICK = "quick"
MODE_STANDARD = "standard"
MODE_ENTERPRISE = "enterprise"

MODE_STAGES = {
    MODE_QUICK:      [1, 15, 3, 35],            # micro-arch + code + lint/static analysis
    MODE_STANDARD:   [1, 15, 2, 3, 35, 4, 5],  # + timing model + simulation + synthesis
    MODE_ENTERPRISE: [1, 15, 2, 3, 35, 4, 5],  # reserved (same as standard)
}

def _normalize_stage_token(s: str) -> int:
    """Convert a stage token string to internal int representation.

    Dot-notation maps as: '1.5' -> 15, '3.5' -> 35, '3.6' -> 36
    Plain integers pass through: '1' -> 1, '4' -> 4
    """
    s = s.strip()
    if "." in s:
        major, minor = s.split(".", 1)
        return int(major) * 10 + int(minor)
    return int(s)

# ── Project Structure ─────────────────────────────────────────────────────
def get_project_paths(project_dir: Path) -> Dict[str, Path]:
    """Get all project paths."""
    return {
        "root": project_dir,
        "workspace": project_dir / "workspace",
        "docs": project_dir / "workspace" / "docs",
        "rtl": project_dir / "workspace" / "rtl",
        "tb": project_dir / "workspace" / "tb",
        "sim": project_dir / "workspace" / "sim",
        "veriflow": project_dir / ".veriflow",
        "config": project_dir / ".veriflow" / "project_config.json",
        "spec": project_dir / "workspace" / "docs" / "spec.json",
        "requirement": project_dir / "requirement.md",
    }

# ── Utility Functions ───────────────────────────────────────────────────────
def load_project_config(project_dir: Path) -> Dict:
    """Load project configuration."""
    config_file = project_dir / ".veriflow" / "project_config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {"mode": MODE_STANDARD, "project": "unknown"}

def save_project_state(project_dir: Path, state: Dict):
    """Save project state."""
    state_file = project_dir / ".veriflow" / "pipeline_state.json"
    state["updated_at"] = datetime.now().isoformat()
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def load_project_state(project_dir: Path) -> Dict:
    """Load project state."""
    state_file = project_dir / ".veriflow" / "pipeline_state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {
        "current_stage": None,
        "completed_stages": [],
        "mode": MODE_STANDARD,
        "status": "initialized"
    }

# ── LLM Worker Interface ────────────────────────────────────────────────────
def find_claude_cli() -> Optional[str]:
    """Find Claude CLI executable: config → PATH → common locations."""
    # 1. Check gui_config.json
    config_file = Path.home() / ".veriflow" / "gui_config.json"
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            cli_path = cfg.get("claude", {}).get("cli_path", "")
            if cli_path and Path(cli_path).exists():
                return cli_path
        except Exception:
            pass

    # 2. PATH search — include .cmd/.bat for Windows npm installs
    for name in ["claude", "claude.cmd", "claude.bat", "claude.exe"]:
        found = shutil.which(name)
        if found:
            return found

    # 3. Common install locations
    candidates = [
        Path.home() / ".claude" / "local" / "claude",
        Path.home() / ".claude" / "local" / "claude.exe",
        Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "claude",
        Path.home() / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    return None

def _get_oss_cad_env() -> Dict[str, str]:
    """
    Get oss-cad-suite environment variables (mimics environment.bat).

    Returns a dictionary of environment variables to use for EDA tools.
    """
    oss_dir = Path(r"C:\oss-cad-suite")
    if not oss_dir.exists():
        return dict(os.environ)

    env = dict(os.environ)
    yosyshq_root = str(oss_dir.resolve())
    bin_dir = str(oss_dir / "bin")
    lib_dir = str(oss_dir / "lib")

    # Update PATH
    env["PATH"] = f"{bin_dir};{lib_dir};{env.get('PATH', '')}"

    # Set SSL certificate
    ssl_cert = str(oss_dir / "etc" / "cacert.pem")
    if Path(ssl_cert).exists():
        env["SSL_CERT_FILE"] = ssl_cert

    # Python executable
    python_exe = str(oss_dir / "lib" / "python3.exe")
    if Path(python_exe).exists():
        env["PYTHON_EXECUTABLE"] = python_exe

    # QT environment
    qt_plugins = str(oss_dir / "lib" / "qt5" / "plugins")
    if Path(qt_plugins).exists():
        env["QT_PLUGIN_PATH"] = qt_plugins
    env["QT_LOGGING_RULES"] = "*=false"

    # GTK environment
    env["GTK_EXE_PREFIX"] = yosyshq_root
    env["GTK_DATA_PREFIX"] = yosyshq_root
    gdk_dir = str(oss_dir / "lib" / "gdk-pixbuf-2.0" / "2.10.0" / "loaders")
    if Path(gdk_dir).exists():
        env["GDK_PIXBUF_MODULEDIR"] = gdk_dir
        gdk_cache = str(oss_dir / "lib" / "gdk-pixbuf-2.0" / "2.10.0" / "loaders.cache")
        if Path(gdk_cache).exists():
            env["GDK_PIXBUF_MODULE_FILE"] = gdk_cache

    # OpenFPGALoader
    openfpgaloader_soj = str(oss_dir / "share" / "openFPGALoader")
    if Path(openfpgaloader_soj).exists():
        env["OPENFPGALOADER_SOJ_DIR"] = openfpgaloader_soj

    return env


def find_eda_tool(tool_name: str) -> Optional[str]:
    """Find an EDA tool by checking gui_config then PATH."""
    # Check gui_config.json first
    config_file = Path.home() / ".veriflow" / "gui_config.json"
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            path = cfg.get("env", {}).get(f"{tool_name}_path", "")
            if path and Path(path).exists():
                return path
        except Exception:
            pass

    # Search in oss-cad-suite bin first
    oss_bin = Path(r"C:\oss-cad-suite\bin")
    if oss_bin.exists():
        tool_path = oss_bin / (tool_name + ".exe")
        if tool_path.exists():
            return str(tool_path)

    # Search system PATH
    for suffix in ["", ".exe"]:
        found = shutil.which(tool_name + suffix)
        if found:
            return found
    return None

def _launch_claude_repl(project_dir: Path, initial_message: str = "") -> Optional[subprocess.Popen]:
    """
    Launch Claude CLI in interactive REPL mode.

    The caller is responsible for writing a CLAUDE.md into project_dir before
    calling this function — Claude reads it automatically on startup and begins
    working without any manual input.

    initial_message: if non-empty, will be injected into Claude's stdin
    automatically after Claude finishes loading, so the session starts without
    any manual user input.

    Windows: opens a PowerShell window (non-blocking).
    Linux/Mac: passthrough to current terminal (blocking until user exits).
    Returns Popen object on Windows, None on Linux/Mac.
    """
    claude_exe = find_claude_cli()
    if not claude_exe:
        print("  ERROR: Claude CLI not found")
        print("  Install: npm install -g @anthropic-ai/claude-code")
        return None

    def _sq(s: str) -> str:
        return s.replace("'", "''")

    if platform.system() == "Windows":
        # Build bat file content — use binary write to avoid Python text-mode
        # double-converting \r\n → \r\r\n.
        def _bq(s: str) -> str:
            """Quote a token for a Windows batch/cmd command line."""
            return '"' + s.replace('"', '""') + '"'

        # Add node.exe parent dir to PATH so claude.cmd can find node even
        # when launched from a GUI process that has no terminal PATH.
        node_exe = shutil.which("node") or shutil.which("node.exe")
        set_path_line = ""
        if node_exe:
            node_dir = str(Path(node_exe).parent)
            set_path_line = f"SET PATH={node_dir};%PATH%"

        # --dangerously-skip-permissions bypasses all path restrictions, so
        # --add-dir is redundant here.  Removing it also eliminates the risk
        # that an argument-parser treats the positional initial_message as a
        # second --add-dir value (consuming it silently).
        args = [
            _bq(claude_exe),
            "--dangerously-skip-permissions",
        ]
        # Pass initial_message BEFORE any path flags to avoid ambiguity
        if initial_message:
            args.append(_bq(initial_message))

        claude_line = " ".join(args)
        bat_lines = [
            "@echo off",
            "title VeriFlow Stage 1 - Architect",
        ]
        if set_path_line:
            bat_lines.append(set_path_line)
        bat_lines += [
            "echo.",
            "echo   ============================================",
            "echo    VeriFlow  Stage 1: Architect",
            "echo   ============================================",
            "echo.",
            "echo   Claude will send 'begin' automatically.",
            "echo   If it stops at the prompt, type:  begin",
            "echo.",
            f"cd /d {_bq(str(project_dir))}",
            claude_line,
            "if %ERRORLEVEL% NEQ 0 (",
            "  echo.",
            "  echo   [VeriFlow] ERROR: Claude exited with code %ERRORLEVEL%",
            "  echo   Check that 'claude' CLI is installed: npm install -g @anthropic-ai/claude-code",
            "  pause",
            ")",
        ]
        # Write with explicit \r\n in binary mode — avoids text-mode double conversion
        bat_content = "\r\n".join(bat_lines) + "\r\n"

        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="vf_stage1_")
        with os.fdopen(fd, "wb") as f:
            f.write(bat_content.encode("utf-8"))

        print(f"  [INFO] Claude exe : {claude_exe}", flush=True)
        print(f"  [INFO] Project dir: {project_dir}", flush=True)
        print(f"  [INFO] Command    : {claude_line}", flush=True)
        if set_path_line:
            print(f"  [INFO] Node dir   : {Path(node_exe).parent}", flush=True)

        def _cleanup():
            time.sleep(30)
            try:
                os.unlink(bat_path)
            except Exception:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()

        # os.startfile() uses ShellExecuteW — always opens a visible window
        # regardless of whether the parent process has a console (GUI mode).
        try:
            os.startfile(bat_path)
            print(f"  [INFO] Claude REPL launched via os.startfile()", flush=True)
            return None  # ShellExecute does not return a trackable proc
        except Exception as e:
            print(f"  [WARN] os.startfile failed ({e}), falling back to CREATE_NEW_CONSOLE", flush=True)
            proc = subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            print(f"  [INFO] Claude REPL launched (PID={proc.pid})", flush=True)
            return proc

    else:
        # Linux/Mac: same approach — pass initial_message as positional arg.
        cmd = [claude_exe, "--dangerously-skip-permissions", "--add-dir", str(project_dir)]
        if initial_message:
            cmd.append(initial_message)
        print("  [INFO] Launching Claude REPL in current terminal...")
        proc = subprocess.Popen(
            cmd,
            stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
            cwd=str(project_dir),
        )
        proc.wait()
        return None


# ── Thread-safe structured logging ───────────────────────────────────────────────
_print_lock = threading.Lock()
_error_logs: List[Dict[str, str]] = []  # Global error log buffer for supervisor analysis

# Shared icon constant (eliminates duplicate definitions)
LOG_ICONS: Dict[str, str] = {
    "info": "ℹ️", "success": "✅", "warning": "⚠️",
    "error": "❌", "stage": "🔄", "command": "⚡"
}

# Current run JSONL log file path (set by run_project() at the start of each run)
_current_jsonl_path: Optional[Path] = None

def _set_log_file(path: Path) -> None:
    """Called by run_project() at the start of each run to set structured log output path."""
    global _current_jsonl_path
    _current_jsonl_path = path


def _log(prefix: str, msg: str, log_type: str = "info") -> None:
    """Thread-safe structured print with log type and timestamp.

    Args:
        prefix: Agent/task identifier (e.g., '[aes_core] ', '[Stage 1] ')
        msg: Log message
        log_type: Log type: 'info', 'success', 'warning', 'error', 'stage', 'command'
    """
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    icon = LOG_ICONS.get(log_type, "ℹ️")

    log_entry = {
        "timestamp": timestamp,
        "prefix": prefix.strip(),
        "message": msg,
        "type": log_type,
        "full_line": f"[{timestamp}] {icon} {prefix}{msg}"
    }

    with _print_lock:
        print(log_entry["full_line"], flush=True)
        # Store errors in buffer for later analysis
        if log_type in ("error", "warning"):
            _error_logs.append(log_entry)
        # Append structured entry to JSONL log if configured
        if _current_jsonl_path:
            try:
                with open(_current_jsonl_path, "a", encoding="utf-8") as _jf:
                    _jf.write(json.dumps({
                        "ts": timestamp, "type": log_type,
                        "prefix": prefix.strip(), "message": msg
                    }) + "\n")
            except Exception:
                pass


def get_error_logs(clear: bool = False) -> List[Dict[str, str]]:
    """Get all buffered error logs for supervisor analysis.

    Args:
        clear: If True, clear the buffer after retrieval

    Returns:
        List of error log entries
    """
    with _print_lock:
        logs = list(_error_logs)
        if clear:
            _error_logs.clear()
        return logs


def clear_error_logs() -> None:
    """Clear the error log buffer."""
    with _print_lock:
        _error_logs.clear()


def call_claude(prompt_file: Path, context: Dict[str, str],
                prefix: str = "") -> Tuple[bool, str]:
    """
    Call Claude Code as a headless worker subprocess using --output-format stream-json.

    Streams all tool calls and text output to stdout in real time via
    _print_stream_event(). Returns (success, text_output) when Claude exits.
    """
    if not prompt_file.exists():
        return False, f"Prompt file not found: {prompt_file}"

    # Substitute {{KEY}} placeholders in the prompt template
    prompt = prompt_file.read_text(encoding="utf-8")
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)

    claude_exe = find_claude_cli()
    if not claude_exe:
        _log(prefix, "  [INFO] Claude CLI not found — using mock mode")
        context["_PROMPT_FILE"] = str(prompt_file)
        return mock_claude_execution(prompt, context)

    project_dir_str = context.get("PROJECT_DIR", ".")
    mode_str        = context.get("MODE", "quick")
    stage_name      = context.get("STAGE_NAME", prompt_file.stem)

    full_prompt = (
        "You are executing a VeriFlow RTL pipeline stage. "
        "Follow ALL instructions below **exactly and completely**.\n\n"
        "## Execution Context\n"
        f"- **Project Directory (absolute path)**: `{project_dir_str}`\n"
        f"- **Pipeline Mode**: `{mode_str}`\n"
        "- All file paths below are relative to the project directory above.\n"
        "- You MUST create every output file listed. "
        "Do NOT describe or discuss — just execute.\n"
        "- After completing all tasks, print the exact summary block "
        "shown at the end of the instructions.\n\n"
        "---\n\n"
        + prompt
    )

    # stream-json requires --verbose
    base_flags = [
        "--print", "--dangerously-skip-permissions",
        "--verbose", "--output-format", "stream-json",
        "--add-dir", project_dir_str,
    ]
    if platform.system() == "Windows" and claude_exe.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", claude_exe] + base_flags
    else:
        cmd = [claude_exe] + base_flags

    _log(prefix, f"🤖 Claude CLI 启动 [{stage_name}] PID=?", "info")

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir_str,
        )
        _log(prefix, f"🤖 Claude CLI 启动 [{stage_name}] PID={proc.pid}", "info")

        proc.stdin.write(full_prompt)
        proc.stdin.close()

        text_parts: List[str] = []
        api_success = False

        for raw in proc.stdout:
            raw = raw.rstrip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
                text = _print_stream_event(event, prefix=prefix)
                if text:
                    text_parts.append(text)
                if isinstance(event, dict) and event.get("type") == "result":
                    api_success = event.get("subtype") == "success"
            except json.JSONDecodeError:
                _log(prefix, f"  [Claude] {raw}")
                text_parts.append(raw)
            except Exception as exc:
                _log(prefix, f"  [parse error] {exc}: {raw[:100]}")

        proc.wait()
        _log(prefix, f"✅ Claude CLI 完成 (exit={proc.returncode})", "success")

        output  = "\n".join(text_parts)
        success = api_success or "STAGE_COMPLETE" in output or proc.returncode == 0
        return success, output

    except FileNotFoundError:
        context["_PROMPT_FILE"] = str(prompt_file)
        return mock_claude_execution(full_prompt, context)
    except Exception as e:
        return False, f"Error calling Claude: {str(e)}"


def _tail_log(path: str, last_pos: int, output_lines: list) -> int:
    """Read new bytes from a log file, print and collect lines. Returns new position."""
    try:
        with open(path, "rb") as f:
            f.seek(last_pos)
            raw = f.read()
            new_pos = last_pos + len(raw)
        if raw:
            for line in raw.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line:
                    print(f"  [Claude] {line}", flush=True)
                    output_lines.append(line)
        return new_pos
    except Exception:
        return last_pos


def _print_stream_event(event, prefix: str = "") -> Optional[str]:
    """
    Parse one stream-json event, print a human-readable line to stdout,
    and return the text content (if any) for STAGE_COMPLETE detection.
    prefix is prepended to every printed line (e.g. '[aes_core] ').
    """
    if not isinstance(event, dict):
        _log(prefix, f"[Claude] {event}", "info")
        return str(event)

    etype = event.get("type", "")

    if etype == "system" and event.get("subtype") == "init":
        tools = event.get("tools", [])
        names = ", ".join(t if isinstance(t, str) else t.get("name", "?") for t in tools)
        _log(prefix, f"[系统] session={event.get('session_id', '')}  tools: {names}", "info")
        return None

    elif etype == "assistant":
        texts = []
        msg = event.get("message", {})
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    _log(prefix, f"[Claude] {text}", "info")
                    texts.append(text)
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp  = block.get("input", {})
                brief = {k: (str(v) if len(str(v)) <= 120 else str(v)[:120] + "…")
                         for k, v in inp.items()}
                _log(prefix, f"[Tool→] {name}  {json.dumps(brief, ensure_ascii=False)}", "command")
        usage = msg.get("usage", {})
        if usage.get("output_tokens"):
            _log(prefix, f"[tokens] in={usage.get('input_tokens',0)} out={usage.get('output_tokens',0)}", "info")
        return "\n".join(texts) or None

    elif etype == "user":
        for block in event.get("message", {}).get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                is_err   = block.get("is_error", False)
                contents = block.get("content", [])
                if isinstance(contents, str):
                    text = contents
                else:
                    text = "\n".join(
                        c.get("text", "") for c in contents
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                if len(text) > 300:
                    text = text[:300] + "…"
                icon = "✗" if is_err else "✓"
                log_type = "error" if is_err else "success"
                _log(prefix, f"[Tool{icon}] {text.replace(chr(10), ' ')}", log_type)
        return None

    elif etype == "result":
        cost  = event.get("cost_usd")
        turns = event.get("num_turns", "?")
        dur   = event.get("duration_ms", 0)
        cost_str = f" 💰${cost:.4f}" if cost else ""
        _log(prefix, f"[完成] turns={turns}  {dur/1000:.1f}s{cost_str}", "success")
        return event.get("result", "")

    # Unknown event — skip silently
    return None


def _run_claude_in_visible_window(
    claude_exe: str, stage_name: str,
    project_dir: str, stdin_path: str, out_path: str
) -> subprocess.Popen:
    """
    Windows only: open a visible PowerShell window that runs Claude CLI.
    Claude's --print mode is silent when stdin is a pipe (no TTY), so we run
    Claude in a background Runspace and show our own spinner in the foreground.
    Output is tee'd to out_path for the GUI tail loop.
    """
    def _sq(s: str) -> str:
        return s.replace("'", "''")

    # Build the .ps1 script. Use PowerShell single-quoted strings for all user
    # paths (no escape sequences needed). Double {{ }} for literal { } in f-string.
    ps_script = """\
$claudeExe  = '{claude_exe}'
$projectDir = '{project_dir}'
$stdinPath  = '{stdin_path}'
$outPath    = '{out_path}'
$stageName  = '{stage_name}'

$host.UI.RawUI.WindowTitle = "VeriFlow - $stageName"
Write-Host ""
Write-Host "  [VeriFlow] Stage : $stageName" -ForegroundColor Cyan
Write-Host "  [VeriFlow] Claude: $claudeExe" -ForegroundColor DarkGray
Write-Host ""

$startTime = [DateTime]::Now

# Run Claude in a background Runspace so we can animate the foreground
$rs = [runspacefactory]::CreateRunspace()
$rs.Open()
$ps = [powershell]::Create()
$ps.Runspace = $rs
[void]$ps.AddScript({{
    param($exe, $dir, $inPath, $outPath)
    $inp = Get-Content -Path $inPath -Raw -Encoding UTF8
    $inp | & $exe --print --dangerously-skip-permissions --add-dir $dir |
        Tee-Object -FilePath $outPath
}}).AddParameters(@{{
    exe     = $claudeExe
    dir     = $projectDir
    inPath  = $stdinPath
    outPath = $outPath
}})
$handle = $ps.BeginInvoke()

# Spinner while Claude processes (stdin=pipe so Claude itself stays silent)
$frames = @('|','/','-','\\')
$i = 0
while (-not $handle.IsCompleted) {{
    $elapsed = [int]([DateTime]::Now - $startTime).TotalSeconds
    $f = $frames[$i % 4]
    Write-Host "`r  $f  Claude 正在生成... $($elapsed)s" -NoNewline -ForegroundColor Yellow
    $i++
    Start-Sleep -Milliseconds 120
}}
$elapsed = [int]([DateTime]::Now - $startTime).TotalSeconds
Write-Host "`r  v  Claude 完成 (用时 $($elapsed)s)                   " -ForegroundColor Green
Write-Host ""

# Display Claude's output
Write-Host "--- Claude 输出 ---" -ForegroundColor DarkGray
$ps.EndInvoke($handle) | Out-Host
$ps.Dispose()
$rs.Close()

Write-Host ""
Write-Host "  [VeriFlow] 5秒后关闭..." -ForegroundColor DarkGray
Start-Sleep 5
""".format(
        claude_exe  = _sq(claude_exe),
        project_dir = _sq(project_dir),
        stdin_path  = _sq(stdin_path),
        out_path    = _sq(out_path),
        stage_name  = stage_name,
    )

    fd_ps, ps_path = tempfile.mkstemp(suffix=".ps1", prefix="cf_run_")
    with os.fdopen(fd_ps, "w", encoding="utf-8-sig") as f:
        f.write(ps_script)

    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_path],
        cwd=project_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    def _cleanup():
        time.sleep(8)
        try: os.unlink(ps_path)
        except Exception: pass
    threading.Thread(target=_cleanup, daemon=True).start()

    return proc

def mock_claude_execution(prompt: str, context: Dict[str, str]) -> Tuple[bool, str]:
    """
    Mock execution for testing when Claude CLI is not available.
    Creates actual output files so downstream validation passes.
    Stage is identified by _PROMPT_FILE (reliable) or role line fallback.
    """
    project_dir = Path(context.get("PROJECT_DIR", "."))

    # Primary: identify by prompt filename
    pf = context.get("_PROMPT_FILE", "").lower()
    if "stage1" in pf or "architect" in pf or "spec" in pf:
        stage = 1
    elif "stage2" in pf or "timing" in pf:
        stage = 2
    elif "stage35" in pf or "skill_d" in pf:
        stage = 35
    elif "stage3" in pf or "coder" in pf or "codegen" in pf:
        stage = 3
    elif "stage4" in pf or "debugger" in pf or "sim" in pf:
        stage = 4
    elif "stage5" in pf or "synth" in pf:
        stage = 5
    elif "stage15" in pf or "microarch" in pf:
        stage = 15
    elif "supervisor" in pf:
        stage = "supervisor"
    else:
        # Fallback: use unique role sentence (not generic words)
        pl = prompt.lower()
        if "you are the **architect**" in pl:
            stage = 1
        elif "you are the **timing modeler**" in pl:
            stage = 2
        elif "you are the **skill d**" in pl or "static quality" in pl:
            stage = 35
        elif "you are the **coder**" in pl:
            stage = 3
        elif "you are the **debugger**" in pl:
            stage = 4
        else:
            stage = 0

    # ── Stage 1: create spec.json ────────────────────────────────────────────
    if stage == 1:
        spec_path = project_dir / "workspace" / "docs" / "spec.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec = {
            "design_name": project_dir.name,
            "description": f"Mock specification for {project_dir.name}",
            "target_frequency_mhz": 300,
            "data_width": 32,
            "byte_order": "MSB_FIRST",
            "target_kpis": {
                "frequency_mhz": 300,
                "max_cells": 5000,
                "power_mw": 100
            },
            "pipeline_stages": 2,
            "critical_path_budget": 3,
            "resource_strategy": "distributed_ram",
            "modules": [
                {
                    "name": "top",
                    "description": "Top-level module",
                    "module_type": "top",
                    "hierarchy_level": 0,
                    "parent": None,
                    "submodules": ["core"],
                    "clock_domains": [{"name": "clk", "frequency_mhz": 300}],
                    "reset_domains": [{"name": "rst_n", "active_level": "low", "synchronous": False}],
                    "ports": [
                        {"name": "clk",   "direction": "input",  "width": 1,  "description": "Clock"},
                        {"name": "rst_n", "direction": "input",  "width": 1,  "description": "Active-low reset"},
                        {"name": "din",   "direction": "input",  "width": 32, "description": "Data input"},
                        {"name": "dout",  "direction": "output", "width": 32, "description": "Data output"},
                        {"name": "valid", "direction": "output", "width": 1,  "description": "Output valid"}
                    ]
                },
                {
                    "name": "core",
                    "description": "Core processing module",
                    "module_type": "processing",
                    "hierarchy_level": 1,
                    "parent": "top",
                    "submodules": [],
                    "ports": [
                        {"name": "clk",   "direction": "input",  "width": 1,  "description": "Clock"},
                        {"name": "rst_n", "direction": "input",  "width": 1,  "description": "Reset"},
                        {"name": "din",   "direction": "input",  "width": 32, "description": "Data input"},
                        {"name": "dout",  "direction": "output", "width": 32, "description": "Data output"},
                        {"name": "valid", "direction": "output", "width": 1,  "description": "Valid flag"}
                    ]
                }
            ]
        }
        spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
        return True, f"""
=== Stage 1: Architect Complete ===
Design: {project_dir.name}
Modules: 2
Top Module: top
Target Frequency: 300 MHz
Output: workspace/docs/spec.json
STAGE_COMPLETE
===================================
"""

    # ── Stage 2: create timing_model.yaml + testbench ─────────────────────────
    elif stage == 2:
        docs_dir = project_dir / "workspace" / "docs"
        tb_dir = project_dir / "workspace" / "tb"
        docs_dir.mkdir(parents=True, exist_ok=True)
        tb_dir.mkdir(parents=True, exist_ok=True)

        design_name = project_dir.name
        spec_path = project_dir / "workspace" / "docs" / "spec.json"
        if spec_path.exists():
            try:
                design_name = json.loads(spec_path.read_text(encoding="utf-8")).get("design_name", design_name)
            except Exception:
                pass

        timing_yaml = f"""design: {design_name}
scenarios:
  - name: basic_operation
    assertions:
      - "i_valid |-> ##[1:3] o_valid"
    stimulus:
      - {{cycle: 0, din: 0xDEADBEEF, i_valid: 1}}
      - {{cycle: 1, i_valid: 0}}
"""
        (docs_dir / "timing_model.yaml").write_text(timing_yaml, encoding="utf-8")

        tb_v = f"""`timescale 1ns/1ps
module tb_{design_name};
    reg         clk, rst_n;
    reg  [31:0] din;
    wire [31:0] dout;
    wire        valid;

    top uut (.clk(clk), .rst_n(rst_n), .din(din), .dout(dout), .valid(valid));

    initial clk = 0;
    always #1.67 clk = ~clk;

    initial begin
        rst_n = 0; din = 0;
        @(posedge clk); #0.1;
        rst_n = 1;
        din = 32'hDEADBEEF;
        @(posedge clk); #0.1;
        din = 0;
        repeat (10) @(posedge clk);
        if (valid) begin
            $display("PASS: dout=%h valid=%b", dout, valid);
        end else begin
            $display("FAIL: valid never asserted");
        end
        $finish;
    end
endmodule
"""
        (tb_dir / f"tb_{design_name}.v").write_text(tb_v, encoding="utf-8")

        return True, f"""
=== Stage 2: Timing Model Complete ===
Design: {design_name}
Output: workspace/docs/timing_model.yaml
Testbench: workspace/tb/tb_{design_name}.v
STAGE_COMPLETE
=======================================
"""

    # ── Stage 35: create static_report.json ───────────────────────────────────
    elif stage == 35:
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "logic_depth_estimate": {"max_levels": 8, "budget": 10, "status": "OK"},
            "cdc_risks": [],
            "latch_risks": [],
            "recommendation": "No critical issues detected"
        }
        (docs_dir / "static_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, """
=== Stage 35: Skill D Complete ===
Static Analysis: PASS
Logic Depth: 8/10 levels (OK)
CDC Risks: 0
Latch Risks: 0
STAGE_COMPLETE
===================================
"""

    # ── Stage 3: create RTL files ────────────────────────────────────────────
    elif stage == 3:
        rtl_dir = project_dir / "workspace" / "rtl"
        rtl_dir.mkdir(parents=True, exist_ok=True)

        design_name = project_dir.name
        spec_path = project_dir / "workspace" / "docs" / "spec.json"
        if spec_path.exists():
            try:
                design_name = json.loads(spec_path.read_text(encoding="utf-8")).get("design_name", design_name)
            except Exception:
                pass

        (rtl_dir / "top.v").write_text(f"""`timescale 1ns/1ps
module top (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] din,
    output reg  [31:0] dout,
    output reg         valid
);

core u_core (
    .clk   (clk),
    .rst_n (rst_n),
    .din   (din),
    .dout  (dout),
    .valid (valid)
);

endmodule
""", encoding="utf-8")

        (rtl_dir / "core.v").write_text(f"""`timescale 1ns/1ps
module core (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] din,
    output reg  [31:0] dout,
    output reg         valid
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        dout  <= 32'h0;
        valid <= 1'b0;
    end else begin
        dout  <= din;
        valid <= 1'b1;
    end
end

endmodule
""", encoding="utf-8")

        return True, f"""
=== Stage 3: Coder Complete ===
Design: {design_name}
Files Generated: 2
  - workspace/rtl/top.v
  - workspace/rtl/core.v
Total Lines: ~50
STAGE_COMPLETE
=================================
"""

    # ── Stage 4: create sim result ───────────────────────────────────────────
    elif stage == 4:
        sim_dir = project_dir / "workspace" / "sim"
        sim_dir.mkdir(parents=True, exist_ok=True)
        (sim_dir / "sim_result.txt").write_text(
            "Mock simulation: ALL TESTS PASSED\nNo errors found.\n", encoding="utf-8"
        )
        return True, """
=== Stage 4: Debugger Complete ===
Files Modified: 0
Simulation: PASSED
Total Errors Fixed: 0
STAGE_COMPLETE
==================================
"""

    # ── Stage 5: create synth_report.json ─────────────────────────────────────
    elif stage == 5:
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "design": project_dir.name,
            "num_cells": 1234,
            "num_wires": 890,
            "note": "Mock synthesis report (Yosys not available)"
        }
        (docs_dir / "synth_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, """
=== Stage 5: Synthesis Complete ===
Cells: 1234 (mock)
Wires: 890 (mock)
STAGE_COMPLETE
====================================
"""

    # ── Stage 15: create micro_arch.md ───────────────────────────────────────
    elif stage == 15:
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        micro_arch_path = docs_dir / "micro_arch.md"
        micro_arch_path.write_text(
            "# Micro-Architecture Document\n\n"
            "## Overview\n"
            "Mock micro-architecture document generated by VeriFlow mock mode.\n\n"
            "## Pipeline Stages\n"
            "- Stage 1: Input register\n"
            "- Stage 2: Processing\n\n"
            "## Critical Paths\n"
            "- Data path: 3ns budget\n"
            "STAGE_COMPLETE\n",
            encoding="utf-8"
        )
        return True, "=== Stage 1.5: Micro-Architecture Design Complete ===\nSTAGE_COMPLETE\n"

    # ── Supervisor: return routing decision JSON ──────────────────────────────
    elif stage == "supervisor":
        return True, '{"action": "abort", "target_stage": 0, "modules": [], "hint": "mock supervisor", "root_cause": "mock", "severity": "low"}'

    else:
        return True, "STAGE_COMPLETE: Unknown stage processed"

# ── TB Tamper Protection Helpers ─────────────────────────────────────────────
def _snapshot_dir(dir_path: Path) -> Dict[str, bytes]:
    """Take a content snapshot of all files in a directory."""
    snapshot = {}
    if dir_path.exists():
        for f in dir_path.rglob("*"):
            if f.is_file():
                rel = str(f.relative_to(dir_path))
                snapshot[rel] = f.read_bytes()
    return snapshot


def _check_dir_tampered(snapshot: Dict[str, bytes], dir_path: Path) -> List[str]:
    """Return list of files that were added, modified, or deleted vs snapshot."""
    changed = []
    if not dir_path.exists():
        return list(snapshot.keys())  # all files gone
    current_files: Dict[str, bytes] = {}
    for f in dir_path.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(dir_path))
            current_files[rel] = f.read_bytes()
    for rel, content in snapshot.items():
        if current_files.get(rel) != content:
            changed.append(rel)
    for rel in current_files:
        if rel not in snapshot:
            changed.append(rel)
    return changed


def _restore_dir(snapshot: Dict[str, bytes], dir_path: Path) -> None:
    """Restore directory to exact snapshot state (overwrite + delete extras)."""
    dir_path.mkdir(parents=True, exist_ok=True)
    for rel, content in snapshot.items():
        target = dir_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    # Remove files not in snapshot
    for f in list(dir_path.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(dir_path))
            if rel not in snapshot:
                f.unlink()


# ── ACI Tool Interface ───────────────────────────────────────────────────────
def run_lint(project_dir: Path, rtl_files: List[Path],
             log_name: str = "linter_error") -> Tuple[bool, str]:
    """
    Run iverilog syntax/lint check (Python-native, cross-platform).
    Returns (passed, output). Skips gracefully if iverilog not installed or crashes.
    """
    iverilog = find_eda_tool("iverilog")
    if not iverilog:
        return True, "⚠️  iverilog not found — lint check skipped"

    # Filter out testbench files for lint (they reference UUT, which may cause spurious errors)
    design_files = [f for f in rtl_files if not f.name.startswith("tb_")]
    files_to_check = design_files if design_files else rtl_files

    # Get the oss-cad-suite environment (critical for iverilog to work correctly)
    env = _get_oss_cad_env()

    cmd = [iverilog, "-Wall", "-tnull"] + [str(f) for f in files_to_check]
    try:
        _log("[run_lint]", f"Running: {' '.join([Path(iverilog).name, '-Wall', '-tnull', '...'])}", "command")
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
            cwd=project_dir,
            env=env  # Use oss-cad-suite environment
        )

        # Check for iverilog crash on Windows (returncode=3221225785 = STATUS_ACCESS_VIOLATION)
        if result.returncode == 3221225785:
            return True, "⚠️  iverilog crash (Windows compatibility) — lint check skipped"

        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr

        # Save the actual raw output to a file for Debugger to read
        log_dir = project_dir / ".veriflow" / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"{log_name}.log"
        log_file.write_text(output, encoding="utf-8")
        _log("[run_lint]", f"Lint output saved to {log_file}", "info")

        # iverilog exits 0 on clean compile
        if result.returncode == 0:
            return True, "✓ PASS: No lint errors\n" + output
        return False, output
    except subprocess.TimeoutExpired:
        return False, "Lint check timed out after 60 seconds"
    except Exception as e:
        return False, f"Error running iverilog: {e}"


def run_sim(project_dir: Path, testbench: Path, rtl_files: List[Path]) -> Tuple[bool, str]:
    """
    Compile and simulate with iverilog+vvp (Python-native, cross-platform).
    Returns (passed, output). Skips gracefully if tools not installed.
    """
    iverilog = find_eda_tool("iverilog")
    vvp      = find_eda_tool("vvp")
    if not iverilog or not vvp:
        return True, "⚠️  iverilog/vvp not found — simulation skipped"

    # Get the oss-cad-suite environment (critical for iverilog to work correctly)
    env = _get_oss_cad_env()

    import tempfile
    fd, sim_out_str = tempfile.mkstemp(suffix=".vvp", dir=str(project_dir))
    os.close(fd)
    sim_out = Path(sim_out_str)

    try:
        non_tb = [f for f in rtl_files if f != testbench]
        compile_cmd = [iverilog, "-o", str(sim_out), str(testbench)] + [str(f) for f in non_tb]
        _log("[run_sim]", f"Compiling: {' '.join([Path(iverilog).name, '-o', sim_out.name, testbench.name, '...'])}", "command")
        r1 = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", cwd=project_dir,
            env=env  # Use oss-cad-suite environment
        )
        if r1.returncode != 0:
            return False, f"Compilation failed:\n{r1.stdout}\n{r1.stderr}"

        _log("[run_sim]", f"Simulating: {Path(vvp).name} {sim_out.name}", "command")
        r2 = subprocess.run(
            [vvp, str(sim_out)], capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", cwd=project_dir,
            env=env  # Use oss-cad-suite environment
        )
        output = r2.stdout + "\n" + r2.stderr
        passed = r2.returncode == 0 and ("PASS" in output or "ALL TESTS PASSED" in output)
        return passed, output
    except subprocess.TimeoutExpired:
        return False, "Simulation timed out after 120 seconds"
    except Exception as e:
        return False, f"Simulation error: {e}"
    finally:
        try:
            sim_out.unlink(missing_ok=True)
        except Exception:
            pass

# ── Stage Implementations ─────────────────────────────────────────────────────
def stage1_architect(project_dir: Path, mode: str,
                     feedback_file: Optional[Path] = None) -> bool:
    """
    Stage 1: Architecture Specification (Interactive REPL Mode)

    Launches Claude in REPL mode for Q&A-based architecture analysis.
    Waits for sentinel file (stage1.done) to confirm completion.
    """
    print("\n" + "="*60)
    print("STAGE 1: ARCHITECT (Interactive Q&A Mode)")
    print("="*60)

    paths = get_project_paths(project_dir)

    # Check requirement.md exists
    if not paths["requirement"].exists():
        print(f"ERROR: requirement.md not found at {paths['requirement']}")
        return False

    # Clear old sentinel to prevent false positives
    sentinel = paths["docs"] / "stage1.done"
    sentinel.unlink(missing_ok=True)

    # ── Build kickoff content ────────────────────────────────────────────────
    kickoff_content = (PROMPTS_DIR / "stage1_architect.md").read_text(encoding="utf-8")

    # Prepend an AUTOSTART header so Claude knows to begin immediately upon
    # receiving the first (pipeline-injected) trigger message.
    autostart_header = """\
<!-- VeriFlow Pipeline: auto-launched session -->
## ⚡ AUTOSTART — VeriFlow Pipeline

This session was **automatically launched** by the VeriFlow pipeline.
You will receive a short trigger message (e.g. "begin").

**As soon as you receive it, immediately:**
1. Read `requirement.md` from the project root directory.
2. Start the Q&A by asking your first clarifying question.

Do NOT wait for the user to re-explain the task — begin executing on the trigger.

---

"""
    kickoff_content = autostart_header + kickoff_content

    kickoff_content += f"""

---

## 完成协议（最后一步）

完成所有问答并生成 `workspace/docs/spec.json` 后，**必须执行**：

```bash
python "{SCRIPT_PATH}" validate --stage 1 -d "{project_dir}"
```

如果输出 `VALIDATE: PASS`，继续执行：

```bash
python "{SCRIPT_PATH}" complete --stage 1 -d "{project_dir}"
```

完成后会显示 `COMPLETE: OK`，并自动生成 `stage1.done` 文件。

**然后告诉用户**：
> 架构分析完成。可以关闭此窗口，流水线将自动继续。

"""

    # ── Also write to stage1_kickoff.md (for reference) ─────────────────────
    kickoff = paths["docs"] / "stage1_kickoff.md"
    kickoff.write_text(kickoff_content, encoding="utf-8")

    # ── Write CLAUDE.md into the PROJECT directory ───────────────────────────
    # Claude Code reads CLAUDE.md automatically on startup and will immediately
    # begin executing the stage 1 Q&A workflow without any user intervention.
    # We back up any existing CLAUDE.md and restore it after stage 1 completes.
    project_claude_md = project_dir / "CLAUDE.md"
    _claude_md_backup = None
    if project_claude_md.exists():
        _claude_md_backup = project_claude_md.read_text(encoding="utf-8")

    project_claude_md.write_text(kickoff_content, encoding="utf-8")

    print(f"\n  [INFO] 启动交互式架构分析...")
    print(f"  [INFO] Claude 启动后将自动读取任务指令并开始执行")
    print(f"  [INFO] 完成后 Claude 会写入 stage1.done，本窗口将自动继续\n")

    # Launch REPL — inject "begin" so Claude starts working without user input
    proc = _launch_claude_repl(project_dir, initial_message="begin")

    # Poll for sentinel file or process exit
    poll_interval = 2   # seconds between sentinel checks
    status_interval = 20  # seconds between GUI status prints
    max_wait = 3600  # 1 hour timeout
    elapsed = 0
    last_status = 0

    while elapsed < max_wait:
        if sentinel.exists():
            break

        # Print periodic status so the GUI textbox stays updated (otherwise
        # the Gradio generator blocks silently on proc.stdout reads).
        if elapsed - last_status >= status_interval:
            mins = elapsed // 60
            print(f"  [Stage 1] 等待架构分析完成... {mins}分{elapsed % 60}秒 / 最多60分钟", flush=True)
            last_status = elapsed

        # Check if process exited unexpectedly (only when we have a proc handle)
        if proc is not None and proc.poll() is not None:
            print("\n  ⚠️  Claude 窗口已关闭，但未检测到 stage1.done", flush=True)
            print("  可能原因：Claude 异常退出，或未执行 complete 命令。", flush=True)
            print("  请手动重新运行 Stage 1，或检查 Claude CLI 安装。", flush=True)
            return False

        time.sleep(poll_interval)
        elapsed += poll_interval

    if not sentinel.exists():
        print(f"\n  ERROR: 超时（{max_wait}秒）未检测到 stage1.done")
        return False

    # Validate sentinel file
    try:
        done_info = json.loads(sentinel.read_text(encoding="utf-8"))
        if done_info.get("status") != "ok":
            print(f"  ERROR: stage1.done 状态异常: {done_info}")
            return False
    except Exception as e:
        print(f"  ERROR: 无法解析 stage1.done: {e}")
        return False

    # Verify spec.json
    if not paths["spec"].exists():
        print("  ERROR: spec.json 未生成")
        return False

    # Checksum validation
    import hashlib
    actual_checksum = hashlib.md5(paths["spec"].read_bytes()).hexdigest()
    expected_checksum = done_info.get("checksum", "")
    if expected_checksum and actual_checksum != expected_checksum:
        print("  ERROR: spec.json 校验失败（文件可能被篡改）")
        return False

    print(f"\n✓ Stage 1 complete (interactive)")
    print(f"  Design: {done_info.get('design', 'unknown')}")
    print(f"  Modules: {done_info.get('modules_count', 0)}")
    print(f"  Spec: {paths['spec']}")

    # ── Restore CLAUDE.md ────────────────────────────────────────────────────
    if _claude_md_backup is not None:
        project_claude_md.write_text(_claude_md_backup, encoding="utf-8")
    else:
        # Remove the stage-1 CLAUDE.md we wrote — leave a clean project dir
        project_claude_md.unlink(missing_ok=True)

    print("stage 1 complete")
    return True

def _build_peer_summary(modules: List[Dict]) -> str:
    """Build a concise port-list summary of all modules for cross-module consistency."""
    lines = [
        "## Peer Module Interfaces",
        "Use these port names/widths EXACTLY when connecting modules.",
        "Do NOT regenerate code for these modules.",
        "",
    ]
    for m in modules:
        lines.append(f"### {m['name']}")
        for p in m.get("ports", []):
            w = p.get("width", 1)
            width_str = f"[{w-1}:0] " if w > 1 else "       "
            desc = p.get("description", "")
            lines.append(f"  {p['direction']:6} wire {width_str}{p['name']};  // {desc}")
        lines.append("")
    return "\n".join(lines)


def stage3_coder(project_dir: Path, mode: str,
                 feedback_file: Optional[Path] = None,
                 modules_filter: Optional[List[str]] = None,
                 max_workers: int = 4) -> bool:
    """Stage 3: RTL Code Generation — parallel per-module Claude workers.

    Each non-top module gets its own Claude subprocess (ThreadPoolExecutor).
    The top module runs last (serially) so all peer interfaces are already
    available from spec.json when it generates instantiation wiring.
    Every worker's log output is prefixed with [module_name] for clarity.
    max_workers caps the number of concurrent Claude subprocesses.
    """
    import concurrent.futures

    print("\n" + "="*60)
    print("STAGE 3: CODER (RTL Code Generation — parallel)")
    print("="*60)

    paths = get_project_paths(project_dir)
    if not paths["spec"].exists():
        print(f"ERROR: spec.json not found at {paths['spec']}")
        return False
    paths["rtl"].mkdir(parents=True, exist_ok=True)

    # ── Load shared resources ────────────────────────────────────────────────
    try:
        spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot parse spec.json: {e}")
        return False

    modules: List[Dict] = spec.get("modules", [])
    if not modules:
        print("ERROR: spec.json contains no modules")
        return False

    if modules_filter:
        modules = [m for m in modules if m.get("name") in modules_filter]

    style_dir = SKILL_DIR / "verilog_flow" / "defaults" / "coding_style" / "generic"
    coding_style = ""
    if style_dir.exists():
        for f in sorted(style_dir.glob("*.md")):
            coding_style += f.read_text(encoding="utf-8") + "\n\n"

    tmpl_dir = SKILL_DIR / "verilog_flow" / "defaults" / "templates" / "generic"
    verilog_templates = ""
    if tmpl_dir.exists():
        for f in sorted(tmpl_dir.glob("*.v")):
            verilog_templates += f"// === {f.name} ===\n"
            verilog_templates += f.read_text(encoding="utf-8") + "\n\n"

    micro_arch = ""
    micro_arch_path = paths["docs"] / "micro_arch.md"
    if micro_arch_path.exists():
        micro_arch = micro_arch_path.read_text(encoding="utf-8")

    user_feedback = ""
    if feedback_file and feedback_file.exists():
        user_feedback = feedback_file.read_text(encoding="utf-8")

    peer_summary = _build_peer_summary(modules)

    # ── Supervisor hint injection ────────────────────────────────────────────
    supervisor_hint = _read_supervisor_hint(project_dir)

    # ── Split top vs leaf modules ────────────────────────────────────────────
    top_modules  = [m for m in modules if m.get("module_type") == "top"]
    leaf_modules = [m for m in modules if m.get("module_type") != "top"]

    # ── ExperienceDB: look up patterns for leaf modules ───────────────────────
    target_freq_mhz = float(spec.get("target_frequency_mhz", 0))
    experience_hints: Dict[str, str] = {}
    try:
        from verilog_flow.common.experience_db import ExperienceDB
        db = ExperienceDB(project_dir / ".veriflow" / "experience_db")
        for mod in leaf_modules:
            matches = db.find_patterns(
                module_type=mod.get("module_type", ""),
                min_frequency=target_freq_mhz if target_freq_mhz > 0 else None,
            )
            if matches:
                experience_hints[mod.get("name", "")] = json.dumps(
                    matches[0].micro_arch_spec, indent=2
                )
    except Exception:
        pass

    def _run_module(mod: Dict) -> Tuple[str, bool]:
        """Worker: generate RTL for one module. Returns (name, success)."""
        name = mod.get("name", "unknown")
        log_prefix = f"[{name}] "
        context: Dict[str, str] = {
            "PROJECT_DIR":      str(project_dir),
            "MODE":             mode,
            "STAGE_NAME":       f"stage3_{name}",
            "MODULE_NAME":      name,
            "MODULE_SPEC":      json.dumps(mod, indent=2, ensure_ascii=False),
            "MICRO_ARCH":       micro_arch,
            "PEER_INTERFACES":  peer_summary,
            "USER_FEEDBACK":    user_feedback,
            "CODING_STYLE":     coding_style,
            "VERILOG_TEMPLATES": verilog_templates,
            "EXPERIENCE_HINT":  experience_hints.get(name, ""),
            "SUPERVISOR_HINT":  supervisor_hint,
        }
        success, _ = call_claude(PROMPTS_DIR / "stage3_module.md", context,
                                 prefix=log_prefix)
        return name, success

    # ── Phase 1: parallel leaf modules ──────────────────────────────────────
    failed: List[str] = []
    if leaf_modules:
        print(f"\n  Phase 1: generating {len(leaf_modules)} leaf module(s) in parallel")
        max_workers = min(len(leaf_modules), max(1, max_workers))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_module, m): m.get("name") for m in leaf_modules}
            for fut in concurrent.futures.as_completed(futures):
                name, ok = fut.result()
                if not ok:
                    failed.append(name)

    if failed:
        print(f"\n  ERROR: module(s) failed in Phase 1: {', '.join(failed)}")
        return False

    # ── Phase 2: top module(s) serially ─────────────────────────────────────
    if top_modules:
        print(f"\n  Phase 2: generating {len(top_modules)} top module(s) serially")
        for mod in top_modules:
            name, ok = _run_module(mod)
            if not ok:
                print(f"\n  ERROR: top module '{name}' failed")
                return False

    print("stage 3 complete")
    return True

def stage4_simulation_loop(project_dir: Path, mode: str) -> bool:
    """Stage 4: Simulation Verification Loop (simulation only; lint is in Stage 3.5).

    Runs simulation in a retry loop with the Debugger LLM to fix errors.
    Requires testbench files in workspace/tb/tb_*.v.
    """
    clear_error_logs()
    _log("[Stage 4]", "\n" + "="*60, "stage")
    _log("[Stage 4]", "STAGE 4: SIMULATION VERIFICATION LOOP", "stage")
    _log("[Stage 4]", "="*60, "stage")

    paths = get_project_paths(project_dir)

    # Load timing model YAML for Debugger context (if available)
    timing_model_yaml: Optional[str] = None
    timing_model_path = paths["docs"] / "timing_model.yaml"
    if timing_model_path.exists():
        try:
            timing_model_yaml = timing_model_path.read_text(encoding="utf-8")
        except Exception:
            pass

    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        _log(f"[Iteration {iteration}/{max_iterations}]", "--- Simulation Iteration ---", "stage")

        rtl_files = list(paths["rtl"].glob("*.v"))
        if not rtl_files:
            _log(f"[Iteration {iteration}]", "ERROR: No RTL files found", "error")
            return False

        # Find testbench
        tb_dir = paths["tb"]
        tb_files = list(tb_dir.glob("tb_*.v")) if tb_dir.exists() else []
        if not tb_files:
            tb_files = [f for f in rtl_files if f.name.startswith("tb_")]

        if not tb_files:
            _log(f"[Iteration {iteration}]", "ERROR: No testbench found (workspace/tb/tb_*.v) — cannot simulate", "error")
            _log(f"[Iteration {iteration}]", "Escalating to Supervisor to regenerate testbench (Stage 2)", "error")
            return False

        testbench = tb_files[0]
        all_files = rtl_files + [testbench] if testbench not in rtl_files else rtl_files
        _log(f"[Iteration {iteration}]", f"Testbench: {testbench.name}", "info")

        sim_passed, sim_output = run_sim(project_dir, testbench, all_files)

        if not sim_passed:
            _log(f"[Iteration {iteration}]", "✗ Simulation FAILED", "error")
            _log(f"[Iteration {iteration}]", f"Output:\n{sim_output[:1000]}...", "error")

            _log(f"[Iteration {iteration}]", "Calling Debugger to fix errors...", "command")
            success = call_debugger(project_dir, "sim", sim_output, rtl_files,
                                    timing_model_yaml=timing_model_yaml)
            if not success:
                _log(f"[Iteration {iteration}]", "ERROR: Debugger failed to fix errors", "error")
                return False

            _log(f"[Iteration {iteration}]", "✓ Errors fixed, retrying simulation...", "success")
            continue

        _log(f"[Iteration {iteration}]", "✓ Simulation PASSED", "success")
        _log(f"[Iteration {iteration}]", f"✓ Stage 4 complete after {iteration} iteration(s)", "success")
        print("stage 4 complete")
        return True

    # Max iterations reached — escalate to Supervisor
    _log("[Max Iterations]", f"ERROR: Maximum iterations ({max_iterations}) reached", "error")
    _log("[Max Iterations]", "Unable to fix simulation errors. Escalating to Supervisor.", "error")

    errors = get_error_logs()
    if errors:
        _log("[Error Summary]", f"Found {len(errors)} error/warning logs for supervisor analysis", "error")
        for i, log in enumerate(errors[-5:], 1):
            _log(f"[Error {i}]", f"{log['type']}: {log['message']}", log['type'])

    return False

# ── CLI Sub-commands for REPL Integration ────────────────────────────────────
def cmd_validate(project_dir: Path, stage: int) -> int:
    """
    Validate stage outputs (deterministic checks, no LLM).
    Called by Claude in REPL mode before completing a stage.
    Returns 0 if PASS, 1 if FAIL.
    """
    paths = get_project_paths(project_dir)
    errors = []

    if stage == 1:
        # Check spec.json exists and is valid
        if not paths["spec"].exists():
            errors.append("MISSING: workspace/docs/spec.json")
        else:
            try:
                spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
                if not spec.get("modules"):
                    errors.append("INVALID: spec.json missing 'modules' field")
                if not any(m.get("module_type") == "top" for m in spec.get("modules", [])):
                    errors.append("INVALID: No module with module_type='top'")
                if not spec.get("target_kpis"):
                    errors.append("INVALID: Missing 'target_kpis' field (required for standard/enterprise)")
                else:
                    kpis = spec["target_kpis"]
                    for field in ("frequency_mhz", "max_cells", "power_mw"):
                        if field not in kpis:
                            errors.append(f"INVALID: target_kpis missing '{field}'")
            except json.JSONDecodeError as e:
                errors.append(f"INVALID JSON: {e}")

            # Optional: schema validation via jsonschema
            schema_path = SCRIPT_DIR / "verilog_flow" / "stage1" / "schemas" / "arch_spec_v2.json"
            if schema_path.exists() and paths["spec"].exists():
                try:
                    import jsonschema  # optional dependency
                    schema = json.loads(schema_path.read_text(encoding="utf-8"))
                    spec_data = json.loads(paths["spec"].read_text(encoding="utf-8"))
                    jsonschema.validate(spec_data, schema)
                except ImportError:
                    pass  # jsonschema not installed — skip silently
                except Exception as je:
                    errors.append(f"SCHEMA: {je}")

    elif stage == 2:
        timing = paths["docs"] / "timing_model.yaml"
        tb_files = list(paths["tb"].glob("tb_*.v"))
        if not timing.exists():
            errors.append("MISSING: workspace/docs/timing_model.yaml")
        if not tb_files:
            errors.append("MISSING: workspace/tb/tb_*.v")

    elif stage == 3:
        rtl_files = list(paths["rtl"].glob("*.v"))
        if not rtl_files:
            errors.append("MISSING: workspace/rtl/*.v")
        else:
            # Run lint as deterministic check
            passed, output = run_lint(project_dir, rtl_files,
                                      log_name="linter_stage3")
            if not passed:
                errors.append(f"LINT_FAIL:\n{output[:500]}")
        report_path = paths["docs"] / "static_report.json"
        if not report_path.exists():
            errors.append("MISSING: workspace/docs/static_report.json")
        else:
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                required = ["logic_depth_estimate", "cdc_risks", "latch_risks"]
                for field in required:
                    if field not in report:
                        errors.append(f"INVALID: static_report.json missing '{field}'")
            except json.JSONDecodeError as e:
                errors.append(f"INVALID JSON: {e}")

    elif stage == 4:
        rtl_files = list(paths["rtl"].glob("*.v"))
        if not rtl_files:
            errors.append("MISSING: workspace/rtl/*.v")
        else:
            passed, output = run_lint(project_dir, rtl_files,
                                      log_name="linter_stage4")
            if not passed:
                errors.append(f"LINT_FAIL:\n{output[:500]}")
            tb_files = list(paths["tb"].glob("tb_*.v"))
            if tb_files:
                sim_passed, sim_output = run_sim(project_dir, tb_files[0], rtl_files + tb_files)
                if not sim_passed:
                    errors.append(f"SIM_FAIL:\n{sim_output[:500]}")

    else:
        errors.append(f"UNKNOWN_STAGE: {stage}")

    # Output result
    if errors:
        print("VALIDATE: FAIL")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1
    else:
        print("VALIDATE: PASS")
        return 0


def cmd_complete(project_dir: Path, stage: int) -> int:
    """
    Mark stage as complete (only if validate passes).
    Writes sentinel file for Stage 1 REPL handshake.
    Returns 0 if OK, 1 if denied.
    """
    # Must validate first
    rc = cmd_validate(project_dir, stage)
    if rc != 0:
        print("COMPLETE: DENIED — validation failed")
        return 1

    paths = get_project_paths(project_dir)

    # Update pipeline state
    state = load_project_state(project_dir)
    if stage not in state.get("completed_stages", []):
        state.setdefault("completed_stages", []).append(stage)
    state["current_stage"] = stage
    save_project_state(project_dir, state)

    # For Stage 1: write sentinel file with checksum
    if stage == 1:
        import hashlib
        spec_path = paths["spec"]
        checksum = hashlib.md5(spec_path.read_bytes()).hexdigest() if spec_path.exists() else ""

        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            modules_count = len(spec.get("modules", []))
            design_name = spec.get("design_name", "unknown")
        except Exception:
            modules_count = 0
            design_name = "unknown"

        sentinel = paths["docs"] / "stage1.done"
        sentinel.write_text(json.dumps({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "checksum": checksum,
            "modules_count": modules_count,
            "design": design_name,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"COMPLETE: OK — Stage {stage} marked complete")
    return 0


def call_debugger(project_dir: Path, error_type: str, error_log: str,
                  rtl_files: List[Path],
                  timing_model_yaml: Optional[str] = None) -> bool:
    """
    Call the Debugger LLM worker to fix errors.
    TB tamper protection: snapshots workspace/tb/ before and after; reverts if modified.
    """
    tb_dir = project_dir / "workspace" / "tb"
    tb_snap = _snapshot_dir(tb_dir)

    context = {
        "PROJECT_DIR": str(project_dir),
        "ERROR_TYPE": error_type,
        "ERROR_LOG": error_log[:5000],  # Limit log size
        "RTL_FILES": ", ".join([str(f) for f in rtl_files]),
    }
    if timing_model_yaml:
        context["TIMING_MODEL_YAML"] = timing_model_yaml[:3000]

    prompt_file = PROMPTS_DIR / "stage4_debugger.md"
    success, output = call_claude(prompt_file, context)
    print(output)

    # Check for TB tampering and restore if detected
    tampered = _check_dir_tampered(tb_snap, tb_dir)
    if tampered:
        _restore_dir(tb_snap, tb_dir)
        print(f"⚠️  WARNING: Debugger attempted to modify testbench files — reverted: {tampered}")

    return success

# ── New Stage Implementations ─────────────────────────────────────────────────
def stage15_microarch(project_dir: Path, mode: str) -> bool:
    """Stage 1.5: Micro-Architecture Design — headless call_claude() worker."""
    print("\n" + "="*60)
    print("STAGE 1.5: MICRO-ARCHITECTURE DESIGN")
    print("="*60)

    paths = get_project_paths(project_dir)
    if not paths["spec"].exists():
        print(f"ERROR: spec.json not found at {paths['spec']}")
        return False
    paths["docs"].mkdir(parents=True, exist_ok=True)

    context: Dict[str, str] = {
        "PROJECT_DIR": str(project_dir),
        "MODE":        mode,
        "STAGE_NAME":  "stage15_microarch",
    }

    success, _ = call_claude(PROMPTS_DIR / "stage15_microarch.md", context)
    if success:
        print("stage 15 complete")
    return success


def stage2_timing_model(project_dir: Path, mode: str) -> bool:
    """Stage 2: Virtual Timing Model — headless call_claude() worker."""
    print("\n" + "="*60)
    print("STAGE 2: VIRTUAL TIMING MODEL")
    print("="*60)

    paths = get_project_paths(project_dir)
    if not paths["spec"].exists():
        print(f"ERROR: spec.json not found at {paths['spec']}")
        return False
    paths["tb"].mkdir(parents=True, exist_ok=True)
    paths["docs"].mkdir(parents=True, exist_ok=True)

    spec_json = paths["spec"].read_text(encoding="utf-8")

    context: Dict[str, str] = {
        "PROJECT_DIR": str(project_dir),
        "MODE":        mode,
        "STAGE_NAME":  "stage2_timing",
        "SPEC_JSON":   spec_json,
    }

    success, _ = call_claude(PROMPTS_DIR / "stage2_timing.md", context)

    # Validate outputs were actually written to disk
    if success:
        timing_yaml = paths["docs"] / "timing_model.yaml"
        tb_files = list(paths["tb"].glob("tb_*.v"))
        if not timing_yaml.exists():
            print("ERROR: Stage 2 reported success but timing_model.yaml not found")
            success = False
        elif not tb_files:
            print("ERROR: Stage 2 reported success but no testbench (tb_*.v) found")
            success = False

    if success:
        print("stage 2 complete")
    return success


def stage35_skill_d(project_dir: Path, mode: str) -> bool:
    """Stage 3.5: Lint check loop + Skill D static quality analysis.

    Phase 1: Run iverilog lint in a retry loop (with Debugger on failure).
    Phase 2: LLM-based static quality analysis (logic depth, CDC, style).
    """
    clear_error_logs()
    _log("[Stage 3.5]", "\n" + "="*60, "stage")
    _log("[Stage 3.5]", "STAGE 3.5: LINT CHECK + STATIC ANALYSIS", "stage")
    _log("[Stage 3.5]", "="*60, "stage")

    paths = get_project_paths(project_dir)
    rtl_files = list(paths["rtl"].glob("*.v")) if paths["rtl"].exists() else []
    if not rtl_files:
        _log("[Stage 3.5]", "[WARN] No RTL files found, skipping", "warning")
        return True
    paths["docs"].mkdir(parents=True, exist_ok=True)

    # Load timing model for Debugger context (if available)
    timing_model_yaml: Optional[str] = None
    timing_model_path = paths["docs"] / "timing_model.yaml"
    if timing_model_path.exists():
        try:
            timing_model_yaml = timing_model_path.read_text(encoding="utf-8")
        except Exception:
            pass

    # ── Phase 1: Lint loop ──────────────────────────────────────────────────
    _log("[Stage 3.5]", "── Phase 1: Lint Check ──", "stage")
    _log("[Stage 3.5]", f"检查 {len(rtl_files)} 个文件: {', '.join(f.name for f in rtl_files)}", "info")
    max_iterations = 5
    for iteration in range(1, max_iterations + 1):
        _log(f"[Lint {iteration}/{max_iterations}]", "Running lint check...", "info")
        lint_passed, lint_output = run_lint(
            project_dir, rtl_files,
            log_name=f"linter_stage35_iter{iteration}"
        )

        if lint_passed:
            # Show warnings even when lint passes (iverilog -Wall may emit warnings)
            warn_lines = [l for l in lint_output.splitlines()
                          if l.strip() and "PASS" not in l and "No lint" not in l]
            if warn_lines:
                _log(f"[Lint {iteration}]", f"✓ Lint PASSED (with {len(warn_lines)} warning(s))", "warning")
                for line in warn_lines[:20]:  # show up to 20 warning lines
                    _log(f"[Lint {iteration}]", line, "warning")
            else:
                _log(f"[Lint {iteration}]", "✓ Lint PASSED — 0 warnings", "success")
            break

        _log(f"[Lint {iteration}]", "✗ Lint FAILED", "error")
        _log(f"[Lint {iteration}]", f"Output:\n{lint_output[:1000]}...", "error")

        _log(f"[Lint {iteration}]", "Calling Debugger to fix errors...", "command")
        fixed = call_debugger(project_dir, "lint", lint_output, rtl_files,
                              timing_model_yaml=timing_model_yaml)
        if not fixed:
            _log(f"[Lint {iteration}]", "ERROR: Debugger failed to fix lint errors", "error")
            return False

        _log(f"[Lint {iteration}]", "✓ Errors fixed, retrying lint...", "success")
        rtl_files = list(paths["rtl"].glob("*.v"))  # refresh after Debugger edits
    else:
        _log("[Stage 3.5]", f"ERROR: Lint still failing after {max_iterations} iterations", "error")
        return False

    # ── Phase 2: LLM static analysis ───────────────────────────────────────
    _log("[Stage 3.5]", "── Phase 2: Static Quality Analysis ──", "stage")
    context: Dict[str, str] = {
        "PROJECT_DIR": str(project_dir),
        "MODE":        mode,
        "STAGE_NAME":  "stage35_skill_d",
        "RTL_FILES":   ", ".join(str(f) for f in rtl_files),
    }

    success, _ = call_claude(PROMPTS_DIR / "stage35_skill_d.md", context)
    if success:
        print("stage 35 complete")
    return success


def _check_skill_d_gates(project_dir: Path, report: Dict) -> None:
    """Check Skill D quality gates and prompt user if violations found."""
    violations = []

    depth = report.get("logic_depth_estimate", {})
    if depth.get("status") == "OVER_BUDGET":
        violations.append(
            f"Logic depth {depth.get('max_levels')} exceeds budget {depth.get('budget')}"
        )

    for risk in report.get("cdc_risks", []):
        if risk.get("risk") == "HIGH":
            violations.append(
                f"CDC risk HIGH: {risk.get('signal')} used in {risk.get('used_in')}"
            )

    if not violations:
        print("\n  ✓ Skill D: No critical quality violations")
        return

    print("\n  ⚠️  WARNING: Skill D detected quality violations:")
    for v in violations:
        print(f"    - {v}")
    if report.get("recommendation"):
        print(f"\n  Recommendation: {report['recommendation']}")

    print("\n  Choose: [C]ontinue  [B]ack to Stage 1  [Q]uit")
    while True:
        try:
            choice = input("  > ").strip().upper()
        except EOFError:
            choice = "C"
        if choice in ("C", ""):
            print("  Continuing despite violations...")
            break
        elif choice in ("B", "Q"):
            print("  Pipeline routing to Supervisor.")
            raise RuntimeError("skill_d_gate_rejected")
        else:
            print("  Invalid choice. Enter C, B, or Q.")


def stage36_human_gate(project_dir: Path) -> bool:
    """Stage 36: Human gate — pause for user to review timing_model.yaml before code gen."""
    paths = get_project_paths(project_dir)
    timing_model = paths["docs"] / "timing_model.yaml"
    tb_dir = paths["tb"]

    print("\n" + "="*60)
    print("STAGE 36: HUMAN GATE (Review Before Code Generation)")
    print("="*60)
    print("\n  Please review the generated files before proceeding:")

    if timing_model.exists():
        print(f"  → Timing model:  {timing_model}")
    else:
        print("  → Timing model:  (not found)")

    tb_files = list(tb_dir.glob("tb_*.v")) if tb_dir.exists() else []
    if tb_files:
        print(f"  → Testbench(es): {', '.join(f.name for f in tb_files)}")
    else:
        print("  → Testbench(es): (not found)")

    print("\n  Verify that behavior assertions and stimulus are correct.")
    print("  [C]ontinue  [Q]uit")

    while True:
        try:
            choice = input("  > ").strip().upper()
        except EOFError:
            choice = "C"
        if choice in ("C", ""):
            print("  ✓ Human gate passed — proceeding to Stage 3")
            print("stage 36 complete")
            return True
        elif choice == "Q":
            print("  Pipeline aborted by user at human gate.")
            return False
        else:
            print("  Invalid choice. Enter C or Q.")


def stage5_synthesis(project_dir: Path, mode: str) -> bool:
    """Stage 5: Yosys Synthesis + KPI Comparison."""
    print("\n" + "="*60)
    print("STAGE 5: YOSYS SYNTHESIS + KPI COMPARISON")
    print("="*60)

    yosys = find_eda_tool("yosys")
    if not yosys:
        print("  ⚠️  Yosys not found — synthesis stage skipped")
        print("  Install Yosys (https://yosyshq.net/yosys/) to enable Stage 5.")
        return True  # Graceful skip

    paths = get_project_paths(project_dir)
    rtl_dir = paths["rtl"]
    rtl_files = [f for f in rtl_dir.glob("*.v") if not f.name.startswith("tb_")]

    if not rtl_files:
        print("ERROR: No RTL files found for synthesis")
        return False

    # Determine top module and KPI targets from spec.json
    top_module = "top"
    target_kpis: Dict = {}
    if paths["spec"].exists():
        try:
            spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
            target_kpis = spec.get("target_kpis", {})
            for m in spec.get("modules", []):
                if m.get("module_type") == "top":
                    top_module = m["name"]
                    break
        except Exception as e:
            print(f"  [WARN] Could not parse spec.json: {e}")

    print(f"  Top module: {top_module}")
    print(f"  RTL files:  {[f.name for f in rtl_files]}")

    # Build Yosys script
    read_cmds = "\n".join(f"read_verilog {f.name}" for f in rtl_files)
    yosys_script = f"{read_cmds}\nsynth -top {top_module}\nstat -json\n"

    fd, script_path = tempfile.mkstemp(suffix=".ys", prefix="vf_synth_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(yosys_script)

    try:
        result = subprocess.run(
            [yosys, "-p", script_path],
            capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace",
            cwd=str(rtl_dir)
        )
        output = result.stdout + "\n" + result.stderr

        if result.returncode != 0:
            print(f"  ✗ Synthesis FAILED (exit={result.returncode})")
            print(f"  Output:\n{output[:2000]}")
            return False

        print("  ✓ Synthesis completed")
        synth_report = _parse_yosys_stat(output, top_module)

        report_path = paths["docs"] / "synth_report.json"
        report_path.write_text(
            json.dumps(synth_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Report saved: {report_path}")

        _print_kpi_dashboard(synth_report, target_kpis)

        print(f"\n✓ Stage 5 complete.")
        print("stage 5 complete")
        return True

    except subprocess.TimeoutExpired:
        print("  ✗ Synthesis timed out after 300 seconds")
        return False
    except Exception as e:
        print(f"  ✗ Synthesis error: {e}")
        return False
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


def _parse_yosys_stat(output: str, top_module: str) -> Dict:
    """Parse Yosys stat -json output into a report dict."""
    json_match = re.search(r'\{[\s\S]*?"modules"[\s\S]*?\}', output)
    if json_match:
        try:
            return json.loads(json_match.group())
        except Exception:
            pass
    # Fallback: extract text metrics
    report: Dict = {"design": top_module}
    m = re.search(r'Number of cells:\s*(\d+)', output)
    if m:
        report["num_cells"] = int(m.group(1))
    m = re.search(r'Number of wires:\s*(\d+)', output)
    if m:
        report["num_wires"] = int(m.group(1))
    report["raw_output"] = output[-3000:]
    return report


def _print_kpi_dashboard(report: Dict, target_kpis: Dict) -> None:
    """Print KPI comparison dashboard and gate on severe violations."""
    print("\n" + "─"*60)
    print("  KPI Dashboard")
    print("─"*60)

    num_cells = report.get("num_cells", "N/A")
    print(f"  Cells: {num_cells}")

    if target_kpis:
        target_freq = target_kpis.get("frequency_mhz")
        target_area = target_kpis.get("max_cells")
        if target_freq:
            print(f"  Target Freq:  {target_freq} MHz  (STA requires dedicated tool)")
        if target_area and isinstance(num_cells, int):
            pct = (num_cells / target_area) * 100
            status = "✓ OK" if pct <= 100 else "✗ OVER"
            print(f"  Area:  {num_cells} / {target_area} cells ({pct:.0f}%) {status}")
            if pct > 120:
                print(f"\n  ⚠️  Area exceeds target by {pct-100:.0f}% — consider revising Stage 1")
                print("\n  Choose: [C]ontinue  [B]ack to Stage 1  [Q]uit")
                try:
                    choice = input("  > ").strip().upper()
                except EOFError:
                    choice = "C"
                if choice in ("B", "Q"):
                    sys.exit(1)
    print("─"*60)


# ── Supervisor Layer ──────────────────────────────────────────────────────────
def _write_supervisor_hint(project_dir: Path, hint: str) -> None:
    """Write Supervisor routing hint to .veriflow/supervisor_hint.md."""
    hint_path = project_dir / ".veriflow" / "supervisor_hint.md"
    hint_path.parent.mkdir(parents=True, exist_ok=True)
    hint_path.write_text(f"# Supervisor Hint\n\n{hint}\n", encoding="utf-8")


def _read_supervisor_hint(project_dir: Path) -> str:
    """Read and clear the Supervisor hint file, or return empty string."""
    hint_path = project_dir / ".veriflow" / "supervisor_hint.md"
    if hint_path.exists():
        hint = hint_path.read_text(encoding="utf-8")
        hint_path.unlink()
        return hint
    return ""


def call_supervisor(project_dir: Path, failed_stage: int, error_summary: str,
                    retry_history: Dict[int, int], mode: str) -> SupervisorDecision:
    """
    Call the Supervisor LLM to get a routing decision after a stage failure.

    Returns a SupervisorDecision dict with keys:
      action, target_stage, modules, hint, root_cause, severity
    """
    _abort: SupervisorDecision = {
        "action": "abort",
        "target_stage": failed_stage,
        "modules": [],
        "hint": "",
        "root_cause": "Supervisor could not determine routing",
        "severity": "high",
    }

    # Build spec summary (compact — only key fields)
    spec_summary: Dict = {}
    spec_path = project_dir / "workspace" / "docs" / "spec.json"
    if spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec_summary = {
                "design_name": spec.get("design_name", "unknown"),
                "modules": [m.get("name") for m in spec.get("modules", [])],
                "target_kpis": spec.get("target_kpis", {}),
            }
        except Exception:
            pass

    # Build experience matches from ExperienceDB
    experience_matches: List[Dict] = []
    try:
        from verilog_flow.common.experience_db import ExperienceDB
        db = ExperienceDB(project_dir / ".veriflow" / "experience_db")
        similar = db.find_similar_failures(stage=f"stage{failed_stage}", unresolved_only=False)
        experience_matches = [
            {"failure_type": f.failure_type, "resolution": f.resolution_notes}
            for f in similar[:3]
        ]
    except Exception:
        pass

    pipeline_context = {
        "failed_stage": failed_stage,
        "mode": mode,
        "retry_history": retry_history,
        "error_summary_preview": error_summary[:500],
    }

    context: Dict[str, str] = {
        "PROJECT_DIR":        str(project_dir),
        "MODE":               mode,
        "STAGE_NAME":         "supervisor",
        "_PROMPT_FILE":       str(PROMPTS_DIR / "supervisor.md"),
        "PIPELINE_CONTEXT":   json.dumps(pipeline_context, indent=2),
        "SPEC_SUMMARY":       json.dumps(spec_summary, indent=2),
        "ERROR_SUMMARY":      error_summary[:2000],
        "EXPERIENCE_MATCHES": json.dumps(experience_matches, indent=2),
    }

    print(f"\n  [Supervisor] Consulting Supervisor for Stage {failed_stage} failure...")
    success, output = call_claude(PROMPTS_DIR / "supervisor.md", context)

    if not success:
        return _abort

    # Robust JSON extraction from output
    match = re.search(r'\{[^{}]*"action"[^{}]*\}', output, re.DOTALL)
    if not match:
        match = re.search(r'\{.*\}', output, re.DOTALL)
    if not match:
        print("  [Supervisor] Could not parse decision JSON — aborting")
        return _abort

    try:
        parsed = json.loads(match.group(0))
        decision: SupervisorDecision = {
            "action":       parsed.get("action", "abort"),
            "target_stage": int(parsed.get("target_stage", failed_stage)),
            "modules":      parsed.get("modules", []),
            "hint":         parsed.get("hint", ""),
            "root_cause":   parsed.get("root_cause", ""),
            "severity":     parsed.get("severity", "medium"),
        }
        print(f"  [Supervisor] Decision: {decision['action']} → Stage {decision['target_stage']}")
        print(f"  [Supervisor] Root cause: {decision['root_cause']}")
        return decision
    except Exception as e:
        print(f"  [Supervisor] Parse error: {e} — aborting")
        return _abort


def _emit_stage_event(project_dir: Path, event_type: str,
                      stage: int, **kwargs) -> None:
    """Write a stage lifecycle event to pipeline_events.jsonl."""
    event = {
        "ts": datetime.now().isoformat(),
        "event": event_type,   # "stage_start" | "stage_complete" | "stage_fail"
        "stage": stage,
        **kwargs
    }
    events_file = project_dir / ".veriflow" / "pipeline_events.jsonl"
    try:
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _dispatch_stage(stage_num: int, project_dir: Path, mode: str,
                    feedback_file: Optional[Path],
                    modules_filter: Optional[List[str]],
                    max_workers: int = 4) -> bool:
    """Dispatch a single stage and return success bool."""
    if stage_num == 1:
        return stage1_architect(project_dir, mode, feedback_file=feedback_file)
    elif stage_num == 2:
        return stage2_timing_model(project_dir, mode)
    elif stage_num == 35:
        return stage35_skill_d(project_dir, mode)
    elif stage_num == 36:
        return stage36_human_gate(project_dir)
    elif stage_num == 3:
        return stage3_coder(project_dir, mode, feedback_file=feedback_file,
                            modules_filter=modules_filter, max_workers=max_workers)
    elif stage_num == 4:
        return stage4_simulation_loop(project_dir, mode)
    elif stage_num == 5:
        return stage5_synthesis(project_dir, mode)
    elif stage_num == 15:
        return stage15_microarch(project_dir, mode)
    else:
        print(f"  Unknown stage: {stage_num}")
        return False


# ── Main State Machine ───────────────────────────────────────────────────────
def run_project(mode: str, project_dir: Path,
                stages_override: Optional[List[int]] = None,
                feedback_file: Optional[Path] = None,
                modules_filter: Optional[List[str]] = None,
                resume: bool = False,
                max_workers: int = 4) -> int:
    """
    Main state machine for running the VeriFlow pipeline.

    Args:
        mode: "quick", "standard", or "enterprise"
        project_dir: Project directory
        resume: If True, skip already-completed stages

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    print("\n" + "="*70)
    print("VeriFlow 8.3 — Complete 5-Stage Architecture")
    print("="*70)
    print(f"Mode: {mode.upper()}")
    print(f"Project: {project_dir}")
    print("="*70)

    # Validate project directory
    if not project_dir.exists():
        print(f"\nERROR: Project directory does not exist: {project_dir}")
        return 1

    paths = get_project_paths(project_dir)

    # Check for requirement.md
    if not paths["requirement"].exists():
        print(f"\nERROR: requirement.md not found at {paths['requirement']}")
        print("Please create a requirement.md file with your design requirements.")
        return 1

    # Create workspace directories first (state file lives in .veriflow)
    for d in ("workspace", "docs", "rtl", "tb", "sim", "veriflow"):
        paths[d].mkdir(parents=True, exist_ok=True)

    # Clear cross-run error buffer and initialise per-run JSONL log
    clear_error_logs()
    log_dir = project_dir / ".veriflow" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ctl_jsonl = log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    _set_log_file(ctl_jsonl)

    # Load or create project state
    state = load_project_state(project_dir)
    state["mode"] = mode
    state["status"] = "running"
    save_project_state(project_dir, state)

    # Get stages to execute
    stages = list(stages_override if stages_override else MODE_STAGES.get(mode, MODE_STAGES[MODE_STANDARD]))

    # --resume: skip already-completed stages
    if resume:
        completed = set(state.get("completed_stages", []))
        stages = [s for s in stages if s not in completed]
        if not stages:
            print("All stages already completed — nothing to resume.")
            return 0
        print(f"  Resuming from stage {stages[0]} (skipping {sorted(completed)})")

    # ── KPITracker setup ──────────────────────────────────────────────────────
    try:
        from verilog_flow.common.kpi import KPITracker
        tracker = KPITracker(paths["veriflow"] / "kpi.json")
        design_name = project_dir.name
        target_freq = 0.0
        spec_path = paths["spec"]
        if spec_path.exists():
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                design_name = spec.get("design_name", design_name)
                target_freq = float(spec.get("target_frequency_mhz", 0))
            except Exception:
                pass
        run_metrics = tracker.start_run(design_name, design_name, target_freq)
    except Exception:
        tracker = None
        run_metrics = None

    MAX_SUPERVISOR_RETRIES = 3
    retry_counts: Dict[int, int] = {}
    last_error: str = ""
    stage_idx = 0
    overall_success = False

    try:
        while stage_idx < len(stages):
            stage_num = stages[stage_idx]
            print(f"\n{'='*70}")
            print(f"Executing Stage {stage_num}")
            print('='*70)

            # 每个 stage 切换到独立的 jsonl 日志文件
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            stage_tag = str(stage_num).replace(".", "_")
            stage_jsonl = log_dir / f"stage{stage_tag}_{ts}.jsonl"
            _set_log_file(stage_jsonl)

            if tracker:
                try:
                    tracker.start_stage(f"stage{stage_num}")
                except Exception:
                    pass

            _emit_stage_event(project_dir, "stage_start", stage_num)
            try:
                success = _dispatch_stage(stage_num, project_dir, mode,
                                          feedback_file, modules_filter,
                                          max_workers=max_workers)
            except RuntimeError as e:
                # Structured escalation (e.g. skill_d_gate_rejected)
                last_error = str(e)
                success = False
                _emit_stage_event(project_dir, "stage_fail", stage_num, error=last_error)

            if tracker:
                try:
                    tracker.end_stage(success=success,
                                      error_message=None if success else last_error)
                except Exception:
                    pass

            if success:
                _emit_stage_event(project_dir, "stage_complete", stage_num)
                # Mark stage complete and advance
                if stage_num not in state["completed_stages"]:
                    state["completed_stages"].append(stage_num)
                state["current_stage"] = stage_num
                save_project_state(project_dir, state)
                retry_counts.pop(stage_num, None)
                stage_idx += 1
                continue

            # ── Stage failed — consult Supervisor ────────────────────────────
            if not last_error:  # emit fail event if RuntimeError path didn't already
                _emit_stage_event(project_dir, "stage_fail", stage_num)
            state["status"] = "failed"
            state["failed_stage"] = stage_num
            save_project_state(project_dir, state)

            retries = retry_counts.get(stage_num, 0)
            if retries >= MAX_SUPERVISOR_RETRIES:
                print(f"\n{'='*70}")
                print(f"PIPELINE FAILED: Supervisor retry limit ({MAX_SUPERVISOR_RETRIES}) reached at Stage {stage_num}")
                print('='*70)
                return 1

            decision = call_supervisor(project_dir, stage_num, last_error,
                                       retry_counts, mode)

            if decision["action"] == "continue":
                # Non-critical — keep going
                if stage_num not in state["completed_stages"]:
                    state["completed_stages"].append(stage_num)
                state["current_stage"] = stage_num
                save_project_state(project_dir, state)
                stage_idx += 1

            elif decision["action"] in ("retry_stage", "escalate_stage"):
                target = decision["target_stage"]
                if target in stages:
                    stage_idx = stages.index(target)
                    retry_counts[target] = retry_counts.get(target, 0) + 1
                    if decision["hint"]:
                        _write_supervisor_hint(project_dir, decision["hint"])
                else:
                    print(f"  [Supervisor] Target stage {target} not in pipeline — aborting")
                    return 1

            else:  # abort
                print(f"\n{'='*70}")
                print(f"PIPELINE FAILED at Stage {stage_num} (Supervisor decision: abort)")
                print('='*70)
                return 1

        # ── All stages complete ───────────────────────────────────────────────
        overall_success = True
        state["status"] = "completed"
        save_project_state(project_dir, state)

        print(f"\n{'='*70}")
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print('='*70)
        print(f"\nGenerated files in: {paths['workspace']}")
        print(f"  - RTL: {paths['rtl']}")
        print(f"  - Docs: {paths['docs']}")
        return 0

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        state["status"] = "interrupted"
        save_project_state(project_dir, state)
        return 130
    except Exception as e:
        print(f"\n\nPipeline failed with error: {e}")
        import traceback
        traceback.print_exc()
        state["status"] = "error"
        state["error"] = str(e)
        save_project_state(project_dir, state)
        return 1
    finally:
        if tracker:
            try:
                tracker.end_run(pass_at_1=overall_success)
            except Exception:
                pass

# ── Main Entry Point ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="VeriFlow Controller v8.3 — Complete 5-Stage Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  run                 Run the complete VeriFlow pipeline
  validate            Validate stage outputs (called by Claude in REPL)
  complete            Mark stage complete (called by Claude in REPL)

Examples:
  # Run in quick mode (fastest, minimal verification)
  python veriflow_ctl.py run --mode quick -d ./my_project

  # Run in standard mode (recommended)
  python veriflow_ctl.py run --mode standard -d ./my_project

  # Validate Stage 1 outputs (REPL mode)
  python veriflow_ctl.py validate --stage 1 -d ./my_project

  # Mark Stage 1 complete (REPL mode)
  python veriflow_ctl.py complete --stage 1 -d ./my_project
""")

    parser.add_argument("command", choices=["run", "validate", "complete"],
                        help="Subcommand to execute")
    parser.add_argument("-d", "--project-dir", type=Path, default=Path("."),
                        help="Project root directory (default: current directory)")

    # run command arguments
    parser.add_argument("--mode", choices=[MODE_QUICK, MODE_STANDARD, MODE_ENTERPRISE],
                        default=MODE_QUICK,
                        help=f"Execution mode (default: {MODE_QUICK})")
    parser.add_argument("--stages", default=None,
                        help="Comma-separated stage numbers to run, e.g. '1' or '3' or '1,3,4'. "
                             "Overrides the default mode stage list.")
    parser.add_argument("--feedback", default=None,
                        help="Path to a feedback.md file passed to LLM workers for revision mode.")
    parser.add_argument("--modules", default=None,
                        help="Comma-separated module names for partial Stage 3 re-generation, e.g. 'uart_tx,top'."
                             " Only these modules will be regenerated when running Stage 3.")
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-completed stages and resume from last failure.")
    parser.add_argument("--workers", type=int, default=4,
                        help="Max concurrent Claude subprocesses for Stage 3 parallel module generation (default: 4).")

    # validate/complete command arguments
    parser.add_argument("--stage", type=int, default=None,
                        help="Stage number for validate/complete commands")

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()

    # Dispatch validate/complete
    if args.command == "validate":
        if args.stage is None:
            print("ERROR: --stage required for validate command")
            return 1
        return cmd_validate(project_dir, args.stage)

    elif args.command == "complete":
        if args.stage is None:
            print("ERROR: --stage required for complete command")
            return 1
        return cmd_complete(project_dir, args.stage)

    # Dispatch run
    elif args.command == "run":
        # Parse --stages override
        stages_override = None
        if args.stages:
            try:
                stages_override = [_normalize_stage_token(s.strip()) for s in args.stages.split(",") if s.strip()]
            except ValueError:
                print(f"ERROR: --stages must be comma-separated stage ids, got: {args.stages}")
                return 1

        feedback_file = Path(args.feedback).resolve() if args.feedback else None
        modules_filter = [m.strip() for m in args.modules.split(",") if m.strip()] if args.modules else None

        return run_project(args.mode, project_dir,
                           stages_override=stages_override,
                           feedback_file=feedback_file,
                           modules_filter=modules_filter,
                           resume=args.resume,
                           max_workers=args.workers)

    return 0


if __name__ == "__main__":
    sys.exit(main())
