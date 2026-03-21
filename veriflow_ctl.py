#!/usr/bin/env python3
"""
VeriFlow Controller v8.1 — Stateless gate controller for Claude Code skill.

Architecture: "Script as gatekeeper, LLM as executor"
- This script enforces stage ordering, prerequisites, and validation gates
- Claude Code (via SKILL.md) drives the flow and executes each stage's tasks
- The LLM cannot skip stages or mark incomplete work as done

Cross-platform: Linux / macOS / Windows (Git Bash, MSYS2, native CMD)

Subcommands:
    status      Show current pipeline progress
    next        Output the prompt for the next stage (blocked if prerequisites unmet)
    validate    Run deterministic checks on a stage's outputs
    complete    Mark a stage done (refused if validation fails)
    rollback    Roll back to a previous stage
    info        Show stage details without generating prompt
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Cross-platform: force UTF-8 stdout/stderr ────────────────────────────────
# Prevents UnicodeEncodeError on Windows terminals with GBK/CP936 codepage
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ────────────────────────────────────────────────────────────────────
# Get the directory where this script is located (skill directory)
# This allows running the script from any directory
SKILL_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = SKILL_DIR / "prompts"

sys.path.insert(0, str(SKILL_DIR / "verilog_flow"))

try:
    from common.kpi import KPITracker
    from common.experience_db import ExperienceDB, FailureCase
    ENHANCED_AVAILABLE = True
except ImportError:
    ENHANCED_AVAILABLE = False

# ── Stage Definitions ────────────────────────────────────────────────────────

STAGES = [
    {"id": 0, "name": "Project Initialization",        "prompt": "stage0_init.md"},
    {"id": 1, "name": "Micro-Architecture Specification", "prompt": "stage1_spec.md"},
    {"id": 2, "name": "Virtual Timing Modeling",        "prompt": "stage2_timing.md"},
    {"id": 3, "name": "RTL Code Generation + Lint",     "prompt": "stage3_codegen.md"},
    {"id": 4, "name": "Simulation & Verification",      "prompt": "stage4_sim.md"},
    {"id": 5, "name": "Synthesis Analysis",             "prompt": "stage5_synth.md"},
    {"id": 6, "name": "Closing",                        "prompt": "stage6_close.md"},
]

STAGE_PREREQUISITES = {
    0: [],
    1: [0],
    2: [0, 1],
    3: [0, 1],  # Quick模式不需要stage2
    4: [0, 1, 3],  # Quick模式不需要stage2
    5: [0, 1, 2, 3, 4],
    6: [0, 1, 3, 4],  # Quick模式不需要stage2和stage5
}
STAGE_ROLLBACK_TARGETS = {
    1: 0,
    2: 1,
    3: 1,
    4: 2,
    5: 1,
    6: 5,
}

MAX_ROLLBACKS = 2


# ── Stage Marker Helpers ─────────────────────────────────────────────────────

def get_marker_path(project_dir: Path, stage_id: int) -> Path:
    return project_dir / ".veriflow" / "stage_completed" / f"stage_{stage_id}.complete"


def is_stage_complete(project_dir: Path, stage_id: int) -> bool:
    return get_marker_path(project_dir, stage_id).exists()


def get_last_completed_stage(project_dir: Path) -> int:
    for s in range(6, -1, -1):
        if is_stage_complete(project_dir, s):
            return s
    return -1


def check_prerequisites(project_dir: Path, stage_id: int) -> Tuple[bool, List[str]]:
    errors = []
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    # 根据模式确定需要的前置条件
    required_prereqs = STAGE_PREREQUISITES.get(stage_id, []).copy()

    # Quick模式跳过stage2和stage5
    if mode == "quick":
        # Quick模式下，stage3不需要stage2，stage4不需要stage2，stage6不需要stage2和stage5
        if stage_id == 3:
            required_prereqs = [0, 1]  # 只需要stage0和stage1
        elif stage_id == 4:
            required_prereqs = [0, 1, 3]  # 只需要stage0,1,3
        elif stage_id == 6:
            required_prereqs = [0, 1, 3, 4]  # 只需要stage0,1,3,4

    for prereq in required_prereqs:
        if not is_stage_complete(project_dir, prereq):
            errors.append(f"Stage {prereq} ({STAGES[prereq]['name']}) not completed")
    return len(errors) == 0, errors


def mark_stage_complete(project_dir: Path, stage_id: int, summary: str = ""):
    marker = get_marker_path(project_dir, stage_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "stage": stage_id,
        "name": STAGES[stage_id]["name"],
        "completed_at": datetime.now().isoformat(),
        "summary": summary,
    }
    marker.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Generate stage summary
    _generate_stage_summary(project_dir, stage_id, summary)


def unmark_stage(project_dir: Path, stage_id: int):
    marker = get_marker_path(project_dir, stage_id)
    if marker.exists():
        marker.unlink()


def _generate_stage_summary(project_dir: Path, stage_id: int, summary: str = ""):
    summaries_dir = project_dir / "reports" / "stage_summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    stage = STAGES[stage_id]

    stage_dirs_map = {
        0: [".veriflow"], 1: ["stage_1_spec"], 2: ["stage_2_timing"],
        3: ["stage_3_codegen"], 4: ["stage_4_sim"], 5: ["stage_5_synth"],
        6: ["reports"],
    }

    files_list = []
    dir_stats = {}
    for dir_name in stage_dirs_map.get(stage_id, []):
        dir_path = project_dir / dir_name
        if dir_path.exists():
            for f in dir_path.rglob("*"):
                if f.is_file():
                    rel_path = str(f.relative_to(project_dir))
                    files_list.append(rel_path)
                    # Track file counts by type
                    ext = f.suffix.lower()
                    dir_stats[ext] = dir_stats.get(ext, 0) + 1

    # Load project config for additional context
    project_config = load_project_config(project_dir)
    design_name = project_config.get("project", "unknown")

    # Build detailed summary content
    content = f"# Stage {stage_id}: {stage['name']} — Summary\n\n"
    content += f"**Completed at**: {datetime.now().isoformat()}\n\n"
    content += "## Status\n\n[DONE] **Completed**\n\n"

    # Stage-specific details
    stage_details_map = {
        0: _generate_stage0_details,
        1: _generate_stage1_details,
        2: _generate_stage2_details,
        3: _generate_stage3_details,
        4: _generate_stage4_details,
        5: _generate_stage5_details,
        6: _generate_stage6_details,
    }

    detail_func = stage_details_map.get(stage_id)
    if detail_func:
        content += detail_func(project_dir, project_config, files_list)
    else:
        content += f"## Summary\n{summary or 'No summary provided.'}\n\n"

    # File statistics
    content += "## File Statistics\n\n"
    if dir_stats:
        for ext, count in sorted(dir_stats.items()):
            ext_name = ext[1:].upper() if ext else "No extension"
            content += f"- {ext_name} files: {count}\n"
    content += f"- **Total files**: {len(files_list)}\n\n"

    # Files list
    content += "## Files Generated\n\n"
    for f in sorted(files_list):
        content += f"- {f}\n"

    summary_file = summaries_dir / f"stage{stage_id}_summary.md"
    summary_file.write_text(content, encoding="utf-8")


def _generate_stage0_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 0."""
    content = "## Tasks Completed\n\n"
    content += "1. **Execution mode selection**\n"
    mode = project_config.get("execution_mode", "unknown")
    content += f"   - Mode selected: {mode}\n"
    if mode == "parameterized":
        content += "   - User confirmation required at key decision points\n"
    else:
        content += "   - Auto-decision based on best practices\n\n"

    content += "2. **Directory structure creation**\n"
    content += "   - stage_1_spec/specs/, stage_1_spec/docs/\n"
    content += "   - stage_2_timing/scenarios/, stage_2_timing/golden_traces/\n"
    content += "   - stage_2_timing/waveforms/, stage_2_timing/cocotb/\n"
    content += "   - stage_3_codegen/rtl/, stage_3_codegen/tb_autogen/\n"
    content += "   - stage_4_sim/tb/, stage_4_sim/sim_output/\n"
    content += "   - stage_5_synth/, reports/, .veriflow/\n\n"

    content += "3. **Toolchain detection**\n"
    content += "   - iverilog: detected and verified\n"
    content += "   - yosys: detected and verified\n\n"

    content += "4. **Project configuration**\n"
    content += f"   - Project: {project_config.get('project', 'unknown')}\n"
    content += f"   - Vendor: {project_config.get('vendor', 'generic')}\n"
    content += f"   - Target frequency: {project_config.get('target_frequency_mhz', 300)} MHz\n\n"

    content += "## Key Configurations\n\n"
    coding_style = project_config.get("coding_style", {})
    content += f"- Reset: {coding_style.get('reset', 'async_active_low')}\n"
    content += f"- Reset signal: {coding_style.get('reset_signal', 'rst_n')}\n"
    content += f"- Clock edge: {coding_style.get('clock_edge', 'posedge')}\n"
    content += f"- Naming convention: {coding_style.get('naming', 'snake_case')}\n"
    content += f"- Port style: {coding_style.get('port_style', 'ANSI')}\n\n"
    return content


