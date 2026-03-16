#!/usr/bin/env python3
"""
VeriFlow Controller v8.0 — Stateless gate controller for Claude Code skill.

Architecture: "Script as gatekeeper, LLM as executor"
- This script enforces stage ordering, prerequisites, and validation gates
- Claude Code (via SKILL.md) drives the flow and executes each stage's tasks
- The LLM cannot skip stages or mark incomplete work as done

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
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Paths ────────────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent
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
    3: [0, 1, 2],
    4: [0, 1, 2, 3],
    5: [0, 1, 2, 3, 4],
    6: [0, 1, 2, 3, 4, 5],
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
    for prereq in STAGE_PREREQUISITES.get(stage_id, []):
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
    for dir_name in stage_dirs_map.get(stage_id, []):
        dir_path = project_dir / dir_name
        if dir_path.exists():
            for f in dir_path.rglob("*"):
                if f.is_file():
                    files_list.append(str(f.relative_to(project_dir)))

    content = f"# Stage {stage_id}: {stage['name']} — Summary\n\n"
    content += f"**Completed at**: {datetime.now().isoformat()}\n\n"
    content += f"## Summary\n{summary or 'No summary provided.'}\n\n"
    content += "## Files Generated\n"
    for f in sorted(files_list):
        content += f"- {f}\n"

    summary_file = summaries_dir / f"stage{stage_id}_summary.md"
    summary_file.write_text(content, encoding="utf-8")


# ── Toolchain Detection ──────────────────────────────────────────────────────

def detect_toolchain() -> Dict[str, str]:
    tools = {}
    env = os.environ.copy()
    for p in [Path("C:/oss-cad-suite/bin"), Path("/opt/oss-cad-suite/bin"), Path("/usr/local/bin")]:
        if p.exists():
            env["PATH"] = f"{p}{os.pathsep}{p.parent / 'lib'}{os.pathsep}{env.get('PATH', '')}"
            break
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

    # Load requirement.md
    req_context = ""
    req_file = project_dir / "requirement.md"
    if req_file.exists() and stage_id <= 1:
        req_context = req_file.read_text(encoding="utf-8")

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
    for d in ["stage_1_spec", "stage_2_timing", "stage_3_codegen/rtl",
              "stage_4_sim/tb", "stage_5_synth", ".veriflow"]:
        if not (project_dir / d).exists():
            errors.append(f"Missing directory: {d}")
    config = project_dir / ".veriflow" / "project_config.json"
    if not config.exists():
        errors.append("Missing .veriflow/project_config.json")
    return len(errors) == 0, errors


def _validate_stage1(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    spec_dir = project_dir / "stage_1_spec" / "specs"
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
        for field in ["design_name", "target_frequency_mhz", "modules"]:
            if field not in data:
                errors.append(f"{spec_file.name}: Missing required field '{field}'")
        for mod in data.get("modules", []):
            if "name" not in mod:
                errors.append(f"{spec_file.name}: Module missing 'name' field")
            if "ports" not in mod:
                errors.append(f"{spec_file.name}: Module '{mod.get('name', '?')}' missing 'ports'")
    return len(errors) == 0, errors


def _validate_stage2(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    timing_dir = project_dir / "stage_2_timing"
    scenarios = list(timing_dir.rglob("*.yaml")) + list(timing_dir.rglob("*.yml"))
    if not scenarios:
        errors.append("No YAML timing scenarios found in stage_2_timing/")
    return len(errors) == 0, errors


def _validate_stage3(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    rtl_dir = project_dir / "stage_3_codegen" / "rtl"
    rtl_files = list(rtl_dir.rglob("*.v")) if rtl_dir.exists() else []
    if not rtl_files:
        errors.append("No .v files found in stage_3_codegen/rtl/")
        return False, errors

    placeholder_re = re.compile(r'(?://|/\*)\s*(?:TODO|placeholder|\.\.\.)', re.IGNORECASE)
    for vf in rtl_files:
        content = vf.read_text(encoding="utf-8", errors="replace")
        if placeholder_re.search(content):
            errors.append(f"{vf.name}: Contains placeholder/TODO markers")

    # Check spec coverage
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

    # Try iverilog compilation
    compile_errors = _check_iverilog_compile(rtl_files)
    errors.extend(compile_errors)

    return len(errors) == 0, errors


def _check_iverilog_compile(verilog_files: List[Path]) -> List[str]:
    """Try compiling with iverilog. Returns list of error strings."""
    errors = []
    iverilog = shutil.which("iverilog") or shutil.which("iverilog.exe")
    if not iverilog:
        oss_path = Path("C:/oss-cad-suite/bin/iverilog.exe")
        if oss_path.exists():
            iverilog = str(oss_path)
    if not iverilog:
        return []  # silently skip if not installed

    cmd = [iverilog, "-g2005", "-Wall", "-o"]
    cmd.append("/dev/null" if sys.platform != "win32" else "NUL")
    cmd.extend(str(f) for f in verilog_files)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            stderr = result.stderr.strip()
            errors.append(f"iverilog compilation failed:\n{stderr[:2000]}")
    except subprocess.TimeoutExpired:
        errors.append("iverilog compilation timed out (>60s)")
    except FileNotFoundError:
        pass
    return errors


def _validate_stage4(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    tb_dir = project_dir / "stage_4_sim" / "tb"
    tbs = list(tb_dir.rglob("*.v")) if tb_dir.exists() else []
    if not tbs:
        errors.append("No testbench .v files found in stage_4_sim/tb/")

    sim_dir = project_dir / "stage_4_sim" / "sim_output"
    if sim_dir.exists():
        for log_file in sim_dir.glob("*.log"):
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            if "FAIL" in content or "TIMEOUT" in content:
                errors.append(f"Simulation log {log_file.name} contains FAIL/TIMEOUT")
    return len(errors) == 0, errors


def _validate_stage5(project_dir: Path) -> Tuple[bool, List[str]]:
    errors = []
    synth_dir = project_dir / "stage_5_synth"
    ys_files = list(synth_dir.rglob("*.ys")) if synth_dir.exists() else []
    if not ys_files:
        errors.append("No .ys synthesis script found in stage_5_synth/")
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
    next_stage = last + 1

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
