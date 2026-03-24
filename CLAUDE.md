# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VeriFlow is an industrial-grade Verilog RTL design pipeline. It implements a **Control Flow Inversion** architecture where Python acts as the master state machine (orchestrator) and Claude LLM acts as worker nodes called via subprocess. Shell scripts in `tools/` interface with EDA tools (iverilog, Yosys).

## Running the Pipeline

```bash
# Run full pipeline (modes: quick | standard | enterprise)
python veriflow_ctl.py run --mode standard -d <project_dir>

# Interactive Stage 1 (architect REPL) subcommands
python veriflow_ctl.py validate --stage 1 -d <project_dir>
python veriflow_ctl.py complete --stage 1 -d <project_dir>
```

**Dependencies:**
- Python 3.8+
- `claude` CLI (Claude Code) — workers are invoked as subprocesses
- `iverilog` + `vvp` (Icarus Verilog) — for lint and simulation
- `yosys` — optional, required for Enterprise mode Stage 5

Both `iverilog` and `yosys` fall back to mock mode if unavailable.

## Pipeline Stages

| Stage | Name | Output | Modes |
|-------|------|--------|-------|
| 1 | Architect (interactive REPL) | `workspace/docs/spec.json` | all |
| 2 | Virtual Timing Model | `workspace/docs/timing_model.yaml`, `workspace/tb/tb_*.v` | standard, enterprise |
| 2.5 | Human Gate | user review pause | standard, enterprise |
| 3 | RTL Coder | `workspace/rtl/*.v` | all |
| 3.5 | Skill D (static analysis) | `workspace/docs/static_report.json` | standard, enterprise |
| 4 | Simulation Loop | lint + sim, auto-retry with Debugger | all |
| 5 | Yosys Synthesis + KPI | `workspace/docs/synth_report.json` | enterprise |

Quick mode: stages 1 → 3 → 4 (lint only).
Standard mode: stages 1 → 2 → 2.5 → 3 → 3.5 → 4.
Enterprise mode: all stages including 5.

## Project Directory Layout (per design)

Each design project has this structure (created by the pipeline):

```
<project_dir>/
├── requirement.md                  # Input: design requirements (user-authored)
├── .veriflow/
│   ├── project_config.json         # Mode, style, iteration limits
│   └── pipeline_state.json         # Stage completion tracking
└── workspace/
    ├── docs/                       # Spec, timing model, reports, *.done sentinels
    ├── rtl/                        # Generated Verilog-2005 RTL (one module per file)
    ├── tb/                         # Generated testbenches
    └── sim/                        # Simulation outputs, VCD waveforms
```

## Architecture

**`veriflow_ctl.py`** (1925 lines) — the entire orchestration logic lives here:
- `VeriFlowController` class drives the state machine
- Each stage is a method that calls `_run_claude_worker(prompt_file, context)` via subprocess
- Stage completion is tracked via `workspace/docs/stage*.done` sentinel files
- Testbench anti-tampering: MD5 snapshots are taken before/after Debugger runs; testbench is restored if modified

**`veriflow_gui.py`** (1486 lines) — Tkinter GUI wrapper around `veriflow_ctl.py`.

**`prompts/`** — Markdown prompt files injected into each Claude worker call:
- `stage1_architect.md` — interactive Q&A to produce `spec.json`
- `stage2_timing.md` — generates timing model YAML + testbench
- `stage3_coder.md` — generates RTL from spec + timing model
- `stage35_skill_d.md` — static quality analysis
- `stage4_debugger.md` — error correction given lint/sim output

**`tools/`** — ACI shell scripts:
- `run_lint.sh` — wraps `iverilog -Wall`
- `run_sim.sh` — wraps `iverilog` compile + `vvp` simulate

**`verilog_flow/`** — support libraries:
- `common/kpi.py` — `KPITracker`, `RunMetrics`, `StageMetrics` for pipeline telemetry
- `common/experience_db.py` — experience database (future ML integration)
- `defaults/project_templates.json` — mode configurations (quick/standard/enterprise)
- `defaults/coding_style/` — Verilog style guides (generic, Intel, Xilinx)
- `defaults/templates/` — Verilog module templates (FIFO, CDC, FSM, etc.)

## RTL Coding Conventions (enforced by Stage 3 prompt)

- Verilog-2005 only (no SystemVerilog)
- ANSI-style port declarations, 4-space indent, `snake_case` identifiers
- One module per file, filename matches module name
- No placeholder logic — all implementations must be complete and synthesizable

## Quality Gates

- **Stage 1**: `spec.json` must include `target_kpis`
- **Stage 2**: `timing_model.yaml` structure validated before proceeding
- **Stage 3.5**: logic depth budget check + CDC risk level check
- **Stage 4**: automatic retry loop (max iterations in `project_config.json`); testbench protected from Debugger modification
- **Stage 5**: KPI gap >20% triggers a gate warning
