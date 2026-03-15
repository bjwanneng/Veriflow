#!/usr/bin/env python3
"""VeriFlow Orchestrator v6.0 — Script-controlled, LLM-executed pipeline.

Architecture:
  - This script controls stage sequencing, validation, and retry logic
  - Claude Code (via `claude -p`) acts as the agent within each stage
  - Each stage has a focused prompt file in prompts/
  - Validation runs between stages to catch errors before proceeding

Usage:
  python veriflow_orchestrator.py --project-dir /path/to/project
  python veriflow_orchestrator.py --project-dir /path/to/project --start-stage 3
  python veriflow_orchestrator.py --project-dir /path/to/project --stage 3  # single stage
"""

import argparse
import json
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Constants ────────────────────────────────────────────────────────────────

STAGES = [
    {"id": 0, "name": "Project Initialization",       "prompt": "stage0_init.md"},
    {"id": 1, "name": "Micro-Architecture Specification", "prompt": "stage1_spec.md"},
    {"id": 2, "name": "Virtual Timing Modeling",       "prompt": "stage2_timing.md"},
    {"id": 3, "name": "RTL Code Generation + Lint",    "prompt": "stage3_codegen.md"},
    {"id": 4, "name": "Simulation & Verification",     "prompt": "stage4_sim.md"},
    {"id": 5, "name": "Synthesis Analysis",            "prompt": "stage5_synth.md"},
    {"id": 6, "name": "Closing",                       "prompt": "stage6_close.md"},
]

MAX_RETRIES = 3
PROMPTS_DIR = Path(__file__).parent / "prompts"
SKILL_DIR = Path(__file__).parent

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "  ", "OK": "✓ ", "FAIL": "✗ ", "WARN": "! ", "RUN": "▶ "}
    print(f"[{ts}] {prefix.get(level, '  ')}{msg}")


def get_marker_path(project_dir: Path, stage_id: int) -> Path:
    return project_dir / ".veriflow" / "stage_completed" / f"stage_{stage_id}.complete"


def is_stage_complete(project_dir: Path, stage_id: int) -> bool:
    return get_marker_path(project_dir, stage_id).exists()


def mark_stage_complete(project_dir: Path, stage_id: int, summary: str = ""):
    marker = get_marker_path(project_dir, stage_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "stage": stage_id,
        "name": STAGES[stage_id]["name"],
        "completed_at": datetime.now().isoformat(),
        "summary": summary,
    }
    marker.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_last_completed_stage(project_dir: Path) -> int:
    """Return the highest completed stage ID, or -1 if none."""
    for s in range(6, -1, -1):
        if is_stage_complete(project_dir, s):
            return s
    return -1


def detect_toolchain() -> Dict[str, str]:
    """Detect iverilog and yosys versions."""
    tools = {}
    oss_bin = Path("C:/oss-cad-suite/bin")
    env = os.environ.copy()
    if oss_bin.exists():
        env["PATH"] = f"{oss_bin}{os.pathsep}{oss_bin.parent / 'lib'}{os.pathsep}{env.get('PATH', '')}"

    for tool in ["iverilog", "yosys"]:
        try:
            r = subprocess.run([tool, "-V"], capture_output=True, text=True, timeout=10, env=env)
            first_line = r.stdout.strip().split("\n")[0] if r.stdout else "unknown"
            tools[tool] = first_line
        except (FileNotFoundError, subprocess.TimeoutExpired):
            tools[tool] = "not found"
    return tools


# ── Prompt Builder ───────────────────────────────────────────────────────────