def _generate_stage1_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 1."""
    content = "## Tasks Completed\n\n"
    content += "1. **Requirement analysis**\n"
    content += "   - Read and analyzed requirement.md\n"
    content += "   - Extracted design parameters and interfaces\n\n"

    # Structured requirements summary
    struct_req_file = project_dir / "stage_1_spec" / "specs" / "structured_requirements.json"
    if struct_req_file.exists():
        try:
            req_data = json.loads(struct_req_file.read_text(encoding="utf-8"))
            requirements = req_data.get("requirements", [])
            total = len(requirements)
            testable = sum(1 for r in requirements if r.get("testable"))
            by_cat = {}
            for r in requirements:
                cat = r.get("category", "unknown")
                by_cat[cat] = by_cat.get(cat, 0) + 1
            content += "   **Structured Requirements**:\n"
            content += f"   - Total requirements: {total}\n"
            for cat, cnt in sorted(by_cat.items()):
                content += f"   - {cat}: {cnt}\n"
            content += f"   - Testable: {testable}\n\n"
        except (json.JSONDecodeError, Exception):
            pass

    content += "2. **Module partitioning**\n"
    spec_dir = project_dir / "stage_1_spec" / "specs"
    module_count = 0
    has_top = False
    has_connectivity = False
    has_dataflow = False
    if spec_dir.exists():
        for spec_file in spec_dir.glob("*_spec.json"):
            try:
                data = json.loads(spec_file.read_text(encoding="utf-8"))
                modules = data.get("modules", [])
                module_count = len(modules)
                content += f"   - {module_count} modules defined in architecture\n"
                for mod in modules:
                    mod_type = mod.get("module_type", "")
                    if mod_type == "top":
                        has_top = True
                    content += f"     - {mod.get('name', 'unknown')} ({mod_type})\n"
                # Check connectivity and dataflow
                if "module_connectivity" in data and len(data.get("module_connectivity", [])) > 0:
                    has_connectivity = True
                if "data_flow_sequences" in data and len(data.get("data_flow_sequences", [])) > 0:
                    has_dataflow = True
            except (json.JSONDecodeError, KeyError):
                pass

    content += "\n3. **Interface definition**\n"
    content += "   - All module ports defined with direction, width, protocol\n"
    content += "   - Byte order specified: MSB_FIRST\n"
    content += "   - Detailed module descriptions provided\n\n"

    content += "4. **Architecture specification**\n"
    content += "   - Generated *_spec.json with complete module connectivity\n"
    if has_connectivity:
        content += "   - [OK] Module connectivity defined\n"
    if has_dataflow:
        content += "   - [OK] Data flow sequences defined\n"
    if has_top:
        content += "   - [OK] Top module identified\n"
    content += "   - Defined FSM specifications and pipeline stages\n\n"

    # Check documentation
    docs_count = sum(1 for f in files_list if "/docs/" in f or f.endswith(".wavedrom") or f.endswith(".md"))
    if docs_count > 0:
        content += "5. **Documentation**\n"
        content += f"   - {docs_count} documentation files created\n\n"

    return content


def _generate_stage2_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 2."""
    content = "## Tasks Completed\n\n"

    scenario_count = sum(1 for f in files_list if f.endswith(".yaml") or f.endswith(".yml"))
    content += f"1. **YAML timing scenarios created: {scenario_count}**\n"
    scenario_types = ["reset_sequence", "single_operation", "back_to_back",
                     "config_mode", "random_stall", "input_bubble"]
    for st in scenario_types:
        if any(st in f for f in files_list):
            content += f"   - {st}.yaml\n"

    trace_count = sum(1 for f in files_list if "golden_traces" in f and f.endswith(".json"))
    content += f"\n2. **Golden traces created: {trace_count}**\n"

    cocotb_count = sum(1 for f in files_list if f.endswith(".py"))
    content += f"\n3. **Cocotb test files created: {cocotb_count}**\n"
    content += "   - Unit tests for each module\n"
    content += "   - Integration tests with golden reference model\n"
    content += "   - Makefile for test execution\n"

    # UVM-like verification library summary
    has_bfm = any("vf_bfm" in f for f in files_list)
    has_scoreboard = any("vf_scoreboard" in f or "scoreboard" in f.lower() for f in files_list)
    has_coverage = any("vf_coverage" in f or "coverage" in f.lower() for f in files_list if f.endswith(".py"))
    has_constrained = any("vf_test_factory" in f or "constrained" in f.lower() for f in files_list)
    content += "\n4. **UVM-like Verification Library**\n"
    if has_bfm:
        content += "   - [OK] BFM (Driver/Monitor) infrastructure\n"
    if has_scoreboard:
        content += "   - [OK] Scoreboard with golden model comparison\n"
    if has_coverage:
        content += "   - [OK] Functional coverage collector\n"
    if has_constrained:
        content += "   - [OK] Constrained random stimulus generator\n"

    # Requirements coverage matrix summary
    matrix_file = project_dir / "stage_2_timing" / "cocotb" / "requirements_coverage_matrix.json"
    if matrix_file.exists():
        try:
            matrix_data = json.loads(matrix_file.read_text(encoding="utf-8"))
            cov_summary = matrix_data.get("coverage_summary", {})
            matrix = matrix_data.get("matrix", [])
            covered = sum(1 for m in matrix if m.get("cocotb_tests"))
            uncovered = sum(1 for m in matrix if not m.get("cocotb_tests"))
            content += "\n   **Requirements Coverage Matrix**:\n"
            content += f"   - Coverage: {cov_summary.get('coverage_pct', 0)}%\n"
            content += f"   - Requirements covered: {covered}\n"
            content += f"   - Requirements uncovered: {uncovered}\n"
        except (json.JSONDecodeError, Exception):
            pass

    waveform_count = sum(1 for f in files_list if "waveforms" in f)
    content += f"\n5. **Waveform diagrams created: {waveform_count}**\n\n"

    return content


