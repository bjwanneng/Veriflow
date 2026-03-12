---
name: verilog-flow-skill
description: Industrial-grade Verilog code generation system with timing and micro-architecture awareness. Generates RTL code from YAML timing scenarios, runs lint checks, simulates with golden trace verification, and performs synthesis analysis. Includes project layout management, vendor-specific coding styles, stage gate quality checks, structured execution logging, and post-run self-evolution analysis. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when the user mentions Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "3.2.0"
  category: hardware-design
---

# VeriFlow-Agent 3.2

Industrial-grade Verilog code generation system with timing and micro-architecture awareness.

## MANDATORY WORKFLOW RULES

**These rules are NON-NEGOTIABLE. You MUST follow them exactly. Violating any rule is a critical error.**

### Rule 1: NEVER skip stages
The workflow has 5 stages: Spec(1) → Timing(2) → Codegen(3) → Sim(4) → Synth(5).
You MUST complete them IN ORDER. You MUST NOT jump from Stage 1 to Stage 3.
You MUST NOT jump from Stage 3 to Stage 5.

### Rule 2: ALWAYS run lint before simulation
Before entering Stage 4 (simulation), you MUST run `LintChecker.check()` on ALL generated .v files.
If any lint issue has severity="error", you MUST fix it before proceeding.
Do NOT ignore lint errors. Do NOT skip lint.

### Rule 3: ALWAYS get human approval before stage transition
Before moving from one stage to the next, you MUST:
1. Show the user a summary of what was done in the current stage
2. Show any warnings or issues found
3. Ask the user to confirm before proceeding
4. If using the Python API: call `checker.require_manual_approval(from_stage, to_stage)`
5. If the user says "no" or "stop", you MUST stop immediately

### Rule 4: NEVER generate placeholder code
All generated Verilog modules MUST be complete, synthesizable implementations.
Do NOT write `// TODO`, `// placeholder`, or empty module bodies.
Do NOT use `$display` or `$finish` in synthesizable code (only in testbenches).

### Rule 5: ALWAYS use Verilog-2005 compatible syntax
- Do NOT use SystemVerilog syntax (logic, interface, always_ff, always_comb)
- Do NOT declare reg/wire inside unnamed begin...end blocks
- Do NOT use `reg` for signals driven by `assign` — use `wire`
- Do NOT use forward references (declare before use)

### Rule 6: ALWAYS check AXI-Stream handshake protocol
When generating AXI-Stream interfaces:
- `valid` MUST be held HIGH until `ready` acknowledges (valid && ready)
- Do NOT pulse `valid` for one cycle without checking `ready`
- Do NOT deassert `valid` before `ready` is seen
- `tdata` MUST NOT change while `valid` is high and `ready` is low

### Rule 7: Error recovery
If iverilog compilation fails:
1. Read the FULL error message
2. Check if it matches a known lint rule (REG_DRIVEN_BY_ASSIGN, FORWARD_REFERENCE, etc.)
3. Fix the root cause — do NOT add workarounds or suppress warnings
4. Re-run lint, then re-compile

If simulation hangs (no output for >10 seconds):
1. Check for missing `$finish` in testbench
2. Check for combinational loops
3. Use `timeout` wrapper: `timeout 30 vvp sim.vvp`

### Rule 8: Windows toolchain
On Windows with oss-cad-suite:
- MUST add BOTH `bin/` AND `lib/` to PATH
- MUST NOT wrap commands in `cmd.exe /c` — run directly from bash
- Use `toolchain_detect.detect_toolchain()` to get correct environment

## Overview

VeriFlow-Agent 3.0 addresses the common problem in Verilog code generation: **"Logically correct, physically failing"**. By adopting a "Shift-Left" philosophy, it brings micro-architecture planning and physical timing estimation to the pre-code-generation phase.

### When to Use

Use this skill when:
- Generating Verilog/RTL code for FPGA or ASIC designs
- Creating testbenches for hardware verification
- Running lint checks on Verilog code
- Performing synthesis and timing analysis
- Defining timing scenarios for hardware testing
- Validating hardware designs against golden references
- Initializing a VeriFlow project with standard directory layout
- Applying vendor-specific coding styles (Xilinx, Intel, generic)
- Running stage gate quality checks between pipeline stages
- Analyzing pipeline execution history for improvement insights

