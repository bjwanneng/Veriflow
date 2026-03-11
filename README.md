# VeriFlow-Agent 3.0

Industrial-grade Verilog code generation system with timing and micro-architecture awareness.

[中文文档](verilog_flow/README.md) | [English Documentation](verilog_flow/README_EN.md) | [Tutorial](verilog_flow/TUTORIAL.md)

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
- **KPI Tracking**: Observable metrics (Pass@1, Timing Closure, Token efficiency) throughout the flow

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
│    RTL generation, Lint, Skill D (logic depth / CDC)         │
├──────────────────────────────────────────────────────────────┤
│  Stage 4: Physical Simulation & Verification                 │
│    Testbench execution, waveform diff, assertion checking    │
├──────────────────────────────────────────────────────────────┤
│  Stage 5: Synthesis-Level Verification                       │
│    Yosys synthesis, timing/area estimation, KPI dashboard    │
└──────────────────────────────────────────────────────────────┘
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
python -c "from verilog_flow import __version__; print(f'VeriFlow {__version__} installed')"
```

---

## Quick Start

### Option 1: Run the Example Project (Recommended)

```bash
cd example_project

# Run all steps at once
python run_all.py

# Or step by step
python 01_define_spec.py       # Define architecture
python 02_generate_rtl.py      # Generate RTL code
python 03_run_simulation.py    # Run simulation
python 04_run_synthesis.py     # Run synthesis
```

### Option 2: Use the CLI

```bash
cd verilog_flow && pip install -e .

# Generate a FIFO module
vf-codegen fifo --depth 16 --width 32 --output rtl/

# Validate a YAML timing scenario
verilog-flow validate scenario.yaml

# Run simulation
vf-sim run rtl/sync_fifo.v scenario.yaml --top sync_fifo --simulator iverilog

# Run synthesis
vf-synth run rtl/sync_fifo.v --top sync_fifo --freq 200
```

### Option 3: Use the Python API

```python
from verilog_flow import RTLCodeGenerator, LintChecker

# Generate FIFO
generator = RTLCodeGenerator()
module = generator.generate_fifo(depth=16, data_width=32)
module.save("rtl/")

# Lint check
checker = LintChecker()
result = checker.check(module.verilog_code, "sync_fifo.v")
print(f"Errors: {result.error_count}, Warnings: {result.warning_count}")
```

---

## Project Structure

```
Veriflow/
├── README.md                      # This file
├── QUICKSTART.md                  # Quick start guide (中文)
│
├── verilog_flow/                  # Main Python package
│   ├── pyproject.toml             # Package configuration & dependencies
│   ├── README.md                  # Detailed documentation (中文)
│   ├── README_EN.md               # Detailed documentation (English)
│   ├── TUTORIAL.md                # Full workflow tutorial
│   ├── QUICKSTART.md              # Package-level quick start
│   ├── __init__.py                # Public API exports
│   ├── common/                    # Shared utilities (KPI, experience DB, logger)
│   ├── stage1/                    # Micro-architecture specification
│   ├── stage2/                    # Virtual timing modeling (YAML DSL, Golden Trace)
│   ├── stage3/                    # Code generation & static analysis (Lint, Skill D)
│   ├── stage4/                    # Simulation & waveform verification
│   ├── stage5/                    # Synthesis & timing/area analysis
│   ├── cli/                       # CLI entry points (main, codegen, simulate, synthesize)
│   └── examples/                  # Example YAML scenarios
│
├── verilog-flow-skill/            # Claude Code Skill integration
│   └── SKILL.md                   # Skill definition for AI-assisted workflows
│
├── example_project/               # End-to-end example project
│   ├── run_all.py                 # One-click full workflow runner
│   ├── requirements.json          # Sample project requirements
│   ├── 01_define_spec.py          # Step 1: Architecture definition
│   ├── 02_generate_rtl.py         # Step 2: RTL generation
│   ├── 03_run_simulation.py       # Step 3: Simulation
│   └── 04_run_synthesis.py        # Step 4: Synthesis
│
└── request.md                     # Original design specification
```

---

## CLI Commands

| Tool | Command | Description |
|------|---------|-------------|
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

## Dependencies

Core dependencies (auto-installed):

- `pyyaml` >= 6.0
- `jsonschema` >= 4.0
- `jinja2` >= 3.0
- `click` >= 8.0
- `rich` >= 13.0
- `pydantic` >= 2.0

Optional groups: `dev` (testing/linting), `docs` (Sphinx), `eda` (cocotb).

---

## Documentation

| Document | Description |
|----------|-------------|
| [QUICKSTART.md](QUICKSTART.md) | Quick start guide (中文) |
| [verilog_flow/README.md](verilog_flow/README.md) | Full documentation (中文) |
| [verilog_flow/README_EN.md](verilog_flow/README_EN.md) | Full documentation (English) |
| [verilog_flow/TUTORIAL.md](verilog_flow/TUTORIAL.md) | Step-by-step tutorial with AXI4 DMA example |
| [example_project/README.md](example_project/README.md) | Example project guide |
| [request.md](request.md) | Original VeriFlow-Agent 3.0 design specification |

---

## License

MIT License

---

## Contributing

Contributions welcome! Please ensure code follows PEP 8, includes tests, and updates documentation.

- Issues: [GitHub Issues](https://github.com/bjwanneng/Veriflow/issues)
- Pull Requests: [GitHub PRs](https://github.com/bjwanneng/Veriflow/pulls)