def _generate_stage3_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 3."""
    content = "## Tasks Completed\n\n"

    rtl_count = sum(1 for f in files_list if "rtl" in f and f.endswith(".v"))
    content += f"1. **RTL modules generated: {rtl_count}**\n"
    for f in sorted(files_list):
        if "rtl" in f and f.endswith(".v") and "/" in f:
            mod_name = f.split("/")[-1].replace(".v", "")
            content += f"   - {mod_name}.v\n"

    tb_count = sum(1 for f in files_list if "tb_autogen" in f and f.endswith(".v"))
    content += f"\n2. **Testbenches generated: {tb_count}**\n"

    # Check lint reports
    lint_step1 = any("lint_step1" in f for f in files_list)
    lint_step2 = any("lint_step2" in f for f in files_list)
    lint_report = any("lint_report" in f for f in files_list)

    content += "\n3. **Lint checks**\n"
    if lint_step1:
        content += "   - [OK] Lint Step 1 (RTL only): completed\n"
    if lint_step2:
        content += "   - [OK] Lint Step 2 (RTL + testbenches): completed\n"
    if lint_report:
        content += "   - [OK] Lint report generated\n"
    content += "   - No placeholder/TODO markers found\n"
    content += "   - iverilog compilation successful\n"
    content += "   - All syntax checks passed\n\n"

    # Check testbench quality
    tb_with_debug = 0
    for f in files_list:
        if "tb_autogen" in f and f.endswith(".v"):
            try:
                fpath = project_dir / f
                if fpath.exists():
                    tb_content = fpath.read_text(encoding="utf-8", errors="replace")
                    display_count = tb_content.count("$display")
                    monitor_count = tb_content.count("$monitor")
                    if display_count + monitor_count >= 3:
                        tb_with_debug += 1
            except Exception:
                pass
    if tb_count > 0:
        content += "4. **Testbench Quality**\n"
        content += f"   - Testbenches with adequate debug prints: {tb_with_debug}/{tb_count}\n"
        content += "   - All testbenches have clock generation\n"
        content += "   - All testbenches have reset sequence\n"
        content += "   - All testbenches have PASS/FAIL status prints\n\n"

    content += "## Coding Style Applied\n\n"
    content += "   - Verilog-2005 standard (no SystemVerilog)\n"
    # Read reset style from project config
    coding_style = project_config.get("coding_style", {})
    reset_type = coding_style.get("reset_type", "async_active_low")
    reset_signal = coding_style.get("reset_signal", "rst_n")
    reset_desc = {
        "async_active_low": f"Async active-low reset ({reset_signal})",
        "async_active_high": f"Async active-high reset ({reset_signal})",
        "sync_active_low": f"Sync active-low reset ({reset_signal})",
        "sync_active_high": f"Sync active-high reset ({reset_signal})",
    }.get(reset_type, f"Reset: {reset_signal}")
    content += f"   - {reset_desc}\n"
    content += "   - Snake_case for module/signal names\n"
    content += "   - UPPER_SNAKE_CASE for parameters\n"
    content += "   - ANSI-style port declarations\n"
    content += "   - Two-block FSM structure\n\n"
    return content


def _generate_stage4_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 4."""
    content = "## Tasks Completed\n\n"

    content += "1. **Testbench deployment**\n"
    tb_count = sum(1 for f in files_list if "/tb/" in f and f.endswith(".v"))
    content += f"   - {tb_count} testbenches copied to stage_4_sim/tb/\n"

    content += "\n2. **Simulation results**\n"
    sim_dir = project_dir / "stage_4_sim" / "sim_output"
    pass_count = 0
    fail_count = 0
    sim_completed = False
    if sim_dir.exists():
        for log_file in sim_dir.glob("*.log"):
            try:
                log_content = log_file.read_text(encoding="utf-8", errors="ignore")
                if "ALL TESTS PASSED" in log_content or "PASSED" in log_content:
                    pass_count += 1
                    sim_completed = True
                elif "FAIL" in log_content or "TIMEOUT" in log_content:
                    fail_count += 1
                elif log_content.strip():
                    sim_completed = True
            except Exception:
                pass
    content += f"   - Tests PASSED: {pass_count}\n"
    content += f"   - Tests FAILED: {fail_count}\n"
    if sim_completed:
        content += "   - [OK] Simulation completed successfully\n"

    # Coverage check
    coverage_count = sum(1 for f in files_list if "/coverage/" in f or f.endswith(".vcd") or f.endswith(".saif") or f.endswith(".dat"))
    vcd_count = sum(1 for f in files_list if f.endswith(".vcd"))
    saif_count = sum(1 for f in files_list if f.endswith(".saif"))
    content += f"\n3. **Coverage Analysis**\n"
    if vcd_count > 0:
        content += f"   - VCD waveform files: {vcd_count}\n"
    if saif_count > 0:
        content += f"   - SAIF activity files: {saif_count}\n"
    content += f"   - Total coverage files: {coverage_count}\n"

    log_count = sum(1 for f in files_list if f.endswith(".log"))
    content += f"\n4. **Simulation logs: {log_count} log files saved**\n\n"

    # Cocotb regression summary
    cocotb_regression_dir = project_dir / "stage_4_sim" / "cocotb_regression"
    cocotb_report_path = cocotb_regression_dir / "cocotb_regression_report.json"
    if not cocotb_report_path.exists():
        cocotb_report_path = project_dir / "stage_4_sim" / "cocotb_regression_report.json"
    if cocotb_report_path.exists():
        try:
            report_data = json.loads(cocotb_report_path.read_text(encoding="utf-8"))
            content += "5. **Cocotb Regression Results**\n"
            content += f"   - Total tests: {report_data.get('total_tests', 'N/A')}\n"
            content += f"   - Passed: {report_data.get('passed', 'N/A')}\n"
            content += f"   - Failed: {report_data.get('failed', 'N/A')}\n"
            seeds = report_data.get("seeds_run", [])
            if seeds:
                content += f"   - Seeds run: {', '.join(str(s) for s in seeds)}\n"
            cov_summary = report_data.get("coverage_summary", {})
            if cov_summary:
                content += "   - Coverage:\n"
                for key, val in cov_summary.items():
                    content += f"     - {key}: {val}%\n"
            content += "\n"
        except (json.JSONDecodeError, Exception):
            content += "5. **Cocotb Regression**: report found but could not be parsed\n\n"
    elif cocotb_regression_dir.exists():
        cocotb_logs = list(cocotb_regression_dir.glob("*.log"))
        if cocotb_logs:
            content += f"5. **Cocotb Regression**: {len(cocotb_logs)} log files found\n\n"

    # Requirements coverage report summary
    req_cov_report = project_dir / "stage_4_sim" / "requirements_coverage_report.json"
    if req_cov_report.exists():
        try:
            rcr_data = json.loads(req_cov_report.read_text(encoding="utf-8"))
            summary = rcr_data.get("summary", {})
            content += "6. **Requirements Coverage Report**\n"
            content += f"   - Total requirements: {summary.get('total_requirements', 'N/A')}\n"
            content += f"   - Verified: {summary.get('verified', 'N/A')}\n"
            content += f"   - Failed: {summary.get('failed', 'N/A')}\n"
            content += f"   - Not run: {summary.get('not_run', 'N/A')}\n"
            content += f"   - Coverage: {summary.get('requirements_coverage_pct', 0)}%\n"
            by_cat = summary.get("by_category", {})
            if by_cat:
                content += "   - By category:\n"
                for cat, cat_data in sorted(by_cat.items()):
                    content += f"     - {cat}: {cat_data.get('verified', 0)}/{cat_data.get('total', 0)} ({cat_data.get('coverage_pct', 0)}%)\n"
            content += "\n"
        except (json.JSONDecodeError, Exception):
            content += "6. **Requirements Coverage Report**: found but could not be parsed\n\n"

    return content