## Quick Start

### 1. Initialize a Project

```bash
# Create standard directory layout + coding style defaults
verilog-flow init --vendor xilinx
```

### 2. Define a Timing Scenario (YAML)

```yaml
scenario: "FIFO_Write_Burst"
description: "Test FIFO write operations with burst transfers"
parameters:
  DEPTH: 4
  DATA_WIDTH: 32
clocks:
  clk:
    period: "5ns"
phases:
  - name: "Reset_Phase"
    duration_ns: 50
    signals: { rst_n: 0, wr_en: 0, rd_en: 0 }
    assertions: ["full == 0", "empty == 1"]
  - name: "Write_Phase"
    duration_ns: 20
    repeat: { count: "$DEPTH", var: "i" }
    signals: { rst_n: 1, wr_en: 1, wr_data: "$i * 2" }
```

### 3. Validate & Generate

```bash
verilog-flow validate scenario.yaml
verilog-flow waveform scenario.yaml --output waveform.html
vf-codegen fifo --depth 16 --width 32 --output rtl/
```

### 4. Run Quality Checks

```bash
verilog-flow check           # All stages
verilog-flow check --stage 3 # Stage 3 only
```

### 5. Run Simulation & Synthesis

```bash
vf-sim run rtl/sync_fifo.v scenario.yaml --top sync_fifo --simulator iverilog
vf-synth run rtl/sync_fifo.v --top sync_fifo --freq 200
```

### 6. Post-Run Analysis

```bash
verilog-flow analyze --runs 10
```

## Five-Stage Workflow

### Stage 1 & 1.5: Micro-Architecture Specification

```python
from verilog_flow import MicroArchitect
architect = MicroArchitect()
spec = architect.design_from_requirements("my_fifo", {
    "target_frequency_mhz": 200, "data_width": 32, "fifo_depth": 16
})
spec.save("output/")
```

### Stage 2: Virtual Timing Modeling

```python
from verilog_flow import parse_yaml_scenario, generate_golden_trace, generate_wavedrom
with open("scenario.yaml") as f:
    scenario = parse_yaml_scenario(f.read())
trace = generate_golden_trace(scenario)
trace.save("golden_trace.json")
html = generate_wavedrom(scenario, output_path="waveform.html")
```

### Stage 3: Code Generation with Lint Check

```python
from verilog_flow import RTLCodeGenerator, ProjectLayout, CodingStyleManager
from verilog_flow.stage3.lint_checker import LintChecker
from pathlib import Path

layout = ProjectLayout(Path("."))
style = CodingStyleManager(layout).get_style("xilinx")
generator = RTLCodeGenerator(coding_style=style)
module = generator.generate_fifo(depth=16, data_width=32)
module.save(layout.get_dir(3, "rtl"))

# MANDATORY: Run lint on ALL generated files before proceeding to Stage 4
linter = LintChecker()
for vfile in layout.get_dir(3, "rtl").rglob("*.v"):
    result = linter.check_file(vfile)
    if not result.passed:
        print(f"LINT ERRORS in {vfile}:")
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.rule_id}: {issue.message} (line {issue.line_number})")
        raise RuntimeError(f"Lint failed for {vfile} — fix errors before Stage 4")
    print(f"  PASS: {vfile} ({result.warning_count} warnings)")
```

### Stage 4: Physical Simulation & Verification

```python
from verilog_flow import TestbenchGenerator, TestbenchConfig, SimulationRunner
from verilog_flow.common.experience_db import ExperienceDB

config = TestbenchConfig(module_name="sync_fifo")
tb_gen = TestbenchGenerator(config)

# Pass experience_db to auto-record results (optional but recommended)
exp_db = ExperienceDB()
runner = SimulationRunner(simulator="iverilog", output_dir="sim_output",
                          experience_db=exp_db)
result = runner.run(design_files=["rtl/sync_fifo.v"],
                    testbench_file="tb.sv", top_module="tb_sync_fifo")

# MANDATORY: Check result before proceeding
if not result.success:
    print(f"SIMULATION FAILED: {result.error}")
    print("Fix the issue and re-run. Do NOT proceed to Stage 5.")
else:
    print(f"PASS: {result.tests_passed} tests, {result.assertions_passed} assertions")
```

