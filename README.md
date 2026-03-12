# VeriFlow-Agent 3.0

Industrial-grade Verilog code generation system with timing and micro-architecture awareness.

[中文文档](verilog_flow/README.md)

---

## Overview

VeriFlow-Agent 3.0 solves the classic Verilog code generation problem: **"Logically correct, physically failing"**. By adopting a "Shift-Left" philosophy, it brings micro-architecture planning and physical timing estimation before code generation, ensuring generated code is not only functionally correct but also meets industrial-grade frequency and resource constraints.

### Key Features

- **5-Stage Pipeline**: Complete workflow from requirements to synthesis verification
- **YAML DSL**: Parameterized timing scenario description with JSON Schema validation
- **Golden Trace**: Cycle-accurate reference waveforms for verification
- **WaveDrom Integration**: Automated waveform diagram generation
- **Skill D Analysis**: Static logic depth and CDC (Clock Domain Crossing) analysis
- **Experience Database**: Learning from past failures and successes
- **KPI Tracking**: Observable metrics (Pass@1, Timing Closure, Token efficiency)
- **Project Layout Management**: Standardized `stage_N_xxx/` directory organization
- **Coding Style System**: Vendor-specific RTL coding rules (generic / Xilinx / Intel)
- **Stage Gate Checker**: Quality gates between pipeline stages
- **Execution Logger**: Structured JSON run logs for traceability
- **Post-Run Analyzer**: Self-evolution via failure pattern detection and regression analysis

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Stage 1 & 1.5: Micro-Architecture Specification            │
│    Pipeline topology, timing budget, interface protocols     │
├──────────────────────────────────────────────────────────────┤
│  Stage 2: Virtual Timing Modeling                            │
│    YAML DSL scenarios, WaveDrom, Golden Trace generation     │
├──────────────────────────────────────────────────────────────┤
│  Stage 3 & 3.5: Code Generation & Static Analysis           │
│    RTL generation, Lint, Skill D, CodingStyle enforcement    │
├──────────────────────────────────────────────────────────────┤
│  Stage 4: Physical Simulation & Verification                 │
│    Testbench execution, waveform diff, assertion checking    │
├──────────────────────────────────────────────────────────────┤
│  Stage 5: Synthesis-Level Verification                       │
│    Yosys synthesis, timing/area estimation, KPI dashboard    │
└──────────────────────────────────────────────────────────────┘

Infrastructure: ProjectLayout · CodingStyleManager · StageGateChecker
                ExecutionLogger · PostRunAnalyzer · ExperienceDB
```

Each stage has explicit input/output contracts and quality gates. If a stage fails its threshold, the flow rolls back automatically.

---

## Installation

### Requirements

- Python 3.9+
- (Optional) [Yosys](https://github.com/YosysHQ/yosys) — for synthesis (Stage 5)
- (Optional) [Icarus Verilog](http://iverilog.icarus.com/) or [Verilator](https://www.veripool.org/verilator/) — for simulation (Stage 4)

### Install from Source

```bash
git clone https://github.com/bjwanneng/Veriflow.git
cd Veriflow/verilog_flow
pip install -e ".[dev]"
```

### Verify Installation

```bash
python -c "from verilog_flow import __version__; print(f'VeriFlow {__version__}')"
```

---

## Quick Start

### Option 1: Run the Example Project

```bash
cd example_project
python run_all.py
```

### Option 2: Initialize a New Project

```bash
# Initialize project directory with standard layout + coding style
verilog-flow init --vendor xilinx

# Run stage gate checks
verilog-flow check

# Run post-execution analysis
verilog-flow analyze --runs 10
```

### Option 3: Use the Python API

```python
from verilog_flow import (
    ProjectLayout, CodingStyleManager, StageGateChecker,
    ExecutionLogger, PostRunAnalyzer,
    RTLCodeGenerator, LintChecker,
)
from pathlib import Path

# Initialize project
layout = ProjectLayout(Path("."))
layout.initialize()

# Load coding style
mgr = CodingStyleManager(layout)
style = mgr.get_style("xilinx")

# Generate RTL with coding style
gen = RTLCodeGenerator(coding_style=style)
module = gen.generate_fifo(depth=16, data_width=32)
module.save(layout.get_dir(3, "rtl"))