def build_prompt(stage_id: int, project_dir: Path, extra_context: str = "") -> str:
    """Build the full prompt for a stage by loading the template and injecting context."""
    prompt_file = PROMPTS_DIR / STAGES[stage_id]["prompt"]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    template = prompt_file.read_text(encoding="utf-8")

    # Load coding style reference (for stages that need it)
    style_ref = ""
    style_file = SKILL_DIR / "verilog_flow" / "defaults" / "coding_style" / "generic" / "base_style.md"
    if style_file.exists() and stage_id in (1, 2, 3):
        style_ref = style_file.read_text(encoding="utf-8")

    # Load spec JSON if it exists (for stages 2+)
    spec_context = ""
    spec_dir = project_dir / "stage_1_spec" / "specs"
    if spec_dir.exists() and stage_id >= 2:
        for f in spec_dir.glob("*_spec.json"):
            spec_context += f"\n--- {f.name} ---\n{f.read_text(encoding='utf-8')}\n"

    # Load requirement.md if it exists
    req_context = ""
    req_file = project_dir / "requirement.md"
    if req_file.exists() and stage_id <= 1:
        req_context = req_file.read_text(encoding="utf-8")

    # Substitute placeholders
    prompt = template.replace("{{PROJECT_DIR}}", str(project_dir))
    prompt = prompt.replace("{{CODING_STYLE}}", style_ref[:3000] if style_ref else "(not loaded)")
    prompt = prompt.replace("{{SPEC_JSON}}", spec_context[:8000] if spec_context else "(not yet generated)")
    prompt = prompt.replace("{{REQUIREMENT}}", req_context[:5000] if req_context else "(not found)")
    prompt = prompt.replace("{{EXTRA_CONTEXT}}", extra_context)
    prompt = prompt.replace("{{TOOLCHAIN}}", json.dumps(detect_toolchain()))

    return prompt


# ── Claude Code Invocation ───────────────────────────────────────────────────

def run_claude(prompt: str, project_dir: Path, timeout_min: int = 15) -> Tuple[int, str]:
    """Invoke Claude Code CLI with the given prompt.

    Returns (exit_code, stdout).
    """
    cmd = [
        "claude", "-p", prompt,
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep,AskUserQuestion",
    ]
    log(f"Invoking Claude Code ({len(prompt)} chars prompt)...", "RUN")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_min * 60,
            cwd=str(project_dir),
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"[TIMEOUT] Claude Code did not finish within {timeout_min} minutes"
    except FileNotFoundError:
        return 127, "[ERROR] 'claude' command not found. Is Claude Code installed and in PATH?"


# ── Stage Validators ─────────────────────────────────────────────────────────

def validate_stage(stage_id: int, project_dir: Path) -> Tuple[bool, List[str]]:
    """Validate a stage's output. Returns (passed, list_of_errors)."""
    validators = {
        0: _validate_stage0,
        1: _validate_stage1,
        2: _validate_stage2,
        3: _validate_stage3,
        4: _validate_stage4,
        5: _validate_stage5,
        6: _validate_stage6,
    }
    validator = validators.get(stage_id)
    if not validator:
        return True, []
    return validator(project_dir)