### Stage 5: Synthesis-Level Verification

```python
from verilog_flow import SynthesisRunner
runner = SynthesisRunner(output_dir="synth_output")
result = runner.run(verilog_files=["rtl/sync_fifo.v"],
                    top_module="sync_fifo", target_frequency_mhz=200)
```

## Infrastructure Modules

### ProjectLayout — Directory Management

```python
from verilog_flow import ProjectLayout
layout = ProjectLayout(Path("."))
layout.initialize()                    # Create all stage dirs + .veriflow/
layout.get_dir(3, "rtl")              # -> project/stage_3_codegen/rtl/
layout.get_coding_style_dir("xilinx") # -> .veriflow/coding_style/xilinx/
layout.migrate_legacy()               # Move old flat dirs to new layout
```

### CodingStyleManager — Vendor-Specific Coding Rules

Built-in presets: `generic` (async active-low rst_n, 4-space), `xilinx` (sync active-high rst, UG901), `intel` (async active-low rst_n, 3-space).

**IMPORTANT**: The vendor preset (Python CodingStyle object) is the authoritative source for reset style, naming, and indentation. The `base_style.md` document is a reference guide based on Xilinx verilog-ethernet conventions — if it conflicts with your chosen vendor preset, the preset wins.

```python
from verilog_flow import CodingStyleManager
mgr = CodingStyleManager(layout)
mgr.initialize_defaults()  # Copy default .md docs & .v templates to project
style = mgr.get_style("xilinx")
doc = mgr.get_style_doc("xilinx")       # Markdown coding style reference
tpl = mgr.get_template("template_sync_fifo")  # .v template content
templates = mgr.list_templates()         # All available template names
issues = mgr.validate_code(verilog_code, style)
```

### StageGateChecker — Quality Gates (Human-in-the-Loop)

Every stage transition requires manual approval. Do NOT skip this step.

```python
from verilog_flow import StageGateChecker
checker = StageGateChecker(layout)

# Step 1: Check current stage quality
result = checker.check_stage(3)
print(f"Errors: {result.error_count}, Warnings: {result.warning_count}")

# Step 2: Request human approval (MANDATORY before proceeding)
# Interactive mode — prints summary and asks user for y/N:
approval = checker.require_manual_approval(3, 4)

# Alternative: programmatic mode with explicit token
result = checker.check_transition(3, 4, approve_token="approved", approved_by="engineer")
assert result.fully_approved  # True only if gate passed AND approval given
```

**WARNING**: `check_transition()` without `approve_token` will FAIL with APPROVAL_REQUIRED error. This is intentional — every transition needs explicit human sign-off.

### ExecutionLogger — Structured Run Logs

```python
from verilog_flow import ExecutionLogger
logger = ExecutionLogger(layout)
run = logger.start_run("my_project")
with logger.stage(3, "codegen") as slog:
    slog.metrics["files_generated"] = 5
logger.end_run(success=True)
# Saved to .veriflow/logs/run_YYYYMMDD_HHMMSS.json
```

### PostRunAnalyzer — Self-Evolution

```python
from verilog_flow import PostRunAnalyzer
analyzer = PostRunAnalyzer(layout)
report = analyzer.analyze(n_recent=10)
# Detects: repeated failures, performance regressions, coverage gaps
# Saves to: reports/post_run_analysis.json
```

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `verilog-flow init [--vendor V]` | Initialize project directory + coding style |
| `verilog-flow check [--stage N]` | Run stage gate quality checks |
| `verilog-flow analyze [--runs N]` | Post-run analysis for self-evolution |
| `verilog-flow validate <yaml>` | Validate YAML timing scenario |
| `verilog-flow waveform <yaml>` | Generate WaveDrom waveform |
| `verilog-flow trace <yaml>` | Generate Golden Trace |
| `verilog-flow dashboard` | Display KPI dashboard |
| `vf-codegen generate <spec>` | Generate RTL from spec |
| `vf-codegen fifo` | Generate FIFO module |
| `vf-codegen handshake` | Generate handshake register |
| `vf-codegen lint <file>` | Run lint check |
| `vf-sim run` | Run simulation |
| `vf-sim diff` | Compare waveforms |
| `vf-synth run` | Run synthesis |
| `vf-synth analyze` | Detailed timing/area analysis |

