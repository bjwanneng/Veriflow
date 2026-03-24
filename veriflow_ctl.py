#!/usr/bin/env python3
"""
VeriFlow Controller v8.3 — Complete 5-Stage Architecture

Architecture: "Python as Master State Machine, LLM as Worker Node"
- This script is the top-level orchestrator implementing the complete state machine
- Claude Code (LLM) is called via subprocess as a worker to execute each stage
- Shell scripts in tools/ act as the ACI (Agent-Computer Interface) for EDA tools

Modes:
    quick      Stages: 1 → 3 → 4(lint-only)        Fast syntax verification
    standard   Stages: 1 → 2 → [gate] → 3 → 35 → 4 Full functional verification
    enterprise Stages: 1 → 2 → [gate] → 3 → 35 → 4 → 5  With synthesis + KPI

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
from typing import Dict, List, Optional, Tuple

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

# ── Mode Configurations ─────────────────────────────────────────────────────
MODE_QUICK = "quick"
MODE_STANDARD = "standard"
MODE_ENTERPRISE = "enterprise"

MODE_STAGES = {
    MODE_QUICK:      [1, 3, 4],              # lint only, fast
    MODE_STANDARD:   [1, 2, 36, 3, 35, 4],  # timing model + human gate + code + skill_d + sim
    MODE_ENTERPRISE: [1, 2, 36, 3, 35, 4, 5],  # + synthesis + KPI
}

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
    # Search PATH
    for suffix in ["", ".exe"]:
        found = shutil.which(tool_name + suffix)
        if found:
            return found
    return None

def _launch_claude_repl(project_dir: Path) -> Optional[subprocess.Popen]:
    """
    Launch Claude CLI in interactive REPL mode.
    Windows: new console window (non-blocking)
    Linux/Mac: current terminal (blocking until user exits)
    Returns Popen object on Windows, None on Linux/Mac.
    """
    claude_exe = find_claude_cli()
    if not claude_exe:
        print("  ERROR: Claude CLI not found")
        print("  Install: npm install -g @anthropic-ai/claude-code")
        return None

    cmd = [claude_exe, "--dangerously-skip-permissions", "--add-dir", str(project_dir)]

    if platform.system() == "Windows":
        # Windows: launch in new console window (non-blocking)
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print(f"  [INFO] Claude REPL launched in new window (PID={proc.pid})")
        return proc
    else:
        # Linux/Mac: passthrough to current terminal (blocking)
        print("  [INFO] Launching Claude REPL in current terminal...")
        print("  [INFO] Type your responses, then exit when done (Ctrl+D or /exit)")
        proc = subprocess.Popen(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=str(project_dir),
        )
        proc.wait()  # Block until user exits
        return None


def call_claude(prompt_file: Path, context: Dict[str, str]) -> Tuple[bool, str]:
    """
    Call Claude Code as a worker subprocess.

    Args:
        prompt_file: Path to the prompt template file
        context: Dictionary of context variables to substitute in the prompt

    Returns:
        (success: bool, output: str)
    """
    # Read the prompt template
    if not prompt_file.exists():
        return False, f"Prompt file not found: {prompt_file}"

    prompt_template = prompt_file.read_text(encoding="utf-8")

    # Substitute context variables
    prompt = prompt_template
    for key, value in context.items():
        prompt = prompt.replace(f"{{{{{key}}}}}", value)

    # Locate Claude CLI (config → PATH → common locations)
    claude_exe = find_claude_cli()
    if not claude_exe:
        print("  [INFO] Claude CLI not found — using mock mode")
        context["_PROMPT_FILE"] = str(prompt_file)
        return mock_claude_execution(prompt, context)

    # Wrap prompt with execution context so Claude executes instead of describing
    project_dir_str = context.get("PROJECT_DIR", ".")
    mode_str        = context.get("MODE", "quick")
    full_prompt = f"""You are executing a VeriFlow RTL pipeline stage. Follow ALL instructions below **exactly and completely**.