def _validate_stage0(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 0: Check directories and config exist."""
    errors = []
    required_dirs = [
        "stage_1_spec", "stage_2_timing", "stage_3_codegen/rtl",
        "stage_4_sim/tb", "stage_5_synth", ".veriflow",
    ]
    for d in required_dirs:
        if not (project_dir / d).exists():
            errors.append(f"Missing directory: {d}")

    config = project_dir / ".veriflow" / "project_config.json"
    if not config.exists():
        errors.append("Missing .veriflow/project_config.json")

    return len(errors) == 0, errors


def _validate_stage1(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 1: Check spec JSON exists and is valid."""
    errors = []
    spec_dir = project_dir / "stage_1_spec" / "specs"
    if not spec_dir.exists():
        spec_dir = project_dir / "stage_1_spec"

    specs = list(spec_dir.glob("*_spec.json"))
    if not specs:
        errors.append("No *_spec.json found in stage_1_spec/")
        return False, errors

    for spec_file in specs:
        try:
            data = json.loads(spec_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{spec_file.name}: Invalid JSON — {e}")
            continue

        # Check required top-level fields
        for field in ["design_name", "target_frequency_mhz", "modules"]:
            if field not in data:
                errors.append(f"{spec_file.name}: Missing required field '{field}'")

        # Check modules have required fields
        for mod in data.get("modules", []):
            if "name" not in mod:
                errors.append(f"{spec_file.name}: Module missing 'name' field")
            if "ports" not in mod:
                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' missing 'ports'")

        # Run requirement validator if available
        try:
            sys.path.insert(0, str(SKILL_DIR / "verilog_flow"))
            from common.requirement_validator import RequirementValidator
            validator = RequirementValidator()
            report = validator.validate_spec(data)
            for finding in report.errors:
                errors.append(f"[PreCheck] {finding.message}")
        except ImportError:
            pass  # Validator not available, skip

    return len(errors) == 0, errors


def _validate_stage2(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 2: Check YAML scenarios exist."""
    errors = []
    timing_dir = project_dir / "stage_2_timing"
    scenarios = list(timing_dir.rglob("*.yaml")) + list(timing_dir.rglob("*.yml"))
    if not scenarios:
        errors.append("No YAML timing scenarios found in stage_2_timing/")
    return len(errors) == 0, errors


def _validate_stage3(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 3: Check RTL files, run lint, compile."""
    errors = []
    rtl_dir = project_dir / "stage_3_codegen" / "rtl"
    rtl_files = list(rtl_dir.rglob("*.v")) if rtl_dir.exists() else []

    if not rtl_files:
        errors.append("No .v files found in stage_3_codegen/rtl/")
        return False, errors

    # Check no placeholders
    import re
    placeholder_re = re.compile(r'//\s*TODO|//\s*placeholder|//\s*\.\.\.', re.IGNORECASE)
    for vf in rtl_files:
        content = vf.read_text(encoding="utf-8", errors="replace")
        if placeholder_re.search(content):
            errors.append(f"{vf.name}: Contains placeholder/TODO markers")

    # Run Python lint (Layer 1)
    try:
        sys.path.insert(0, str(SKILL_DIR / "verilog_flow"))
        from stage3.lint_checker import LintChecker
        linter = LintChecker()
        for vf in rtl_files:
            result = linter.check_file(vf)
            for issue in result.issues:
                if issue.severity == "error":
                    errors.append(f"[Lint] {vf.name}:{issue.line_number} {issue.rule_id}: {issue.message}")
    except ImportError:
        pass

    # Run iverilog compilation (Layer 2)
    iverilog = shutil.which("iverilog")
    if not iverilog:
        oss = Path("C:/oss-cad-suite/bin/iverilog.exe")
        if oss.exists():
            iverilog = str(oss)

    if iverilog:
        cmd = [iverilog, "-g2005", "-Wall", "-o", os.devnull] + [str(f) for f in rtl_files]
        env = os.environ.copy()
        oss_bin = Path("C:/oss-cad-suite/bin")
        if oss_bin.exists():
            env["PATH"] = f"{oss_bin}{os.pathsep}{oss_bin.parent / 'lib'}{os.pathsep}{env.get('PATH', '')}"
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
            if r.returncode != 0:
                errors.append(f"[iverilog] Compilation failed:\n{r.stderr.strip()}")
        except subprocess.TimeoutExpired:
            errors.append("[iverilog] Compilation timed out")

    return len(errors) == 0, errors


def _validate_stage4(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 4: Check testbenches exist and sim logs show PASS."""
    errors = []
    tb_dir = project_dir / "stage_4_sim" / "tb"
    tbs = list(tb_dir.rglob("*.v")) if tb_dir.exists() else []
    if not tbs:
        errors.append("No testbench .v files found in stage_4_sim/tb/")

    # Check sim output for FAIL
    sim_dir = project_dir / "stage_4_sim" / "sim_output"
    if sim_dir.exists():
        for log_file in sim_dir.glob("*.log"):
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            if "FAIL" in content:
                errors.append(f"[Sim] {log_file.name} contains FAIL")
            if "PASS" not in content:
                errors.append(f"[Sim] {log_file.name} has no PASS verdict")

    return len(errors) == 0, errors


def _validate_stage5(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 5: Check synthesis ran and produced output."""
    errors = []
    synth_dir = project_dir / "stage_5_synth"
    ys_files = list(synth_dir.rglob("*.ys")) if synth_dir.exists() else []
    if not ys_files:
        errors.append("No .ys synthesis script found in stage_5_synth/")
    return len(errors) == 0, errors


def _validate_stage6(project_dir: Path) -> Tuple[bool, List[str]]:
    """Stage 6: Closing — just check report exists."""
    report = project_dir / "reports" / "final_report.md"
    if not report.exists():
        return False, ["No final_report.md in reports/"]
    return True, []


# ── Main Orchestrator Loop ───────────────────────────────────────────────────

def run_stage(stage_id: int, project_dir: Path, extra_context: str = "") -> bool:
    """Execute a single stage: build prompt → call Claude → validate → mark complete.

    Returns True if stage completed successfully.
    """
    stage = STAGES[stage_id]
    print(f"\n{'='*60}")
    print(f"  Stage {stage_id}: {stage['name']}")
    print(f"{'='*60}")

    for attempt in range(1, MAX_RETRIES + 1):
        log(f"Attempt {attempt}/{MAX_RETRIES}", "RUN")

        # Build prompt
        try:
            prompt = build_prompt(stage_id, project_dir, extra_context)
        except FileNotFoundError as e:
            log(str(e), "FAIL")
            return False

        # Call Claude Code
        exit_code, output = run_claude(prompt, project_dir)

        if exit_code != 0:
            log(f"Claude Code exited with code {exit_code}", "WARN")
            if attempt < MAX_RETRIES:
                extra_context = f"Previous attempt failed. Claude output:\n{output[-2000:]}"
                continue
            else:
                log("Max retries reached — stage failed", "FAIL")
                return False

        # Validate output
        log("Validating stage output...", "INFO")
        passed, errors = validate_stage(stage_id, project_dir)

        if passed:
            log(f"Stage {stage_id} validation PASSED", "OK")
            mark_stage_complete(project_dir, stage_id)
            return True
        else:
            log(f"Validation found {len(errors)} error(s):", "WARN")
            for err in errors[:10]:
                log(f"  {err}", "FAIL")
            if attempt < MAX_RETRIES:
                error_summary = "\n".join(errors[:15])
                extra_context = (
                    f"Previous attempt produced output that failed validation.\n"
                    f"Errors to fix:\n{error_summary}\n\n"
                    f"Please fix these issues and ensure all outputs are correct."
                )
            else:
                log("Max retries reached — stage failed", "FAIL")
                return False

    return False


def main():
    parser = argparse.ArgumentParser(
        description="VeriFlow Orchestrator v6.0 — Script-controlled, LLM-executed pipeline")
    parser.add_argument("--project-dir", "-d", type=Path, default=Path("."),
                        help="Project root directory")
    parser.add_argument("--start-stage", "-s", type=int, default=None,
                        help="Start from this stage (default: auto-detect)")
    parser.add_argument("--stage", type=int, default=None,
                        help="Run only this single stage")
    parser.add_argument("--end-stage", "-e", type=int, default=6,
                        help="Stop after this stage (default: 6)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without executing")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    print(f"\nVeriFlow Orchestrator v6.0")
    print(f"Project: {project_dir}")

    # Determine start stage
    if args.stage is not None:
        start = args.stage
        end = args.stage
    elif args.start_stage is not None:
        start = args.start_stage
        end = args.end_stage
    else:
        last = get_last_completed_stage(project_dir)
        start = last + 1
        end = args.end_stage
        if last >= 0:
            log(f"Last completed stage: {last} ({STAGES[last]['name']})", "INFO")
        log(f"Will start from Stage {start}", "INFO")

    if start > 6:
        log("All stages already complete!", "OK")
        return 0

    # Dry run
    if args.dry_run:
        for s in range(start, end + 1):
            print(f"  [DRY] Would run Stage {s}: {STAGES[s]['name']}")
        return 0

    # Execute stages
    for stage_id in range(start, end + 1):
        # Check prerequisites
        if stage_id > 0 and not is_stage_complete(project_dir, stage_id - 1):
            log(f"Stage {stage_id - 1} not complete — cannot proceed to {stage_id}", "FAIL")
            return 1

        success = run_stage(stage_id, project_dir)
        if not success:
            log(f"Pipeline stopped at Stage {stage_id}", "FAIL")
            return 1

    print(f"\n{'='*60}")
    log("Pipeline completed successfully!", "OK")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