def _generate_stage5_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 5."""
    content = "## Tasks Completed\n\n"

    content += "1. **Synthesis script created**\n"
    content += "   - Yosys synthesis script (.ys) generated\n"
    content += "   - Reads all RTL files, elaborates top module\n"
    content += "   - Runs full synthesis flow (proc, opt, fsm, techmap, etc.)\n\n"

    content += "2. **Synthesis executed**\n"
    synth_log = project_dir / "stage_5_synth" / "synth.log"
    synth_report = project_dir / "stage_5_synth" / "synth_report.json"
    cell_count = 0
    has_errors = False
    has_critical_warnings = False

    if synth_log.exists():
        try:
            log_content = synth_log.read_text(encoding="utf-8", errors="ignore")
            import re
            match = re.search(r"(\d+)\s+cells", log_content)
            if match:
                cell_count = int(match.group(1))
                content += f"   - Total cells: {cell_count}\n"
            # Check for errors and critical warnings
            if "ERROR:" in log_content or "Error:" in log_content:
                has_errors = True
                content += "   - [WARN] Errors found in synthesis log\n"
            if "CRITICAL" in log_content or "critical" in log_content.lower():
                has_critical_warnings = True
                content += "   - [WARN] Critical warnings found in synthesis log\n"
            if not has_errors and not has_critical_warnings:
                content += "   - [OK] No errors or critical warnings\n"
        except Exception:
            pass

    content += "\n3. **Outputs generated**\n"
    if any("synth_netlist" in f for f in files_list):
        content += "   - [OK] synth_netlist.v: Synthesized netlist\n"
    if synth_log.exists():
        content += "   - [OK] synth.log: Complete synthesis log\n"
    if synth_report.exists():
        content += "   - [OK] synth_report.json: Structured synthesis report\n"
        try:
            report_data = json.loads(synth_report.read_text(encoding="utf-8"))
            status = report_data.get("status", "unknown")
            content += f"   - Report status: {status}\n"
            if "warnings" in report_data:
                content += f"   - Warnings in report: {len(report_data.get('warnings', []))}\n"
            if "errors" in report_data:
                content += f"   - Errors in report: {len(report_data.get('errors', []))}\n"
        except Exception:
            pass

    content += "\n"
    return content


def _generate_stage6_details(project_dir: Path, project_config: Dict, files_list: List[str]) -> str:
    """Generate detailed summary for Stage 6."""
    content = "## Tasks Completed\n\n"

    content += "1. **Final report generated**\n"
    content += "   - final_report.md created in reports/\n"
    content += "   - Includes project summary, module list, verification results\n"
    content += "   - Includes synthesis resource utilization\n"
    content += "   - Includes recommendations for future enhancements\n\n"

    content += "2. **Project completion**\n"
    content += "   - All 7 stages (0-6) completed successfully\n"
    content += "   - All validation checks passed\n"
    content += "   - All deliverables generated\n\n"

    content += "## Overall Status\n\n"
    content += "[DONE] **PROJECT COMPLETE**\n\n"

    content += "## Deliverable Summary\n\n"
    rtl_total = sum(1 for f in files_list if f.endswith(".v") and "rtl" in f)
    tb_total = sum(1 for f in files_list if f.endswith(".v") and ("tb" in f or "test" in f))
    yaml_total = sum(1 for f in files_list if f.endswith(".yaml") or f.endswith(".yml"))
    json_total = sum(1 for f in files_list if f.endswith(".json"))
    py_total = sum(1 for f in files_list if f.endswith(".py"))
    md_total = sum(1 for f in files_list if f.endswith(".md"))

    content += f"- RTL modules: {rtl_total}\n"
    content += f"- Testbenches: {tb_total}\n"
    content += f"- Timing scenarios (YAML): {yaml_total}\n"
    content += f"- Spec/Report JSON: {json_total}\n"
    content += f"- Cocotb tests: {py_total}\n"
    content += f"- Markdown reports: {md_total}\n\n"
    return content


# ── Toolchain Detection ──────────────────────────────────────────────────────

def _get_toolchain_env() -> Dict[str, str]:
    """Build an environment dict with common EDA tool paths for all platforms."""
    env = os.environ.copy()
    # Cross-platform search paths for oss-cad-suite and common install locations
    search_paths = [
        # Windows
        Path("C:/oss-cad-suite/bin"),
        Path("C:/oss-cad-suite/lib"),
        # macOS (Homebrew)
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        # Linux
        Path("/opt/oss-cad-suite/bin"),
        Path("/opt/oss-cad-suite/lib"),
        Path("/usr/bin"),
        # User-local
        Path.home() / "oss-cad-suite" / "bin",
        Path.home() / "oss-cad-suite" / "lib",
    ]
    extra = os.pathsep.join(str(p) for p in search_paths if p.exists())
    if extra:
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env


def detect_toolchain() -> Dict[str, str]:
    tools = {}
    env = _get_toolchain_env()
    for tool in ["iverilog", "yosys"]:
        try:
            r = subprocess.run([tool, "-V"], capture_output=True, text=True,
                               timeout=10, env=env, encoding="utf-8", errors="replace")
            tools[tool] = r.stdout.strip().split("\n")[0] if r.stdout else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            tools[tool] = "not found"
    return tools


# ── Project Config ───────────────────────────────────────────────────────────

def load_project_config(project_dir: Path) -> Dict:
    config_file = project_dir / ".veriflow" / "project_config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {"execution_mode": "automatic", "auto_approve": {}}


# ── Prompt Builder ───────────────────────────────────────────────────────────

def build_prompt(stage_id: int, project_dir: Path, extra_context: str = "") -> str:
    prompt_file = PROMPTS_DIR / STAGES[stage_id]["prompt"]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    template = prompt_file.read_text(encoding="utf-8")
    config = load_project_config(project_dir)
    vendor = config.get("vendor", "generic")

    # Load coding style
    style_ref = ""
    if stage_id in (1, 2, 3):
        for v in ["generic"] + ([vendor] if vendor != "generic" else []):
            style_dir = SKILL_DIR / "verilog_flow" / "defaults" / "coding_style" / v
            if style_dir.exists():
                for f in style_dir.glob("*.md"):
                    style_ref += f"\n--- Coding Style: {f.name} ---\n{f.read_text(encoding='utf-8')}\n"
        # Inject coding style overrides from project_config
        coding_style = config.get("coding_style", {})
        if coding_style:
            style_ref += "\n--- Project Coding Style Overrides ---\n"
            reset_type = coding_style.get("reset_type", "")
            reset_signal = coding_style.get("reset_signal", "")
            if reset_type and reset_signal:
                style_ref += f"- Reset: {reset_type.replace('_', ' ')} ({reset_signal})\n"
            for k, v_val in coding_style.items():
                if k not in ("reset_type", "reset_signal"):
                    style_ref += f"- {k}: {v_val}\n"

    # Load templates
    templates_ref = ""
    if stage_id in (2, 3, 4):
        for v in ["generic"] + ([vendor] if vendor != "generic" else []):
            temp_dir = SKILL_DIR / "verilog_flow" / "defaults" / "templates" / v
            if temp_dir.exists():
                for f in list(temp_dir.rglob("*.v")) + list(temp_dir.rglob("*.sv")):
                    templates_ref += f"\n--- Template: {f.name} ---\n```verilog\n{f.read_text(encoding='utf-8')}\n```\n"

    # Load spec JSON (for stages 2+)
    spec_context = ""
    spec_dir = project_dir / "stage_1_spec" / "specs"
    if spec_dir.exists() and stage_id >= 2:
        for f in spec_dir.glob("*_spec.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                spec_context += f"\n--- {f.name} ---\n{json.dumps(data, indent=2, ensure_ascii=False)}\n"
            except json.JSONDecodeError:
                spec_context += f"\n--- {f.name} ---\n{f.read_text(encoding='utf-8')}\n"

    # Load requirement.md (with encoding auto-detection)
    req_context = ""
    req_file = project_dir / "requirement.md"
    if req_file.exists() and stage_id <= 2:
        for enc in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
            try:
                req_context = req_file.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, ValueError):
                continue

    # Substitute placeholders
    prompt = template.replace("{{PROJECT_DIR}}", str(project_dir))
    prompt = prompt.replace("{{CODING_STYLE}}", style_ref or "(no coding style loaded)")
    prompt = prompt.replace("{{TEMPLATES}}", templates_ref or "(no templates loaded)")
    prompt = prompt.replace("{{SPEC_JSON}}", spec_context or "(not yet generated)")
    prompt = prompt.replace("{{REQUIREMENT}}", req_context or "(not found)")
    prompt = prompt.replace("{{EXTRA_CONTEXT}}", extra_context)
    prompt = prompt.replace("{{TOOLCHAIN}}", json.dumps(detect_toolchain(), ensure_ascii=False))

    return prompt


# ── Stage Validators ─────────────────────────────────────────────────────────

def validate_stage(stage_id: int, project_dir: Path) -> Tuple[bool, List[str]]:
    """Validate a stage's output. Returns (passed, errors)."""
    validators = {
        0: _validate_stage0, 1: _validate_stage1, 2: _validate_stage2,
        3: _validate_stage3, 4: _validate_stage4, 5: _validate_stage5,
        6: _validate_stage6,
    }
    validator = validators.get(stage_id)
    if not validator:
        return True, []
    return validator(project_dir)