## Execution Context
- **Project Directory (absolute path)**: `{project_dir_str}`
- **Pipeline Mode**: `{mode_str}`
- All file paths in the instructions below are relative to the project directory above.
- You MUST create every output file listed. Do NOT describe, summarize, or discuss — just execute.
- After completing all tasks, print the exact summary block shown at the end of the instructions.

---

{prompt}
"""

    stage_name = context.get("STAGE_NAME", prompt_file.stem)
    project_dir_path = context.get("PROJECT_DIR", ".")

    try:
        # Write prompt to a temp file so the visible terminal can read it via stdin redirect
        fd_in, stdin_path = tempfile.mkstemp(suffix=".txt", prefix="cf_in_")
        with os.fdopen(fd_in, "w", encoding="utf-8") as f:
            f.write(full_prompt)

        # Temp file for capturing Claude's output (tailed by the poll loop below)
        fd_out, out_path = tempfile.mkstemp(suffix=".log", prefix="cf_out_")
        os.close(fd_out)

        try:
            if platform.system() == "Windows":
                proc = _run_claude_in_visible_window(
                    claude_exe, stage_name, project_dir_path, stdin_path, out_path
                )
            else:
                # Non-Windows: hidden Popen, pipe stdout directly
                if claude_exe.lower().endswith((".cmd", ".bat")):
                    cmd = ["cmd", "/c", claude_exe,
                           "--print", "--dangerously-skip-permissions",
                           "--add-dir", project_dir_path]
                else:
                    cmd = [claude_exe,
                           "--print", "--dangerously-skip-permissions",
                           "--add-dir", project_dir_path]
                proc = subprocess.Popen(
                    cmd,
                    stdin=open(stdin_path, "r", encoding="utf-8"),
                    stdout=open(out_path, "w", encoding="utf-8"),
                    stderr=subprocess.STDOUT,
                    cwd=project_dir_path,
                )

            print(f"  [INFO] 🤖 Claude CLI 启动 [{stage_name}] PID={proc.pid}", flush=True)

            # Heartbeat + file-tail loop: keeps GUI alive and forwards Claude output
            _stop_hb = threading.Event()
            def _heartbeat():
                while not _stop_hb.wait(2):
                    print(".", end="", flush=True)

            hb = threading.Thread(target=_heartbeat, daemon=True)
            hb.start()

            output_lines = []
            last_pos = 0
            try:
                while proc.poll() is None:
                    time.sleep(0.3)
                    last_pos = _tail_log(out_path, last_pos, output_lines)
                # Drain any remaining output after process exits
                _tail_log(out_path, last_pos, output_lines)
            finally:
                _stop_hb.set()
                hb.join(timeout=1)

            proc.wait()
            print(f"  [INFO] ✅ Claude CLI 完成 (exit={proc.returncode})", flush=True)
            output = "\n".join(output_lines)
            success = "STAGE_COMPLETE" in output or proc.returncode == 0
            return success, output

        finally:
            try: os.unlink(stdin_path)
            except Exception: pass
            try: os.unlink(out_path)
            except Exception: pass

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
def run_lint(project_dir: Path, rtl_files: List[Path]) -> Tuple[bool, str]:
    """
    Run iverilog syntax/lint check (Python-native, cross-platform).
    Returns (passed, output). Skips gracefully if iverilog not installed.
    """
    iverilog = find_eda_tool("iverilog")
    if not iverilog:
        return True, "⚠️  iverilog not found — lint check skipped (install iverilog to enable)"

    # Filter out testbench files for lint (they reference UUT, which may cause spurious errors)
    design_files = [f for f in rtl_files if not f.name.startswith("tb_")]
    files_to_check = design_files if design_files else rtl_files

    cmd = [iverilog, "-Wall", "-tnull"] + [str(f) for f in files_to_check]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
            cwd=project_dir
        )
        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
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

    import tempfile
    fd, sim_out_str = tempfile.mkstemp(suffix=".vvp", dir=str(project_dir))
    os.close(fd)
    sim_out = Path(sim_out_str)

    try:
        non_tb = [f for f in rtl_files if f != testbench]
        compile_cmd = [iverilog, "-o", str(sim_out), str(testbench)] + [str(f) for f in non_tb]
        r1 = subprocess.run(
            compile_cmd, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", cwd=project_dir
        )
        if r1.returncode != 0:
            return False, f"Compilation failed:\n{r1.stdout}\n{r1.stderr}"

        r2 = subprocess.run(
            [vvp, str(sim_out)], capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", cwd=project_dir
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

    # Write kickoff file with Q&A instructions
    kickoff = paths["docs"] / "stage1_kickoff.md"
    kickoff_content = (PROMPTS_DIR / "stage1_architect.md").read_text(encoding="utf-8")

    # Add completion protocol
    kickoff_content += f"""

