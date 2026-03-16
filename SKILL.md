---
name: verilog-flow-skill
description: Industrial-grade Verilog design pipeline with script-controlled orchestration and LLM-executed stages. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when you mention Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "8.0.0"
  category: hardware-design
---

# VeriFlow-Agent 8.0 — Gate-Controlled Pipeline

Architecture: **Script as gatekeeper, LLM as executor.**
- `veriflow_ctl.py` enforces stage ordering, prerequisites, and validation gates
- You (Claude Code) drive the flow and execute each stage's creative tasks
- You cannot skip stages or mark incomplete work as done — the script prevents it

## Pipeline Stages

| Stage | Name | Key Output |
|-------|------|------------|
| 0 | Project Initialization | Directory structure, project_config.json |
| 1 | Micro-Architecture Spec | `stage_1_spec/specs/*_spec.json` |
| 2 | Virtual Timing Modeling | YAML scenarios, golden traces, Cocotb tests |
| 3 | RTL Code Generation + Lint | `stage_3_codegen/rtl/*.v`, testbenches |
| 4 | Simulation & Verification | Testbenches, sim logs (all PASS) |
| 5 | Synthesis Analysis | Yosys synthesis, synth_report.json |
| 6 | Closing | `reports/final_report.md` |

## EXECUTION PROTOCOL

**You MUST follow this exact loop. Do NOT deviate.**

The controller script path is:
```
CTL="C:\Users\wanneng.zhang\.claude\skills\verilog-flow-skill\veriflow_ctl.py"
```

### Loop: repeat until all stages complete

**Step 1 — Get next stage prompt**
```bash
python "$CTL" next -d "PROJECT_DIR"
```
- If output starts with `BLOCKED:` → a prerequisite stage is incomplete. Fix it first.
- If output starts with `ALL_STAGES_COMPLETE` → pipeline is done. Stop.
- Otherwise, the output contains `---BEGIN_PROMPT---` ... `---END_PROMPT---` with the full task instructions.

**Step 2 — Execute the tasks**
Read the prompt output from Step 1 and execute ALL tasks described in it. This is where you do the real work: generate specs, write Verilog, create testbenches, run simulations, etc.

**Step 3 — Validate**
```bash
python "$CTL" validate -d "PROJECT_DIR" STAGE_NUMBER
```
- If `VALIDATION_PASSED` → proceed to Step 4.
- If `VALIDATION_FAILED` → read the errors, fix them, then re-run validate. Do NOT proceed until validation passes.

**Step 4 — Mark complete**
```bash
python "$CTL" complete -d "PROJECT_DIR" STAGE_NUMBER
```
- If `STAGE_COMPLETE` → go back to Step 1 for the next stage.
- If `REFUSED` → validation failed internally. Fix errors and retry.

**Step 5 — (If needed) Ask user before proceeding to next stage**
For stages 1-5, use AskUserQuestion to confirm with the user before moving to the next stage. Show them a brief summary of what was accomplished.

### Rollback (when stuck)
If a stage repeatedly fails and the root cause is in an earlier stage:
```bash
python "$CTL" rollback -d "PROJECT_DIR" TARGET_STAGE
```
This clears all completion markers after TARGET_STAGE. Then resume the loop from Step 1.

### Check progress anytime
```bash
python "$CTL" status -d "PROJECT_DIR"
```

## IMPORTANT RULES

1. **Always use the controller** — never manually create `.veriflow/stage_completed/` marker files
2. **Never skip validation** — always run `validate` before `complete`
3. **Fix errors in-place** — if validation fails, fix the files and re-validate; do not move on
4. **One stage at a time** — the controller enforces sequential execution
5. **requirement.md** — the project directory must contain a `requirement.md` file describing the design
6. **Windows PATH** — for iverilog/yosys, add to PATH: `export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"`
