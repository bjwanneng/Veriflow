---
name: verilog-flow-skill
description: Industrial-grade Verilog design pipeline with script-controlled orchestration and LLM-executed stages. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when you mention Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "8.2.0"
  category: hardware-design
---

# VeriFlow 8.2 — Control Flow Inversion Architecture

Architecture: **Python as Master State Machine, LLM as Worker Node**

---

## Quick Start

```bash
# 1. Ensure project directory has requirement.md
# 2. Run the pipeline
python veriflow_ctl.py run --mode quick -d ./my_project
```

---

## Three Execution Modes

| Mode | Stages | 适用场景 | Verification Depth |
|------|--------|----------|-------------------|
| **Quick** | 1→3→4 | Simple modules, prototypes, rapid iteration | Minimal (basic lint + smoke sim) |
| **Standard** | 1→2→3→4→5 | General projects, recommended default | Full (timing + coverage + synth) |
| **Enterprise** | 1→2→3→4→5 | Critical projects, industrial grade | Strict (reviews + formal checks) |

### Mode Selection Guide

- **Quick Mode**: Counters, simple FSMs, small FIFOs, learning/prototyping
- **Standard Mode**: Interface controllers, algorithm modules, general IP
- **Enterprise Mode**: Complex SoCs, critical paths, strict quality gates

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Controller                         │
│                    (Master State Machine)                      │
├─────────────────────────────────────────────────────────────┤
│  Stage 1 (Architect)  │  Stage 3 (Coder)  │ Stage 4 (Debug) │
│  - spec.json          │  - RTL .v files   │ - Error fixes   │
└─────────────────────────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  ACI Tools  │
                    │ - run_lint  │
                    │ - run_sim   │
                    └─────────────┘
```

### Key Components

1. **Python Controller** (`veriflow_ctl.py`)
   - Main orchestrator implementing the state machine
   - Calls LLM workers via subprocess
   - Manages the verification loop

2. **LLM Worker Nodes** (prompts/)
   - `stage1_architect.md` - Generates architecture spec
   - `stage3_coder.md` - Generates Verilog RTL
   - `stage4_debugger.md` - Fixes errors

3. **ACI Tools** (tools/)
   - `run_lint.sh` - Syntax checking with iverilog
   - `run_sim.sh` - Simulation with iverilog + vvp

---

## Command Reference

```bash
# Run the complete pipeline
python veriflow_ctl.py run --mode [quick|standard|enterprise] -d ./project

# Options:
#   --mode      Execution mode (default: quick)
#   -d, --project-dir  Project directory (default: current directory)
```

---

## Project Structure

```
project/
├── requirement.md          # Design requirements (input)
├── .veriflow/
│   ├── project_config.json # Project configuration
│   └── pipeline_state.json # Pipeline state tracking
└── workspace/
    ├── docs/
    │   └── spec.json       # Architecture specification
    ├── rtl/
    │   ├── *.v             # RTL source files
    │   └── tb_*.v          # Testbenches (if generated)
    └── sim/
        └── *.vcd           # Waveform files
```

---

## Requirements

### Software Dependencies
- Python 3.8+
- Icarus Verilog (iverilog + vvp) - for lint and simulation
- Claude CLI (optional, uses mock mode if not available)

### Installation (oss-cad-suite)
```bash
# Download and extract oss-cad-suite for your platform
# https://github.com/YosysHQ/oss-cad-suite-build

# Add to PATH
export PATH="/path/to/oss-cad-suite/bin:$PATH"
```

---

## Update Log

### v8.2.0 (2026-03-23)
- **NEW ARCHITECTURE**: Control Flow Inversion
  - Python script is now the master state machine
  - LLM workers called via subprocess
  - ACI tools for EDA integration
- Simplified prompt set (3 prompts instead of 7)
- New `run` subcommand replaces old `next/validate/complete`
- Direct mode selection via `--mode` flag

---

**Documentation Version**: 8.2.0
**Compatible Controller Version**: >= 8.2.0