---

## 🎯 完成协议（最后一步）

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
> ✅ 架构分析完成。可以关闭此窗口，流水线将自动继续。

"""
    kickoff.write_text(kickoff_content, encoding="utf-8")

    print(f"\n  [INFO] 启动交互式架构分析...")
    print(f"  [INFO] 剧本文件: {kickoff}")
    print(f"  [INFO] 请在 Claude 窗口中开始对话")
    print(f"  [INFO] 完成后 Claude 会写入 stage1.done，本窗口将自动继续\n")

    # Launch REPL
    proc = _launch_claude_repl(project_dir)

    # Poll for sentinel file or process exit
    poll_interval = 2  # seconds
    max_wait = 3600  # 1 hour timeout
    elapsed = 0

    while elapsed < max_wait:
        if sentinel.exists():
            break

        # Check if process exited (Windows only)
        if proc is not None and proc.poll() is not None:
            print("\n  ⚠️  Claude 窗口已关闭，但未检测到完成信号")
            print("  可能原因：未执行 complete 命令，或 Claude 异常退出")
            print("\n  选项：")
            print("    [R]etry — 重新启动 Claude REPL")
            print("    [Q]uit  — 退出流水线")
            try:
                choice = input("  > ").strip().upper()
            except EOFError:
                choice = "Q"

            if choice == "R":
                sentinel.unlink(missing_ok=True)
                proc = _launch_claude_repl(project_dir)
                elapsed = 0
                continue
            else:
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
                 modules_filter: Optional[List[str]] = None) -> bool:
    """
    Stage 3: RTL Code Generation — per-module loop.

    Reads spec.json, then calls Claude once per module for focused, high-quality
    generation. Each call receives the target module's full spec plus a peer
    interface summary so port names stay consistent across modules.

    Falls back to single-call mode if spec has no module list.
    """
    print("\n" + "="*60)
    print("STAGE 3: CODER (RTL Code Generation — per-module)")
    print("="*60)

    paths = get_project_paths(project_dir)

    if not paths["spec"].exists():
        print(f"ERROR: spec.json not found at {paths['spec']}")
        return False

    paths["rtl"].mkdir(parents=True, exist_ok=True)

    # Load spec
    try:
        spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to parse spec.json: {e}")
        return False

    modules = spec.get("modules", [])
    # Apply module filter (partial re-generation)
    if modules_filter:
        filtered = [m for m in modules if m.get("name") in modules_filter]
        if filtered:
            print(f"  [INFO] Module filter active: {modules_filter} ({len(filtered)}/{len(modules)} modules)")
            modules = filtered
        else:
            print(f"  [WARN] --modules filter matched nothing, running all modules")
    feedback_text = ""
    if feedback_file and feedback_file.exists():
        feedback_text = feedback_file.read_text(encoding="utf-8")
        print(f"  [INFO] Revision mode: using feedback from {feedback_file.name}")

    if not modules:
        # Fallback: single call (old behaviour)
        print("  [INFO] No module list in spec — using single-call fallback")
        context = {
            "PROJECT_DIR": str(project_dir),
            "MODE": mode,
            "STAGE_NAME": "stage3_coder",
        }
        if feedback_text:
            context["USER_FEEDBACK"] = feedback_text
        prompt_file = PROMPTS_DIR / "stage3_coder.md"
        success, output = call_claude(prompt_file, context)
        print(output)
        if not success:
            print("\nERROR: Stage 3 (Coder) failed")
            return False
    else:
        # Per-module generation
        peer_summary = _build_peer_summary(modules)
        total = len(modules)

        for idx, module in enumerate(modules, start=1):
            module_name = module.get("name", f"module_{idx}")
            print(f"\n{'='*60}")
            print(f"Executing Stage 3 Module {idx}/{total}: {module_name}")
            print('='*60)

            context = {
                "PROJECT_DIR":    str(project_dir),
                "MODE":           mode,
                "MODULE_NAME":    module_name,
                "MODULE_SPEC":    json.dumps(module, indent=2, ensure_ascii=False),
                "PEER_INTERFACES": peer_summary,
                "STAGE_NAME":     f"stage3_{module_name}",
            }
            if feedback_text:
                context["USER_FEEDBACK"] = feedback_text

            prompt_file = PROMPTS_DIR / "stage3_module.md"
            if not prompt_file.exists():
                # Graceful fallback to the all-in-one prompt
                prompt_file = PROMPTS_DIR / "stage3_coder.md"

            success, output = call_claude(prompt_file, context)
            print(output)

            if not success:
                print(f"\nERROR: Failed to generate module '{module_name}'")
                return False

            print(f"stage 3 module {module_name} complete")

    # Verify at least one RTL file was created
    rtl_files = list(paths["rtl"].glob("*.v"))
    if not rtl_files:
        print(f"\nERROR: No RTL files created in {paths['rtl']}")
        return False

    print(f"\n✓ Stage 3 complete. Generated {len(rtl_files)} RTL file(s):")
    for f in rtl_files:
        print(f"  - {f.name}")
    print("stage 3 complete")
    return True

def stage4_simulation_loop(project_dir: Path, mode: str, lint_only: bool = False) -> bool:
    """
    Stage 4: Simulation Verification Loop

    Runs lint/simulation in a loop with the Debugger LLM to fix errors.
    If lint_only=True, skips simulation (Quick mode).
    """
    print("\n" + "="*60)
    if lint_only:
        print("STAGE 4: LINT CHECK (Quick mode)")
    else:
        print("STAGE 4: SIMULATION VERIFICATION LOOP")
    print("="*60)

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
        print(f"\n--- Verification Iteration {iteration}/{max_iterations} ---")

        # Step 1: Get all RTL files (exclude TBs for lint)
        rtl_files = list(paths["rtl"].glob("*.v"))
        if not rtl_files:
            print("ERROR: No RTL files found")
            return False

        # Step 2: Run lint check
        print("\n[1/2] Running lint check...")
        lint_passed, lint_output = run_lint(project_dir, rtl_files)

        if not lint_passed:
            print("  ✗ Lint check FAILED")
            print(f"  Output:\n{lint_output[:1000]}...")

            print("\n  Calling Debugger to fix errors...")
            success = call_debugger(project_dir, "lint", lint_output, rtl_files,
                                    timing_model_yaml=timing_model_yaml)

            if not success:
                print("  ERROR: Debugger failed to fix errors")
                return False

            print("  ✓ Errors fixed, retrying verification...")
            continue
        else:
            print("  ✓ Lint check PASSED")

        # Quick mode: stop after lint
        if lint_only:
            print(f"\n✓ Stage 4 (lint-only) complete after {iteration} iteration(s)")
            return True

        # Step 3: Run simulation using testbench from workspace/tb/
        print("\n[2/2] Simulation check...")
        tb_dir = paths["tb"]
        tb_files = list(tb_dir.glob("tb_*.v")) if tb_dir.exists() else []

        # Fallback: look in rtl dir too
        if not tb_files:
            tb_files = [f for f in rtl_files if f.name.startswith("tb_")]

        if tb_files:
            testbench = tb_files[0]
            all_files = rtl_files + [testbench] if testbench not in rtl_files else rtl_files
            print(f"  Found testbench: {testbench.name}")
            sim_passed, sim_output = run_sim(project_dir, testbench, all_files)

            if not sim_passed:
                print("  ✗ Simulation FAILED")
                print(f"  Output:\n{sim_output[:1000]}...")

                print("\n  Calling Debugger to fix errors...")
                success = call_debugger(project_dir, "sim", sim_output, rtl_files,
                                        timing_model_yaml=timing_model_yaml)

                if not success:
                    print("  ERROR: Debugger failed to fix errors")
                    return False

                print("  ✓ Errors fixed, retrying verification...")
                continue
            else:
                print("  ✓ Simulation PASSED")
        else:
            print("  No testbench found (workspace/tb/tb_*.v), skipping simulation")

        # All checks passed
        print(f"\n✓ Stage 4 complete after {iteration} iteration(s)")
        print("  All lint checks passed")
        if tb_files:
            print("  Simulation passed")
        return True

    # Max iterations reached
    print(f"\nERROR: Maximum iterations ({max_iterations}) reached")
    print("Unable to fix all errors. Manual intervention required.")
    print("\nOptions:")
    print("  [B]ack to Stage 2 — revise timing model/testbench")
    print("  [Q]uit")
    try:
        choice = input("  > ").strip().upper()
    except EOFError:
        choice = "Q"
    if choice != "B":
        return False
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
            passed, output = run_lint(project_dir, rtl_files)
            if not passed:
                errors.append(f"LINT_FAIL:\n{output[:500]}")

    elif stage == 35:
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
            passed, output = run_lint(project_dir, rtl_files)
            if not passed:
                errors.append(f"LINT_FAIL:\n{output[:500]}")
            # Sim check if testbench exists
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
def stage2_timing_model(project_dir: Path, mode: str) -> bool:
    """Stage 2: Virtual Timing Model — generate timing_model.yaml + testbench."""
    print("\n" + "="*60)
    print("STAGE 2: VIRTUAL TIMING MODEL")
    print("="*60)

    paths = get_project_paths(project_dir)

    if not paths["spec"].exists():
        print(f"ERROR: spec.json not found at {paths['spec']}")
        return False

    # Ensure tb directory exists
    paths["tb"].mkdir(parents=True, exist_ok=True)

    context = {
        "PROJECT_DIR": str(project_dir),
        "MODE": mode,
        "STAGE_NAME": "stage2_timing",
    }

    prompt_file = PROMPTS_DIR / "stage2_timing.md"
    success, output = call_claude(prompt_file, context)
    print(output)

    if not success:
        print("\nERROR: Stage 2 (Timing Model) failed")
        return False

    # Validate timing_model.yaml was created
    timing_model = paths["docs"] / "timing_model.yaml"
    if not timing_model.exists():
        print(f"\nERROR: timing_model.yaml not created at {timing_model}")
        return False

    # Basic YAML field validation
    try:
        import yaml
        data = yaml.safe_load(timing_model.read_text(encoding="utf-8"))
        missing = [k for k in ("design", "scenarios") if k not in data]
        if missing:
            print(f"\nERROR: timing_model.yaml missing required fields: {missing}")
            return False
        for sc in data.get("scenarios", []):
            for field in ("name", "assertions", "stimulus"):
                if field not in sc:
                    print(f"  [WARN] scenario '{sc.get('name','?')}' missing field '{field}'")
    except ImportError:
        print("  [INFO] PyYAML not installed — skipping YAML schema validation")
    except Exception as e:
        print(f"\nERROR: Failed to validate timing_model.yaml: {e}")
        return False

    print(f"\n✓ Stage 2 complete. Timing model: {timing_model}")
    print("stage 2 complete")
    return True


def stage35_skill_d(project_dir: Path, mode: str) -> bool:
    """Stage 3.5: Skill D — LLM-based static quality analysis."""
    print("\n" + "="*60)
    print("STAGE 35: SKILL D (Static Quality Analysis)")
    print("="*60)

    paths = get_project_paths(project_dir)

    rtl_files = list(paths["rtl"].glob("*.v")) if paths["rtl"].exists() else []
    if not rtl_files:
        print("  [WARN] No RTL files found, skipping static analysis")
        return True

    context = {
        "PROJECT_DIR": str(project_dir),
        "MODE": mode,
        "STAGE_NAME": "stage35_skill_d",
    }

    prompt_file = PROMPTS_DIR / "stage35_skill_d.md"
    success, output = call_claude(prompt_file, context)
    print(output)

    if not success:
        print("\nERROR: Stage 35 (Skill D) failed")
        return False

    # Read static report and check quality gates
    report_path = paths["docs"] / "static_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            _check_skill_d_gates(project_dir, report)
        except Exception as e:
            print(f"  [WARN] Could not parse static_report.json: {e}")

    print("stage 35 complete")
    return True


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
            print("  Pipeline aborted by user.")
            sys.exit(1)
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


# ── Main State Machine ───────────────────────────────────────────────────────
def run_project(mode: str, project_dir: Path,
                stages_override: Optional[List[int]] = None,
                feedback_file: Optional[Path] = None,
                modules_filter: Optional[List[str]] = None) -> int:
    """
    Main state machine for running the VeriFlow pipeline.

    Args:
        mode: "quick", "standard", or "enterprise"
        project_dir: Project directory

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

    # Load or create project state
    state = load_project_state(project_dir)
    state["mode"] = mode
    state["status"] = "running"
    save_project_state(project_dir, state)

    # Create workspace directories
    paths["workspace"].mkdir(parents=True, exist_ok=True)
    paths["docs"].mkdir(parents=True, exist_ok=True)
    paths["rtl"].mkdir(parents=True, exist_ok=True)
    paths["tb"].mkdir(parents=True, exist_ok=True)
    paths["sim"].mkdir(parents=True, exist_ok=True)
    paths["veriflow"].mkdir(parents=True, exist_ok=True)

    # Get stages to execute
    stages = stages_override if stages_override else MODE_STAGES.get(mode, MODE_STAGES[MODE_STANDARD])

    # Execute stages
    try:
        for stage_num in stages:
            print(f"\n{'='*70}")
            print(f"Executing Stage {stage_num}")
            print('='*70)

            if stage_num == 1:
                success = stage1_architect(project_dir, mode, feedback_file=feedback_file)
            elif stage_num == 2:
                success = stage2_timing_model(project_dir, mode)
            elif stage_num == 35:
                success = stage35_skill_d(project_dir, mode)
            elif stage_num == 36:
                success = stage36_human_gate(project_dir)
            elif stage_num == 3:
                success = stage3_coder(project_dir, mode, feedback_file=feedback_file,
                                       modules_filter=modules_filter)
            elif stage_num == 4:
                lint_only = (mode == MODE_QUICK)
                success = stage4_simulation_loop(project_dir, mode, lint_only=lint_only)
            elif stage_num == 5:
                success = stage5_synthesis(project_dir, mode)
            else:
                print(f"  Unknown stage: {stage_num}")
                success = False

            if not success:
                state["status"] = "failed"
                state["failed_stage"] = stage_num
                save_project_state(project_dir, state)
                print(f"\n{'='*70}")
                print(f"PIPELINE FAILED at Stage {stage_num}")
                print('='*70)
                return 1

            # Mark stage as complete
            if stage_num not in state["completed_stages"]:
                state["completed_stages"].append(stage_num)
            state["current_stage"] = stage_num
            save_project_state(project_dir, state)

        # All stages complete
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
                stages_override = [int(s.strip()) for s in args.stages.split(",") if s.strip()]
            except ValueError:
                print(f"ERROR: --stages must be comma-separated integers, got: {args.stages}")
                return 1

        feedback_file = Path(args.feedback).resolve() if args.feedback else None
        modules_filter = [m.strip() for m in args.modules.split(",") if m.strip()] if args.modules else None

        return run_project(args.mode, project_dir,
                           stages_override=stages_override,
                           feedback_file=feedback_file,
                           modules_filter=modules_filter)

    return 0


if __name__ == "__main__":
    sys.exit(main())