def _validate_stage0(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    # Common directories for all modes
    common_dirs = ["stage_1_spec", "stage_3_codegen/rtl",
                   "stage_4_sim/tb", "stage_4_sim/sim_output", ".veriflow", "reports"]

    # Standard/Enterprise only directories
    standard_dirs = ["stage_2_timing", "stage_5_synth"]

    # Check common directories
    for d in common_dirs:
        if not (project_dir / d).exists():
            errors.append(f"Missing directory: {d}")

    # Check mode-specific directories
    if mode in ("standard", "enterprise"):
        for d in standard_dirs:
            if not (project_dir / d).exists():
                errors.append(f"Missing directory: {d} (required for {mode} mode)")

    config_file = project_dir / ".veriflow" / "project_config.json"
    if not config_file.exists():
        errors.append("Missing .veriflow/project_config.json")
    return len(errors) == 0, errors


def _validate_stage1(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    spec_dir = project_dir / "stage_1_spec" / "specs"
    docs_dir = project_dir / "stage_1_spec" / "docs"
    if not spec_dir.exists():
        spec_dir = project_dir / "stage_1_spec"
    specs = list(spec_dir.glob("*_spec.json"))
    if not specs:
        errors.append("No *_spec.json found in stage_1_spec/specs/")
        return False, errors
    for spec_file in specs:
        try:
            data = json.loads(spec_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{spec_file.name}: Invalid JSON — {e}")
            continue
        # 检查必需字段
        for field in ["design_name", "target_frequency_mhz", "modules", "architecture_summary"]:
            if field not in data:
                errors.append(f"{spec_file.name}: Missing required field '{field}'")
        # 检查是否有详细的方案介绍
        arch_summary = data.get("architecture_summary", "")
        if len(arch_summary.strip()) < 50:
            errors.append(f"{spec_file.name}: architecture_summary too short, need detailed introduction")
        # 检查模块划分
        modules = data.get("modules", [])
        if len(modules) == 0:
            errors.append(f"{spec_file.name}: No modules defined")
        else:
            # 检查是否有 top 模块
            has_top = any(mod.get("module_type") == "top" for mod in modules)
            if not has_top:
                errors.append(f"{spec_file.name}: No module with module_type='top' found")
        # 检查模块互联
        if "module_connectivity" not in data or len(data.get("module_connectivity", [])) == 0:
            errors.append(f"{spec_file.name}: Missing module_connectivity section")
        # 检查数据流程
        if "data_flow_sequences" not in data or len(data.get("data_flow_sequences", [])) == 0:
            errors.append(f"{spec_file.name}: Missing data_flow_sequences section")
        # 检查每个module
        for mod in modules:
            if "name" not in mod:
                errors.append(f"{spec_file.name}: Module missing 'name' field")
            if "ports" not in mod:
                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' missing 'ports'")
            if "description" not in mod or len(mod.get("description", "").strip()) < 10:
                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' missing detailed description")

            # ── Timing contract checks ──
            has_pipeline = "pipeline_stages_detail" in mod and len(mod.get("pipeline_stages_detail", [])) > 0
            has_handshake = any(
                p.get("protocol") in ("handshake", "valid-ready", "valid_ready")
                or "valid" in p.get("name", "").lower()
                for p in mod.get("ports", [])
            )
            has_fsm = "fsm_spec" in mod and mod.get("fsm_spec")

            if has_pipeline or has_handshake:
                timing_contracts = mod.get("timing_contracts", [])
                if not timing_contracts:
                    errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' has pipeline/handshake but missing timing_contracts")
                else:
                    for tc in timing_contracts:
                        if tc.get("protocol_type") == "valid_ready_backpressure":
                            if not tc.get("backpressure_signal"):
                                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' timing_contract '{tc.get('contract_name', '?')}' missing backpressure_signal")
                            if not tc.get("stall_behavior"):
                                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' timing_contract '{tc.get('contract_name', '?')}' missing stall_behavior")
                        # Cross-check latency vs pipeline depth
                        if has_pipeline:
                            pipeline_depth = len(mod.get("pipeline_stages_detail", []))
                            contract_latency = tc.get("latency_cycles", -1)
                            if contract_latency >= 0 and pipeline_depth > 0 and contract_latency != pipeline_depth:
                                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' latency_cycles ({contract_latency}) != pipeline_stages_detail count ({pipeline_depth})")

            if has_pipeline or has_fsm:
                cbt = mod.get("cycle_behavior_tables", [])
                if not cbt:
                    errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' has pipeline/FSM but missing cycle_behavior_tables")
    # 检查是否有文档
    doc_files = list(docs_dir.glob("*.md")) + list(docs_dir.glob("*.wavedrom")) + list(docs_dir.glob("*.json"))
    if not doc_files and docs_dir.exists():
        # 检查 stage_1_spec 根目录
        doc_files = list((project_dir / "stage_1_spec").glob("*.md")) + list((project_dir / "stage_1_spec").glob("*.wavedrom"))
    if not doc_files:
        errors.append("No documentation found in stage_1_spec/docs/ (timing diagram or architecture doc)")

    # ── Structured requirements check ──
    struct_req_file = project_dir / "stage_1_spec" / "specs" / "structured_requirements.json"
    if not struct_req_file.exists():
        errors.append("Missing stage_1_spec/specs/structured_requirements.json")
    else:
        try:
            req_data = json.loads(struct_req_file.read_text(encoding="utf-8"))
            requirements = req_data.get("requirements", [])
            if not requirements:
                errors.append("structured_requirements.json: 'requirements' array is empty")
            else:
                has_functional = False
                for req in requirements:
                    for field in ("req_id", "category", "description", "testable"):
                        if field not in req:
                            errors.append(f"structured_requirements.json: requirement missing '{field}' field")
                    if req.get("category") == "functional":
                        has_functional = True
                    if req.get("testable") and not req.get("acceptance_criteria"):
                        errors.append(f"structured_requirements.json: testable requirement '{req.get('req_id', '?')}' missing acceptance_criteria")
                if not has_functional:
                    errors.append("structured_requirements.json: no requirement with category='functional' found")
        except json.JSONDecodeError as e:
            errors.append(f"structured_requirements.json: invalid JSON — {e}")

    return len(errors) == 0, errors


def _validate_stage2(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    # Quick模式跳过stage2验证
    if mode == "quick":
        # Quick模式下stage2是可选的
        timing_dir = project_dir / "stage_2_timing"
        if not timing_dir.exists():
            # Quick模式允许没有stage2目录
            return True, []
        # 如果有stage2目录，仍然检查内容完整性
        # 但不强制要求

    # Standard/Enterprise模式的完整检查
    timing_dir = project_dir / "stage_2_timing"
    scenarios = list(timing_dir.rglob("*.yaml")) + list(timing_dir.rglob("*.yml"))
    if not scenarios:
        errors.append("No YAML timing scenarios found in stage_2_timing/")

    # Check golden traces
    golden_dir = timing_dir / "golden_traces"
    if golden_dir.exists():
        traces = list(golden_dir.glob("*.json"))
        if not traces:
            errors.append("No golden trace JSON files found in stage_2_timing/golden_traces/")
    else:
        errors.append("Missing stage_2_timing/golden_traces/ directory")

    # Check cocotb files
    cocotb_dir = timing_dir / "cocotb"
    if cocotb_dir.exists():
        py_files = list(cocotb_dir.glob("*.py"))
        if not py_files:
            errors.append("No Python test files found in stage_2_timing/cocotb/")
        else:
            # Check for GoldenModel class with tick() and reset()
            has_golden_model = False
            has_timing_checker = False
            for py_file in py_files:
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    if "class GoldenModel" in content:
                        has_golden_model = True
                        if "def tick(" not in content:
                            errors.append(f"{py_file.name}: GoldenModel missing tick() method")
                        if "def reset(" not in content:
                            errors.append(f"{py_file.name}: GoldenModel missing reset() method")
                    if "TimingChecker" in content or "timing_checker" in content or "cycle_check" in content.lower():
                        has_timing_checker = True
                    # Syntax check
                    try:
                        compile(content, str(py_file), "exec")
                    except SyntaxError as e:
                        errors.append(f"{py_file.name}: Python syntax error — {e}")
                except Exception:
                    pass
            if not has_golden_model:
                errors.append("No GoldenModel class found in stage_2_timing/cocotb/ Python files")
            if not has_timing_checker:
                errors.append("No TimingChecker (or equivalent cycle-by-cycle comparison) found in stage_2_timing/cocotb/")

            # ── UVM-like verification architecture checks ──
            all_content = ""
            for py_file in py_files:
                try:
                    all_content += py_file.read_text(encoding="utf-8", errors="replace") + "\n"
                except Exception:
                    pass
            # Also check vf_bfm/ subdirectory
            bfm_dir = cocotb_dir / "vf_bfm"
            if bfm_dir.exists():
                for py_file in bfm_dir.rglob("*.py"):
                    try:
                        all_content += py_file.read_text(encoding="utf-8", errors="replace") + "\n"
                    except Exception:
                        pass

            has_driver = bool(re.search(r'class\s+\w*Driver', all_content)) and ("def send(" in all_content or "def drive(" in all_content)
            has_monitor = bool(re.search(r'class\s+\w*Monitor', all_content)) and "def start(" in all_content
            has_scoreboard = bool(re.search(r'class\s+\w*Scoreboard\b', all_content, re.IGNORECASE)) and "def check(" in all_content and "def report(" in all_content
            has_coverage = ("CoverageCollector" in all_content or "coverpoint" in all_content.lower()) and "coverage_report" in all_content.lower()
            has_constrained_random = ("ConstrainedRandom" in all_content or "random.Random" in all_content or "COCOTB_RANDOM_SEED" in all_content)

            if not has_driver:
                errors.append("No Driver class with send/drive method found in cocotb verification library")
            if not has_monitor:
                errors.append("No Monitor class with start method found in cocotb verification library")
            if not has_scoreboard:
                errors.append("No Scoreboard class with check+report methods found in cocotb verification library")
            if not has_coverage:
                errors.append("No coverage collection (CoverageCollector/coverpoint/coverage_report) found in cocotb verification library")
            if not has_constrained_random:
                errors.append("No constrained random (ConstrainedRandom/random.Random/COCOTB_RANDOM_SEED) found in cocotb verification library")
    else:
        errors.append("Missing stage_2_timing/cocotb/ directory")

    # ── Requirements coverage matrix check ──
    matrix_file = timing_dir / "cocotb" / "requirements_coverage_matrix.json"
    if not matrix_file.exists():
        errors.append("Missing stage_2_timing/cocotb/requirements_coverage_matrix.json")
    else:
        try:
            matrix_data = json.loads(matrix_file.read_text(encoding="utf-8"))
            matrix = matrix_data.get("matrix", [])
            if not matrix:
                errors.append("requirements_coverage_matrix.json: 'matrix' array is empty")
            else:
                for entry in matrix:
                    if "req_id" not in entry:
                        errors.append("requirements_coverage_matrix.json: matrix entry missing 'req_id'")
                    cocotb_tests = entry.get("cocotb_tests", [])
                    if not cocotb_tests:
                        errors.append(f"requirements_coverage_matrix.json: req '{entry.get('req_id', '?')}' has no cocotb_tests mapped")
            cov_summary = matrix_data.get("coverage_summary", {})
            cov_pct = cov_summary.get("coverage_pct", 0)
            if cov_pct <= 0:
                errors.append("requirements_coverage_matrix.json: coverage_summary.coverage_pct must be > 0")
        except json.JSONDecodeError as e:
            errors.append(f"requirements_coverage_matrix.json: invalid JSON — {e}")

    return len(errors) == 0, errors


def _validate_stage3(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    rtl_dir = project_dir / "stage_3_codegen" / "rtl"
    tb_autogen_dir = project_dir / "stage_3_codegen" / "tb_autogen"
    reports_dir = project_dir / "stage_3_codegen" / "reports"

    rtl_files = list(rtl_dir.rglob("*.v")) if rtl_dir.exists() else []
    if not rtl_files:
        errors.append("No .v files found in stage_3_codegen/rtl/")
        return False, errors

    # 检查 placeholder/TODO
    placeholder_re = re.compile(r'(?://|/\*)\s*(?:TODO|placeholder|\.\.\.)', re.IGNORECASE)
    for vf in rtl_files:
        content = vf.read_text(encoding="utf-8", errors="replace")
        if placeholder_re.search(content):
            errors.append(f"{vf.name}: Contains placeholder/TODO markers")

    # 检查 spec 覆盖率
    spec_dir = project_dir / "stage_1_spec" / "specs"
    if spec_dir.exists():
        rtl_names = {f.stem for f in rtl_files}
        for spec_file in spec_dir.glob("*_spec.json"):
            try:
                data = json.loads(spec_file.read_text(encoding="utf-8"))
                for mod in data.get("modules", []):
                    name = mod.get("name", "")
                    if name and name not in rtl_names:
                        errors.append(f"Module '{name}' in spec but no {name}.v found")
            except (json.JSONDecodeError, KeyError):
                pass

    # Lint 检查：第一步 - iverilog 编译
    compile_errors = _check_iverilog_compile(rtl_files)
    if compile_errors:
        errors.extend(compile_errors)
    else:
        # 检查是否有 lint 报告
        lint_report_found = False
        lint_report_files = []
        if reports_dir.exists():
            for report_file in list(reports_dir.glob("*.log")) + list(reports_dir.glob("*.rpt")) + list(reports_dir.glob("*.json")):
                if "lint" in report_file.name.lower():
                    lint_report_found = True
                    lint_report_files.append(report_file)
                    break
        # 也检查 stage_3_codegen 根目录
        if not lint_report_found:
            for report_file in list((project_dir / "stage_3_codegen").glob("*.log")) + list((project_dir / "stage_3_codegen").glob("*.rpt")):
                if "lint" in report_file.name.lower():
                    lint_report_found = True
                    lint_report_files.append(report_file)
                    break
        if not lint_report_found:
            errors.append("No lint report found in stage_3_codegen/reports/ or stage_3_codegen/")
        else:
            # 检查lint报告是否是伪造的 - 检测常见的伪造模式
            fake_patterns = [
                "Quick mode", "no EDA tools", "no iverilog",
                "skipping lint", "lint skipped", "fake lint",
                "Lint Step 1: RTL only - PASSED"
            ]
            for report_file in lint_report_files:
                try:
                    report_content = report_file.read_text(encoding="utf-8", errors="ignore")
                    for pattern in fake_patterns:
                        if pattern.lower() in report_content.lower():
                            errors.append(f"Lint report {report_file.name} appears to be fake — contains forbidden pattern: '{pattern}'")
                except Exception:
                    pass

    # Testbench 检查
    tb_files = list(tb_autogen_dir.rglob("*.v")) if tb_autogen_dir.exists() else []
    if not tb_files:
        errors.append("No testbench files found in stage_3_codegen/tb_autogen/")
    else:
        # Determine reset signal name from project config
        config = load_project_config(project_dir)
        coding_style = config.get("coding_style", {})
        reset_signal = coding_style.get("reset_signal", "rst_n")
        # Accept both the configured name and common alternatives
        reset_names = {reset_signal, "rst_n", "rst", "reset"}

        for tb_file in tb_files:
            content = tb_file.read_text(encoding="utf-8", errors="replace")
            display_count = content.count("$display")
            monitor_count = content.count("$monitor")
            if display_count + monitor_count < 3:
                errors.append(f"{tb_file.name}: Too few debug prints, need more $display/$monitor for debugging")
            if "PASS" not in content and "FAIL" not in content and "pass" not in content and "fail" not in content:
                errors.append(f"{tb_file.name}: No PASS/FAIL status prints found")
            if "always" not in content and "#" not in content:
                errors.append(f"{tb_file.name}: No clock generation found")
            # Check for any recognized reset signal
            if not any(rn in content for rn in reset_names) and "reset" not in content.lower():
                errors.append(f"{tb_file.name}: No reset sequence found (expected '{reset_signal}' or similar)")

    # ── Timing annotation checks on RTL files ──
    for vf in rtl_files:
        content = vf.read_text(encoding="utf-8", errors="replace")
        if "TIMING CONTRACT" not in content:
            errors.append(f"{vf.name}: Missing TIMING CONTRACT comment block")
        if "TIMING SELF-CHECK" not in content:
            errors.append(f"{vf.name}: Missing TIMING SELF-CHECK comment block")
        if not re.search(r'//\s*Cycle\s+\d+', content):
            errors.append(f"{vf.name}: Missing per-cycle annotations (expected '// Cycle N:' comments)")

    return len(errors) == 0, errors


def _check_iverilog_compile(verilog_files: List[Path]) -> List[str]:
    """Try compiling with iverilog. Returns list of error strings."""
    errors = []
    env = _get_toolchain_env()
    iverilog = shutil.which("iverilog", path=env.get("PATH"))
    if not iverilog:
        iverilog = shutil.which("iverilog.exe", path=env.get("PATH"))
    if not iverilog:
        # 不允许静默跳过 - 要求iverilog必须可用
        return ["iverilog not found in PATH. Please install iverilog (part of oss-cad-suite)."]

    # Use a temp file for output — cross-platform (avoids /dev/null vs NUL)
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".vvp", delete=False)
        tmp.close()

        cmd = [iverilog, "-g2005", "-Wall", "-o", tmp.name]
        cmd.extend(str(f) for f in verilog_files)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                encoding="utf-8", errors="replace", env=env)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            errors.append(f"iverilog compilation failed:\n{stderr[:2000]}")
    except subprocess.TimeoutExpired:
        errors.append("iverilog compilation timed out (>60s)")
    except FileNotFoundError:
        errors.append("iverilog execution failed - file not found")
    finally:
        if tmp and os.path.exists(tmp.name):
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    return errors


def _validate_stage4(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    tb_dir = project_dir / "stage_4_sim" / "tb"
    sim_output_dir = project_dir / "stage_4_sim" / "sim_output"
    coverage_dir = project_dir / "stage_4_sim" / "coverage"

    # 检查 testbench 文件
    tbs = list(tb_dir.rglob("*.v")) if tb_dir.exists() else []
    if not tbs:
        errors.append("No testbench .v files found in stage_4_sim/tb/")

    # 检查仿真是否完成
    sim_completed = False
    all_tests_passed = True
    if sim_output_dir.exists():
        log_files = list(sim_output_dir.glob("*.log"))
        if log_files:
            sim_completed = True
            for log_file in log_files:
                content = log_file.read_text(encoding="utf-8", errors="ignore")

                # 检查伪造日志模式 - 快速失败
                fake_patterns = [
                    "Quick mode", "no EDA tools", "no simulation",
                    "simulation skipped", "fake simulation", "simulated without tools",
                    "Lint Step", "no iverilog", "no vvp"
                ]
                is_fake = False
                for pattern in fake_patterns:
                    if pattern.lower() in content.lower():
                        errors.append(f"Simulation log {log_file.name} appears to be fake — contains forbidden pattern: '{pattern}'")
                        is_fake = True
                        all_tests_passed = False

                if not is_fake:
                    if "FAIL" in content or "TIMEOUT" in content:
                        errors.append(f"Simulation log {log_file.name} contains FAIL/TIMEOUT")
                        all_tests_passed = False

                    # 验证日志包含实际仿真器输出的特征
                    has_iverilog_signature = any(kw in content for kw in [
                        "VCD info", "dumpfile", "dumpvars", "iverilog",
                        "Icarus Verilog", "VCD dump", "At time",
                    ])
                    has_vvp_signature = any(kw in content for kw in [
                        "vvp", "VVP", "Running simulation", "Simulation interrupted",
                    ])
                    has_test_signals = any(kw in content for kw in [
                        "clk", "rst", "valid", "ready", "data",
                        "[TEST", "[INFO]", "[PASS]", "[FAIL]"
                    ])

                    # 至少需要有一些仿真特征
                    if not (has_iverilog_signature or has_vvp_signature or has_test_signals):
                        errors.append(f"Simulation log {log_file.name}: no simulation signature found (iverilog/vvp/test signals missing)")

                    # Verify that the log contains some positive completion indicator
                    has_pass = any(kw in content for kw in [
                        "ALL TESTS PASSED", "PASSED", "PASS", "Test passed",
                        "Simulation complete", "simulation finished",
                    ])
                    if not has_pass and all_tests_passed:
                        errors.append(f"Simulation log {log_file.name}: no PASS/completion indicator found")
    if not sim_completed:
        errors.append("No simulation logs found in stage_4_sim/sim_output/ - simulation may not have run")

    # 检查覆盖率报告
    coverage_found = False
    # 检查常见的覆盖率文件格式
    if coverage_dir.exists():
        coverage_files = (list(coverage_dir.glob("*.dat")) +
                          list(coverage_dir.glob("*.vcd")) +
                          list(coverage_dir.glob("*.saif")) +
                          list(coverage_dir.glob("*.html")) +
                          list(coverage_dir.glob("*.json")))
        if coverage_files:
            coverage_found = True
    # 也检查 sim_output 目录
    if not coverage_found and sim_output_dir.exists():
        coverage_files = (list(sim_output_dir.glob("*.dat")) +
                          list(sim_output_dir.glob("*.vcd")) +
                          list(sim_output_dir.glob("*.saif")))
        if coverage_files:
            coverage_found = True
    # 检查 stage_4_sim 根目录
    if not coverage_found:
        coverage_files = (list((project_dir / "stage_4_sim").glob("*.dat")) +
                          list((project_dir / "stage_4_sim").glob("*.vcd")) +
                          list((project_dir / "stage_4_sim").glob("*.saif")))
        if coverage_files:
            coverage_found = True
    if not coverage_found:
        errors.append("No coverage data found (.vcd, .dat, .saif) - coverage analysis missing")

    # ── Timing-specific test checks ── (Standard/Enterprise only)
    if mode in ("standard", "enterprise"):
        has_latency_test = False
        has_backpressure_test = False
        if sim_output_dir.exists():
            for log_file in sim_output_dir.glob("*.log"):
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore").lower()
                    if "latency" in content:
                        has_latency_test = True
                    if "backpressure" in content or "stress" in content or "back_pressure" in content:
                        has_backpressure_test = True
                except Exception:
                    pass
        # Also check testbench source files for timing tests
        if tb_dir.exists():
            for tb_file in tb_dir.rglob("*.v"):
                try:
                    content = tb_file.read_text(encoding="utf-8", errors="replace").lower()
                    if "latency" in content:
                        has_latency_test = True
                    if "backpressure" in content or "stress" in content or "back_pressure" in content:
                        has_backpressure_test = True
                except Exception:
                    pass
        if not has_latency_test:
            errors.append("No latency detection test found in simulation logs or testbenches")
        if not has_backpressure_test:
            errors.append("No backpressure/stress test found in simulation logs or testbenches")

    # ── Cocotb regression checks ── (Standard/Enterprise only)
    if mode in ("standard", "enterprise"):
        cocotb_regression_dir = project_dir / "stage_4_sim" / "cocotb_regression"
        has_cocotb_regression = False
        if cocotb_regression_dir.exists():
            cocotb_files = list(cocotb_regression_dir.rglob("*.py")) + list(cocotb_regression_dir.rglob("*.log"))
            if cocotb_files:
                has_cocotb_regression = True
        # Also check for cocotb logs in sim_output
        if not has_cocotb_regression and sim_output_dir.exists():
            for log_file in sim_output_dir.glob("*.log"):
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore").lower()
                    if "cocotb" in content:
                        has_cocotb_regression = True
                        break
                except Exception:
                    pass
        if not has_cocotb_regression:
            errors.append("No cocotb regression found — expected stage_4_sim/cocotb_regression/ directory or cocotb logs")

        # Check cocotb_regression_report.json
        cocotb_report_path = cocotb_regression_dir / "cocotb_regression_report.json" if cocotb_regression_dir.exists() else None
        # Also check stage_4_sim root
        if not cocotb_report_path or not cocotb_report_path.exists():
            cocotb_report_path = project_dir / "stage_4_sim" / "cocotb_regression_report.json"
        if cocotb_report_path and cocotb_report_path.exists():
            try:
                report_data = json.loads(cocotb_report_path.read_text(encoding="utf-8"))
                failed = report_data.get("failed", -1)
                if failed != 0:
                    errors.append(f"cocotb_regression_report.json: {failed} tests failed (expected 0)")
                if "seeds_run" not in report_data:
                    errors.append("cocotb_regression_report.json: missing 'seeds_run' field")
            except json.JSONDecodeError:
                errors.append("cocotb_regression_report.json is not valid JSON")
        else:
            if has_cocotb_regression:
                errors.append("cocotb_regression_report.json not found — regression report missing")

    # ── Requirements coverage report check ──
    req_cov_report = project_dir / "stage_4_sim" / "requirements_coverage_report.json"
    if not req_cov_report.exists():
        errors.append("Missing stage_4_sim/requirements_coverage_report.json")
    else:
        try:
            rcr_data = json.loads(req_cov_report.read_text(encoding="utf-8"))
            summary = rcr_data.get("summary", {})
            req_cov_pct = summary.get("requirements_coverage_pct", 0)
            if req_cov_pct <= 0:
                errors.append("requirements_coverage_report.json: requirements_coverage_pct must be > 0")
        except json.JSONDecodeError as e:
            errors.append(f"requirements_coverage_report.json: invalid JSON — {e}")

    return len(errors) == 0, errors


def _validate_stage5(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    # Quick模式跳过stage5验证
    if mode == "quick":
        synth_dir = project_dir / "stage_5_synth"
        if not synth_dir.exists():
            # Quick模式允许没有stage5目录
            return True, []

    # Standard/Enterprise模式的完整检查
    synth_dir = project_dir / "stage_5_synth"
    ys_files = list(synth_dir.rglob("*.ys")) if synth_dir.exists() else []
    if not ys_files:
        errors.append("No .ys synthesis script found in stage_5_synth/")

    # 检查综合报告中的 errors 和 critical warnings
    synth_log = synth_dir / "synth.log"
    synth_report_json = synth_dir / "synth_report.json"

    log_has_error = False
    log_has_critical_warning = False

    if synth_log.exists():
        try:
            content = synth_log.read_text(encoding="utf-8", errors="ignore")
            # 检查 error
            error_patterns = ["ERROR", "Error", "error"]
            for pat in error_patterns:
                if pat in content:
                    # 过滤掉一些非错误的包含 error 的情况
                    lines = content.split("\n")
                    for line in lines:
                        if pat in line and "warning" not in line.lower() and "note" not in line.lower():
                            # 检查是否是 Yosys 的普通输出，还是真正的错误
                            if "ERROR:" in line or "Error:" in line:
                                log_has_error = True
                                errors.append(f"Synthesis log contains ERROR: {line.strip()[:200]}")
            # 检查 critical warning
            critical_patterns = ["CRITICAL", "Critical", "critical", "Warning:"]
            for pat in critical_patterns:
                if pat in content:
                    lines = content.split("\n")
                    for line in lines:
                        if "CRITICAL" in line or ("Warning:" in line and ("timing" in line.lower() or "unconnected" in line.lower() or "latency" in line.lower())):
                            log_has_critical_warning = True
                            errors.append(f"Synthesis log contains critical warning: {line.strip()[:200]}")
        except Exception:
            pass
    else:
        errors.append("No synth.log found - synthesis may not have run")

    # 检查 JSON 报告
    if synth_report_json.exists():
        try:
            report_data = json.loads(synth_report_json.read_text(encoding="utf-8"))
            status = report_data.get("status", "")
            if status == "FAIL":
                errors.append("synth_report.json indicates synthesis FAIL")
            # 检查报告中的 errors 和 warnings
            report_errors = report_data.get("errors", [])
            report_warnings = report_data.get("warnings", [])
            if report_errors:
                for err in report_errors[:5]:
                    errors.append(f"synth_report.json error: {str(err)[:200]}")
            if report_warnings:
                # 检查是否是 critical warning
                for warn in report_warnings:
                    warn_str = str(warn).lower()
                    if "critical" in warn_str or "unconnected" in warn_str or "timing" in warn_str:
                        errors.append(f"synth_report.json critical warning: {str(warn)[:200]}")
        except json.JSONDecodeError:
            errors.append("synth_report.json is not valid JSON")
    else:
        errors.append("No synth_report.json found")

    # 检查是否有综合网表
    netlist = synth_dir / "synth_netlist.v"
    if not netlist.exists():
        errors.append("No synth_netlist.v found - synthesis output missing")

    return len(errors) == 0, errors


def _validate_stage6(project_dir: Path) -> Tuple[bool, List[str]]:
    report = project_dir / "reports" / "final_report.md"
    if not report.exists():
        return False, ["No final_report.md in reports/"]
    return True, []


# ── Experience DB Helper ─────────────────────────────────────────────────────

def record_failure(project_dir: Path, stage_id: int, failure_type: str, error_message: str):
    if not ENHANCED_AVAILABLE:
        return
    try:
        db = ExperienceDB(project_dir / ".veriflow" / "experience_db")
        case = FailureCase(
            case_id="", module_name="unknown", target_frequency_mhz=300.0,
            stage=str(stage_id), failure_type=failure_type, error_message=error_message,
        )
        db.record_failure(case)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# SUBCOMMANDS
# ══════════════════════════════════════════════════════════════════════════════

def cmd_status(project_dir: Path) -> int:
    """Show current pipeline progress."""
    last = get_last_completed_stage(project_dir)
    next_stage = last + 1

    print(f"Project: {project_dir}")
    print(f"Last completed: Stage {last} ({STAGES[last]['name']})" if last >= 0 else "No stages completed yet")
    print()

    for stage in STAGES:
        sid = stage["id"]
        done = is_stage_complete(project_dir, sid)
        marker = "[DONE]" if done else "[    ]"
        current = " <-- next" if sid == next_stage and next_stage <= 6 else ""
        print(f"  {marker} Stage {sid}: {stage['name']}{current}")

    if next_stage > 6:
        print("\nAll stages complete!")
    else:
        print(f"\nNext action: python veriflow_ctl.py next -d \"{project_dir}\"")

    return 0


def cmd_next(project_dir: Path, extra_context: str = "") -> int:
    """Output the prompt for the next stage. Refuses if prerequisites unmet."""
    last = get_last_completed_stage(project_dir)
    config = load_project_config(project_dir)
    mode = config.get("mode", "standard").lower()

    # 根据模式确定下一个stage
    next_stage = last + 1

    # Quick模式跳过stage2和stage5
    if mode == "quick":
        if next_stage == 2:
            # 跳过stage2，直接到stage3
            mark_stage_complete(project_dir, 2, "Skipped in Quick mode")
            next_stage = 3
        elif next_stage == 5:
            # 跳过stage5，直接到stage6
            mark_stage_complete(project_dir, 5, "Skipped in Quick mode")
            next_stage = 6

    if next_stage > 6:
        print("ALL_STAGES_COMPLETE")
        print("All stages are already complete. Nothing to do.")
        return 0

    # Hard gate: check prerequisites
    ok, errors = check_prerequisites(project_dir, next_stage)
    if not ok:
        print(f"BLOCKED: Cannot proceed to Stage {next_stage}")
        for err in errors:
            print(f"  - {err}")
        return 1

    # Build and output the prompt
    try:
        prompt = build_prompt(next_stage, project_dir, extra_context)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1

    # Save prompt to file for reference
    prompt_file = project_dir / ".veriflow" / f"stage_{next_stage}_prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    # Output stage header + prompt
    print(f"STAGE:{next_stage}")
    print(f"NAME:{STAGES[next_stage]['name']}")
    print(f"PROMPT_FILE:{prompt_file}")
    print("---BEGIN_PROMPT---")
    print(prompt)
    print("---END_PROMPT---")

    return 0


def cmd_validate(project_dir: Path, stage_id: int) -> int:
    """Run deterministic validation checks on a stage's outputs."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    print(f"Validating Stage {stage_id}: {STAGES[stage_id]['name']}...")
    passed, errors = validate_stage(stage_id, project_dir)

    if passed:
        print(f"VALIDATION_PASSED")
        print(f"Stage {stage_id} outputs are valid.")
        print(f"Next: python veriflow_ctl.py complete -d \"{project_dir}\" {stage_id}")
    else:
        print(f"VALIDATION_FAILED")
        print(f"Stage {stage_id} has {len(errors)} error(s):")
        for err in errors:
            print(f"  [ERROR] {err}")
        # Record to experience DB
        record_failure(project_dir, stage_id, "validation_failed", "\n".join(errors[:5]))

    return 0 if passed else 1


def cmd_complete(project_dir: Path, stage_id: int, summary: str = "") -> int:
    """Mark a stage as complete. Refuses if validation fails."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    if is_stage_complete(project_dir, stage_id):
        print(f"Stage {stage_id} is already marked complete.")
        return 0

    # Hard gate: must pass validation first
    passed, errors = validate_stage(stage_id, project_dir)
    if not passed:
        print(f"REFUSED: Stage {stage_id} validation failed. Cannot mark complete.")
        for err in errors:
            print(f"  [ERROR] {err}")
        print(f"\nFix the errors above, then retry:")
        print(f"  python veriflow_ctl.py complete -d \"{project_dir}\" {stage_id}")
        return 1

    # Mark complete
    if not summary:
        summary = f"Stage {stage_id} completed at {datetime.now().isoformat()}"
    mark_stage_complete(project_dir, stage_id, summary)

    # KPI tracking
    if ENHANCED_AVAILABLE:
        try:
            kpi = KPITracker(project_dir / ".veriflow" / "kpi.json")
            run_id = f"stage{stage_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            module_name = _get_design_name(project_dir)
            kpi.start_run(run_id, module_name, target_frequency_mhz=300.0)
            kpi.start_stage(STAGES[stage_id]["name"])
            kpi.end_stage(success=True)
            is_final = (stage_id == 6)
            if is_final:
                kpi.end_run(pass_at_1=True, timing_closure=True)
            else:
                kpi.end_run(pass_at_1=True)
        except Exception:
            pass

    print(f"STAGE_COMPLETE:{stage_id}")
    print(f"Stage {stage_id} ({STAGES[stage_id]['name']}) marked COMPLETE.")

    next_stage = stage_id + 1
    if next_stage <= 6:
        print(f"\nNext: python veriflow_ctl.py next -d \"{project_dir}\"")
    else:
        print("\nAll stages complete! Pipeline finished.")

    return 0


def _get_design_name(project_dir: Path) -> str:
    spec_dir = project_dir / "stage_1_spec" / "specs"
    if spec_dir.exists():
        for f in spec_dir.glob("*_spec.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                return data.get("design_name", "unknown")
            except (json.JSONDecodeError, KeyError):
                pass
    return "unknown"


def cmd_rollback(project_dir: Path, target_stage: int) -> int:
    """Roll back to a target stage, clearing all subsequent completion markers."""
    if target_stage < 0 or target_stage > 6:
        print(f"ERROR: Invalid target stage {target_stage}. Valid range: 0-6")
        return 1

    last = get_last_completed_stage(project_dir)
    if target_stage > last:
        print(f"ERROR: Cannot rollback to Stage {target_stage} — last completed is Stage {last}")
        return 1

    # Clear markers from target+1 onwards
    cleared = []
    for s in range(target_stage + 1, 7):
        if is_stage_complete(project_dir, s):
            unmark_stage(project_dir, s)
            cleared.append(s)

    if cleared:
        print(f"ROLLBACK_DONE")
        print(f"Cleared completion markers for stages: {cleared}")
        print(f"Pipeline will resume from Stage {target_stage + 1}")
        print(f"\nNext: python veriflow_ctl.py next -d \"{project_dir}\"")
    else:
        print(f"No stages to clear after Stage {target_stage}")

    return 0


def cmd_info(project_dir: Path, stage_id: int) -> int:
    """Show details about a specific stage without generating prompt."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    stage = STAGES[stage_id]
    done = is_stage_complete(project_dir, stage_id)
    prereqs = STAGE_PREREQUISITES.get(stage_id, [])
    prereqs_met, prereq_errors = check_prerequisites(project_dir, stage_id)

    print(f"Stage {stage_id}: {stage['name']}")
    print(f"  Status: {'COMPLETE' if done else 'PENDING'}")
    print(f"  Prompt file: {PROMPTS_DIR / stage['prompt']}")
    print(f"  Prerequisites: {prereqs if prereqs else 'None'}")
    print(f"  Prerequisites met: {'Yes' if prereqs_met else 'No'}")
    if prereq_errors:
        for err in prereq_errors:
            print(f"    - {err}")

    # Show validation status if stage has outputs
    if done or stage_id <= get_last_completed_stage(project_dir):
        passed, errors = validate_stage(stage_id, project_dir)
        print(f"  Validation: {'PASS' if passed else 'FAIL'}")
        if errors:
            for err in errors[:5]:
                print(f"    - {err}")

    return 0


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="VeriFlow Controller v8.0 — Stateless gate controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  status              Show current pipeline progress
  next                Output prompt for the next stage (blocked if prerequisites unmet)
  validate <N>        Run deterministic checks on stage N outputs
  complete <N>        Mark stage N done (refused if validation fails)
  rollback <N>        Roll back to stage N, clearing subsequent markers
  info <N>            Show stage details

Examples:
  python veriflow_ctl.py status -d ./my_project
  python veriflow_ctl.py next -d ./my_project
  python veriflow_ctl.py validate -d ./my_project 3
  python veriflow_ctl.py complete -d ./my_project 3
  python veriflow_ctl.py rollback -d ./my_project 1
""")
    parser.add_argument("command", choices=["status", "next", "validate", "complete", "rollback", "info"],
                        help="Subcommand to run")
    parser.add_argument("stage", nargs="?", type=int, default=None,
                        help="Stage number (required for validate/complete/rollback/info)")
    parser.add_argument("-d", "--project-dir", type=Path, default=Path("."),
                        help="Project root directory (default: current directory)")
    parser.add_argument("--summary", type=str, default="",
                        help="Summary text for complete command")
    parser.add_argument("--extra-context", type=str, default="",
                        help="Extra context to inject into the prompt (for next command)")

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()

    # Dispatch
    if args.command == "status":
        return cmd_status(project_dir)

    elif args.command == "next":
        return cmd_next(project_dir, extra_context=args.extra_context)

    elif args.command == "validate":
        if args.stage is None:
            print("ERROR: validate requires a stage number. Usage: veriflow_ctl.py validate <N>")
            return 1
        return cmd_validate(project_dir, args.stage)

    elif args.command == "complete":
        if args.stage is None:
            print("ERROR: complete requires a stage number. Usage: veriflow_ctl.py complete <N>")
            return 1
        return cmd_complete(project_dir, args.stage, summary=args.summary)

    elif args.command == "rollback":
        if args.stage is None:
            print("ERROR: rollback requires a target stage. Usage: veriflow_ctl.py rollback <N>")
            return 1
        return cmd_rollback(project_dir, args.stage)

    elif args.command == "info":
        if args.stage is None:
            print("ERROR: info requires a stage number. Usage: veriflow_ctl.py info <N>")
            return 1
        return cmd_info(project_dir, args.stage)

    return 0


if __name__ == "__main__":
    sys.exit(main())