# Run stage gate check
checker = StageGateChecker(layout)
for result in checker.check_all():
    print(f"Stage {result.stage}: {'PASS' if result.passed else 'FAIL'}")
```

---

## Standard Project Layout

After `verilog-flow init`, the project directory looks like:

```
project_root/
  .veriflow/                          # Hidden metadata directory
    logs/                             # Structured execution logs (JSON)
    experience_db/                    # Design patterns & failure cases
    coding_style/                     # Verilog coding style rules
      generic/*.md
      xilinx/*.md
      intel/*.md
    templates/                        # RTL code templates (.v per vendor)
      generic/*.v                     # sync_fifo, async_fifo, fsm, ram, etc.
      xilinx/
      intel/
  stage_1_spec/specs/                 # Micro-architecture spec JSON
  stage_2_timing/                     # Virtual timing modeling
    scenarios/                        # YAML scenarios
    golden_traces/                    # Golden reference traces
    waveforms/                        # WaveDrom HTML
  stage_3_codegen/rtl/                # Generated RTL
    common/ crypto/ tx/ rx/
  stage_4_sim/                        # Simulation
    tb/                               # Testbenches
    sim/                              # Simulation outputs
  stage_5_synth/synth/                # Per-module synthesis results
  reports/                            # Cross-stage reports
```

---

## CLI Commands

| Tool | Command | Description |
|------|---------|-------------|
| `verilog-flow` | `init [--vendor V]` | Initialize project directory + coding style |
| `verilog-flow` | `check [--stage N]` | Run stage gate quality checks |
| `verilog-flow` | `analyze [--runs N]` | Post-run analysis for self-evolution |
| `verilog-flow` | `validate` | Validate YAML timing scenario |
| `verilog-flow` | `waveform` | Generate WaveDrom waveform |
| `verilog-flow` | `trace` | Generate Golden Trace |
| `verilog-flow` | `dashboard` | Display KPI dashboard |
| `vf-codegen` | `generate` | Generate RTL from spec |
| `vf-codegen` | `fifo` / `handshake` | Generate standard modules |
| `vf-codegen` | `lint` | Run lint check |
| `vf-sim` | `run` / `diff` / `trace` | Simulation & waveform comparison |
| `vf-synth` | `run` / `analyze` / `report` | Synthesis & timing analysis |

---

## Project Structure

```
Veriflow/
├── README.md                      # This file
├── verilog_flow/                  # Main Python package
│   ├── pyproject.toml             # Package configuration & dependencies
│   ├── README.md                  # Detailed documentation (中文)
│   ├── __init__.py                # Public API exports
│   ├── common/                    # Shared infrastructure
│   │   ├── project_layout.py     # Directory layout management
│   │   ├── coding_style.py       # Coding style rules & manager
│   │   ├── stage_gate.py         # Stage gate quality checker
│   │   ├── execution_log.py      # Structured execution logger
│   │   ├── post_run_analyzer.py  # Post-run self-evolution analysis
│   │   ├── experience_db.py      # Experience database
│   │   ├── kpi.py                # KPI tracking
│   │   └── logger.py             # Logging utilities
│   ├── stage1/                    # Micro-architecture specification
│   ├── stage2/                    # Virtual timing modeling (YAML DSL)
│   ├── stage3/                    # Code generation & static analysis
│   ├── stage4/                    # Simulation & waveform verification
│   ├── stage5/                    # Synthesis & timing/area analysis
│   ├── cli/                       # CLI entry points
│   └── examples/                  # Example YAML scenarios
│   ├── defaults/                  # Package-level defaults (shipped with repo)
│   │   ├── coding_style/         # Coding style docs (.md per vendor)
│   │   └── templates/            # RTL templates (.v per vendor)
├── verilog-flow-skill/            # Claude Code Skill integration
│   └── SKILL.md
└── example_project/               # End-to-end example project
```

---

## Dependencies

Core (auto-installed): `pyyaml`, `jsonschema`, `jinja2`, `click`, `rich`, `pydantic`

Optional groups: `dev` (testing/linting), `docs` (Sphinx), `eda` (cocotb)

---

## License

MIT License