## v3.2 Changelog — Real-Project Hardening

### New Lint Rules (5 rules added to `lint_checker.py`)

| Rule ID | Severity | Description |
|---------|----------|-------------|
| `REG_DRIVEN_BY_ASSIGN` | error | `reg` signal driven by `assign` — must be `wire` |
| `FORWARD_REFERENCE` | error | Signal used before declaration (iverilog -g2005 strict) |
| `NBA_AS_COMBINATIONAL` | warning | Non-blocking `<=` target read combinationally in same block |
| `MULTI_DRIVER_CONFLICT` | error | Signal driven by both `always` and `assign` |
| `AXIS_HANDSHAKE_PULSE` | warning | AXI-Stream `valid` cleared without checking `ready` |

### Enhanced Coding Style Validation

`CodingStyleManager.validate_code()` now enforces:
- Module name snake_case check
- Signal name snake_case check
- Parameter UPPER_CASE check

### Toolchain Auto-Detection (`common/toolchain_detect.py`)

- Auto-detects OS and oss-cad-suite installation
- Windows: automatically adds `lib/` to PATH for DLL resolution
- Unified `shell_env()` for all subprocess calls (sim + synth)
- Avoids `cmd.exe /c` wrapper issues on Windows

### Experience DB Auto-Recording

`SimulationRunner` and `SynthesisRunner` now accept optional `experience_db` parameter:
- On failure: auto-records `FailureCase` with error details
- On success: auto-records `DesignPattern` with metrics (cell count, timing, etc.)

### Human-in-the-Loop Stage Gate

Stage transitions now require explicit manual approval:

```python
# Interactive (CLI)
checker = StageGateChecker(layout)
checker.require_manual_approval(3, 4)  # Prints summary, asks y/N

# Programmatic (CI/script)
result = checker.check_transition(3, 4, approve_token="my_token", approved_by="engineer_name")
assert result.fully_approved
```

Approval records are persisted to `.veriflow/approvals/` for audit trail.

## Common Errors Quick Reference

If you encounter any of these errors, follow the fix instructions exactly:

| Error Message | Root Cause | Fix |
|---------------|-----------|-----|
| `Variable 'X' cannot be driven by continuous assignment` | `reg` driven by `assign` | Change `reg` to `wire` for signal X |
| `Unable to bind wire/reg/memory 'X'` | Forward reference | Move declaration of X before the line that uses it |
| `Variable declaration in unnamed block requires SystemVerilog` | `reg` inside unnamed `begin...end` | Move reg declaration to module level, or add a name to the block |
| `Multiple drivers on signal 'X'` | Signal driven by both `always` and `assign` | Use only ONE driver type: either always (reg) or assign (wire) |
| Simulation hangs, no output | Missing `$finish`, combinational loop, or deadlock | Add `$finish` to testbench; check for `assign a = b; assign b = a;` loops |
| `AXIS_HANDSHAKE_PULSE` warning | `valid` cleared without checking `ready` | Hold `valid` high until `ready` acknowledges: `if (valid && ready) valid <= 0;` |
| Exit code 127 on Windows | Missing DLL path | Add `oss-cad-suite/lib` to PATH alongside `bin` |
| `APPROVAL_REQUIRED` error | Stage transition without approval | Call `require_manual_approval()` or pass `approve_token` parameter |

## Troubleshooting

### Import Error
```bash
cd verilog_flow && pip install -e .
```

### Yosys / Simulator Not Found
Install Yosys (`apt install yosys` / `brew install yosys`) or Icarus Verilog (`apt install iverilog`).

As of v3.2, toolchain auto-detection handles oss-cad-suite on Windows/Linux/macOS automatically. If tools are still not found, set `YOSYSHQ_ROOT` environment variable to your oss-cad-suite directory.

### Windows: cmd.exe Swallows Output
Do NOT wrap iverilog/yosys in `cmd.exe /c`. VeriFlow v3.2 runs tools directly with correct PATH via `toolchain_detect`.

## License

MIT License
