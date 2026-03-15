# VeriFlow-Agent 3.0 User Guide

An industrial-grade Verilog code generation system with timing and micro-architecture awareness.

---

## Overview

VeriFlow-Agent 3.0 addresses a common problem in Verilog code generation: **"logically correct, physically failed"**. Through a "shift-left" philosophy, it moves micro-architecture planning and physical timing estimation ahead of code generation.

### Core Features

- **5-Stage Pipeline**: Complete workflow from requirements to synthesis
- **YAML DSL**: Parameterized timing scenario descriptions
- **Golden Trace**: Cycle-accurate references for verification
- **WaveDrom Integration**: Automatic waveform diagram generation
- **Experience Database**: Learning from failures and successes
- **KPI Tracking**: Observable metrics throughout the flow
- **Standard Directory Layout**: `stage_N_xxx/` unified output organization
- **Coding Style System**: Vendor-specific RTL coding standards (generic / Xilinx / Intel)
- **Stage Gate Checks**: Quality gates between stages
- **Structured Execution Logs**: JSON-formatted run logs
- **Post-Run Analysis**: Self-evolution capability (failure mode detection, performance regression analysis)

---

## Installation

```bash
git clone https://github.com/bjwanneng/Veriflow.git
cd Veriflow/verilog_flow
pip install -e ".[dev]"
```

Optional dependencies: Yosys (synthesis), Icarus Verilog / Verilator (simulation)

---

## Quick Start

### Initialize a Project

```bash
# Initialize standard directory structure + coding style
verilog-flow init --vendor xilinx

# Run gate checks
verilog-flow check

# Run post-run analysis
verilog-flow analyze --runs 10
```

### Python API

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

# Gate checks
checker = StageGateChecker(layout)
for r in checker.check_all():
    print(f"Stage {r.stage}: {'PASS' if r.passed else 'FAIL'}")

# Execution logging
logger = ExecutionLogger(layout)
run = logger.start_run("my_project")
with logger.stage(3, "codegen") as slog:
    slog.metrics["files"] = 1
logger.end_run(success=True)

# Post-run analysis
analyzer = PostRunAnalyzer(layout)
report = analyzer.analyze(n_recent=10)
for ins in report.insights:
    print(f"[{ins.severity}] {ins.message}")
```

---

## Standard Directory Layout

Project structure after `verilog-flow init`:

```
project_root/
  .veriflow/                          # Hidden metadata directory
    logs/                             # Structured execution logs
    experience_db/                    # Design patterns & failure cases
    coding_style/                     # Verilog coding style standards
      generic/*.md
      xilinx/*.md
      intel/*.md
    templates/                        # RTL code templates (.v files, organized by vendor)
      generic/*.v                     # sync_fifo, async_fifo, fsm, ram, etc.
  stage_1_spec/specs/                 # Micro-architecture specification JSON
  stage_2_timing/                     # Virtual timing modeling
    scenarios/                        # YAML scenarios
    golden_traces/                    # Golden references
    waveforms/                        # Waveform HTML
  stage_3_codegen/rtl/                # Generated RTL
    common/ crypto/ tx/ rx/
  stage_4_sim/                        # Simulation verification
    tb/                               # Testbench
    sim/                              # Simulation output
  stage_5_synth/synth/                # Synthesis results
  reports/                            # Cross-stage reports
```

---

## Five-Stage Workflow

### Stage 1: Micro-Architecture Specification

```python
from verilog_flow import MicroArchitect

architect = MicroArchitect()
spec = architect.design_from_requirements("my_fifo", {
    "target_frequency_mhz": 200,
    "data_width": 32,
    "fifo_depth": 16,
})
spec.save(layout.get_dir(1, "specs"))
```

### Stage 2: Virtual Timing Modeling

```bash
verilog-flow validate scenario.yaml
verilog-flow waveform scenario.yaml -o waveform.html
verilog-flow trace scenario.yaml -o golden_trace.json
```

### Stage 3: Code Generation and Static Analysis

```bash
vf-codegen fifo --depth 16 --width 32 --output rtl/
vf-codegen lint rtl/sync_fifo.v
```

### Stage 4: Simulation Verification

```bash
vf-sim run rtl/sync_fifo.v scenario.yaml --top sync_fifo --simulator iverilog
vf-sim diff golden.json waveform.vcd
```

### Stage 5: Synthesis Verification

```bash
vf-synth run rtl/sync_fifo.v --top sync_fifo --freq 200
```

---

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `verilog-flow init [--vendor V]` | Initialize project directory + coding style |
| `verilog-flow check [--stage N]` | Run gate checks |
| `verilog-flow analyze [--runs N]` | Post-run analysis |
| `verilog-flow validate` | Validate YAML scenarios |
| `verilog-flow waveform` | Generate waveform diagrams |
| `verilog-flow trace` | Generate Golden Trace |
| `verilog-flow dashboard` | Display KPI dashboard |
| `vf-codegen generate` | Generate RTL from specification |
| `vf-codegen fifo / handshake` | Generate standard modules |
| `vf-codegen lint` | Run lint checks |
| `vf-sim run / diff / trace` | Simulation and waveform comparison |
| `vf-synth run / analyze / report` | Synthesis and timing analysis |

---

## Coding Style System

Three built-in coding standards:

| Vendor | Reset Style | Indentation | Characteristics |
|--------|-------------|-------------|-----------------|
| `generic` | async active-low | 4 spaces | General Verilog-2005 |
| `xilinx` | sync active-high | 4 spaces | UG901 recommended, BRAM/DSP inference |
| `intel` | async active-low | 3 spaces | Intel FPGA recommended |

```python
mgr = CodingStyleManager(layout)
mgr.initialize_defaults()  # Copy default .md and .v files to project
style = mgr.get_style("xilinx")

# Get coding standard documentation (Markdown)
doc = mgr.get_style_doc("xilinx")

# Get templates
tpl = mgr.get_template("template_sync_fifo", "generic")
templates = mgr.list_templates("generic")

# Validate code style
issues = mgr.validate_code(verilog_code, style)
```

---

## Project Structure

```
verilog_flow/
├── __init__.py                # Public API exports
├── common/                    # Shared infrastructure
│   ├── project_layout.py     # Directory layout management
│   ├── coding_style.py       # Coding standard management
│   ├── stage_gate.py         # Stage gate checks
│   ├── execution_log.py      # Structured execution logs
│   ├── post_run_analyzer.py  # Post-run analysis
│   ├── experience_db.py      # Experience database
│   ├── kpi.py                # KPI tracking
│   └── logger.py             # Logging utilities
├── defaults/                  # Package-level default resources (shipped with repo)
│   ├── coding_style/         # Coding standard documents (.md, organized by vendor)
│   └── templates/            # RTL templates (.v, organized by vendor)
├── stage1/                    # Micro-architecture specification
├── stage2/                    # Virtual timing modeling
├── stage3/                    # Code generation and static analysis
├── stage4/                    # Simulation verification
├── stage5/                    # Synthesis analysis
├── cli/                       # Command-line interface
└── examples/                  # Example scenarios
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'verilog_flow'` | `cd verilog_flow && pip install -e .` |
| `Yosys not found` | Install Yosys (only required for Stage 5) |
| `iverilog: command not found` | Install Icarus Verilog (only required for Stage 4) |

---

## License

MIT License
