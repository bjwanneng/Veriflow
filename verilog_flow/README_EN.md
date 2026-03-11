# VeriFlow-Agent 3.0 User Guide

Industrial-grade Verilog code generation system with timing and micro-architecture awareness.

**中文**: [README.md](README.md)

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Five-Stage Workflow](#five-stage-workflow)
- [CLI Command Reference](#cli-command-reference)
- [Python API Usage](#python-api-usage)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)

---

## Overview

VeriFlow-Agent 3.0 addresses the common problem in Verilog code generation: **"Logically correct, physically failing"**. By adopting a "Shift-Left" philosophy, it brings micro-architecture planning and physical timing estimation to the pre-code-generation phase.

### Key Features

- **5-Stage Pipeline**: Complete workflow from requirements to synthesis
- **YAML DSL**: Parameterized timing scenario description
- **Golden Trace**: Cycle-accurate reference for verification
- **WaveDrom Integration**: Automated waveform generation
- **Experience Database**: Learning from failures and successes
- **KPI Tracking**: Observable metrics throughout the flow

---

## Installation

### Requirements

- Python 3.9 or higher
- (Optional) Yosys - for synthesis features
- (Optional) Icarus Verilog or Verilator - for simulation features

### Install from Source

```bash
git clone https://github.com/veriflow/verilog-flow.git
cd verilog-flow
pip install -e ".[dev]"
```

### Verify Installation

```bash
python -c "from verilog_flow import __version__; print(f'VeriFlow {__version__} installed successfully')"
```

---

## Quick Start

### 1. Define a Timing Scenario

Create a YAML file describing your test scenario:

```yaml
# fifo_write_scenario.yaml
scenario: "FIFO_Write_Burst"
description: "Test FIFO write operations with burst transfers"

parameters:
  DEPTH: 4
  DATA_WIDTH: 32

clocks:
  clk:
    period: "5ns"  # 200MHz

phases:
  - name: "Reset_Phase"
    duration_ns: 50
    signals:
      rst_n: 0
      wr_en: 0
      rd_en: 0
    assertions:
      - "full == 0"
      - "empty == 1"

  - name: "Write_Phase"
    duration_ns: 20
    repeat:
      count: "$DEPTH"
      var: "i"
    signals:
      rst_n: 1
      wr_en: 1
      wr_data: "$i * 2"
    assertions:
      - "full == 0 until i == $DEPTH-1"
```

### 2. Validate the Scenario

```bash
python -m verilog_flow.cli.main validate fifo_write_scenario.yaml
```

### 3. Generate Waveform

```bash
python -m verilog_flow.cli.main waveform fifo_write_scenario.yaml --output waveform.html
```

### 4. Generate Golden Trace

```bash
python -m verilog_flow.cli.main trace fifo_write_scenario.yaml --output golden_trace.json
```

---

## Five-Stage Workflow

### Stage 1 & 1.5: Micro-Architecture Specification

Define module micro-architecture specification:

```python
from verilog_flow import SpecGenerator, MicroArchitect

# Use automated architecture design
architect = MicroArchitect()
spec = architect.design_from_requirements(
    module_name="my_fifo",
    requirements={
        "target_frequency_mhz": 200,
        "data_width": 32,
        "fifo_depth": 16,
        "interface_type": "axi4-lite"
    }
)

# Save specification
spec.save("output/")

# View design decisions
print(architect.explain_design(spec))
```

### Stage 2: Virtual Timing Modeling

Parse YAML scenario and generate reference waveforms:

```python
from verilog_flow import parse_yaml_scenario, generate_golden_trace, generate_wavedrom

# Load scenario from YAML
with open("scenario.yaml") as f:
    scenario = parse_yaml_scenario(f.read())

# Generate Golden Trace
trace = generate_golden_trace(scenario)
trace.save("golden_trace.json")

# Generate waveform
html = generate_wavedrom(scenario, output_path="waveform.html")
```

### Stage 3: Code Generation & Static Analysis

Generate RTL code and run static checks:

```bash
# Generate code from specification
python -m verilog_flow.cli.codegen generate spec.json --output rtl/ --lint --analyze

# Generate standard FIFO
python -m verilog_flow.cli.codegen fifo --depth 16 --width 32 --output rtl/

# Generate handshake register
python -m verilog_flow.cli.codegen handshake --width 64 --output rtl/

# Run lint check
python -m verilog_flow.cli.codegen lint rtl/sync_fifo.v
```

### Stage 4: Physical Simulation & Verification

Run simulation and compare against Golden Trace:

```bash
# Generate testbench and run simulation
python -m verilog_flow.cli.simulate run \
    rtl/sync_fifo.v \
    scenario.yaml \
    --top sync_fifo \
    --simulator iverilog \
    --output sim_output/

# Compare waveforms
python -m verilog_flow.cli.simulate diff \
    sim_output/golden_trace.json \
    sim_output/waveform.vcd
```

### Stage 5: Synthesis-Level Verification

Run synthesis and analyze timing/area:

```bash
# Run synthesis
python -m verilog_flow.cli.synthesize run \
    rtl/sync_fifo.v \
    --top sync_fifo \
    --target generic \
    --freq 200 \
    --output synth_output/

# Detailed analysis (timing + area)
python -m verilog_flow.cli.synthesize analyze \
    rtl/sync_fifo.v \
    --top sync_fifo \
    --target ice40 \
    --freq 100
```

---

## CLI Command Reference

### Main Command (verilog-flow)

| Command | Description | Example |
|---------|-------------|---------|
| `validate` | Validate YAML scenario | `verilog-flow validate scenario.yaml` |
| `waveform` | Generate waveform | `verilog-flow waveform scenario.yaml -o wave.html` |
| `trace` | Generate Golden Trace | `verilog-flow trace scenario.yaml -o trace.json` |
| `dashboard` | Display KPI dashboard | `verilog-flow dashboard` |

### Code Generation Command (vf-codegen)

| Command | Description | Example |
|---------|-------------|---------|
| `generate` | Generate RTL from spec | `vf-codegen generate spec.json -o rtl/` |
| `fifo` | Generate FIFO module | `vf-codegen fifo --depth 16 --width 32` |
| `handshake` | Generate handshake register | `vf-codegen handshake --width 64` |
| `lint` | Run lint check | `vf-codegen lint design.v` |

**generate options:**
- `--output, -o`: Output directory
- `--lint/--no-lint`: Run lint check (default: yes)
- `--analyze`: Run logic depth and CDC analysis

### Simulation Command (vf-sim)

| Command | Description | Example |
|---------|-------------|---------|
| `run` | Run simulation | `vf-sim run design.v scenario.yaml -t top` |
| `diff` | Compare waveforms | `vf-sim diff golden.json waveform.vcd` |
| `trace` | Generate Golden Trace | `vf-sim trace scenario.yaml` |

**run options:**
- `--top, -t`: Top module name
- `--simulator, -s`: Simulator choice (iverilog/verilator)
- `--golden-trace`: Golden Trace file path

### Synthesis Command (vf-synth)

| Command | Description | Example |
|---------|-------------|---------|
| `run` | Run synthesis | `vf-synth run design.v -t top -f 200` |
| `analyze` | Detailed analysis | `vf-synth analyze design.v -t top` |
| `report` | Display report | `vf-synth report result.json` |

**run/analyze options:**
- `--top, -t`: Top module name (required)
- `--target`: Target device (generic/ice40/ecp5/xilinx)
- `--freq, -f`: Target frequency (MHz, default: 100)
- `--output, -o`: Output directory

---

## Python API Usage

### Basic Usage

```python
from verilog_flow import (
    RTLCodeGenerator,
    TestbenchGenerator,
    TestbenchConfig,
    SynthesisRunner
)

# Generate FIFO
generator = RTLCodeGenerator()
module = generator.generate_fifo(depth=16, data_width=32)
module.save("output/")

# Generate testbench
config = TestbenchConfig(module_name="sync_fifo")
tb_gen = TestbenchGenerator(config)
tb_code = tb_gen.generate_from_scenario(scenario)

# Run synthesis
runner = SynthesisRunner(output_dir="synth/")
result = runner.run(
    verilog_files=["rtl/sync_fifo.v"],
    top_module="sync_fifo",
    target_frequency_mhz=200
)

print(f"Estimated Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
print(f"Cell count: {result.cell_count}")
```

### Advanced Usage: Custom Code Generation

```python
from verilog_flow import RTLCodeGenerator
from verilog_flow.stage1 import MicroArchSpec

# Load micro-architecture specification
spec = MicroArchSpec.from_file("my_design_spec.json")

# Generate code
generator = RTLCodeGenerator()
module = generator.generate_from_spec(spec)

# View generated code
print(module.verilog_code)

# Get metadata
print(f"Lines of code: {module.lines_of_code}")
print(f"Parameters: {module.parameters}")
print(f"Ports: {module.ports}")
```

### Static Analysis

```python
from verilog_flow import LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth, analyze_cdc

# Lint check
lint_checker = LintChecker()
with open("design.v") as f:
    result = lint_checker.check(f.read(), "design.v")

print(f"Errors: {result.error_count}")
print(f"Warnings: {result.warning_count}")

for issue in result.issues:
    print(f"[{issue.severity}] {issue.rule_id}: {issue.message}")

# Logic depth analysis
depth_result = analyze_logic_depth(verilog_code, target_depth=10)
print(f"Violations: {depth_result['violation_count']}")

# CDC analysis
cdc_result = analyze_cdc(verilog_code)
print(f"Unsafe crossings: {len(cdc_result.unsafe_crossings)}")
```

---

## Advanced Features

### 1. KPI Tracking

```python
from verilog_flow import KPITracker

tracker = KPITracker()

# Start tracking
run = tracker.start_run(
    run_id="run_001",
    module_name="my_fifo",
    target_frequency_mhz=200
)

# Track stages
stage = tracker.start_stage("code_generation")
# ... generate code ...
tracker.end_stage(success=True, token_count=1500)

# End and save
tracker.end_run(
    pass_at_1=True,
    timing_closure=True
)

# View summary
summary = tracker.get_summary(n_runs=10)
print(f"Pass@1 rate: {summary['pass_at_1_rate']*100:.1f}%")
```

### 2. Custom Templates

```python
from verilog_flow.stage3 import TemplateEngine

engine = TemplateEngine()

template = """
module {{ module_name }} (
    input clk,
    input rst_n,
    {% for port in ports %}
    {{ port.direction }} [{{ port.width-1 }}:0] {{ port.name }}{% if not loop.last %},{% endif %}
    {% endfor %}
);
    // Implementation
    {{ implementation }}
endmodule
"""

context = {
    "module_name": "my_module",
    "ports": [
        {"name": "data_in", "direction": "input", "width": 32},
        {"name": "data_out", "direction": "output", "width": 32}
    ],
    "implementation": "// TODO: Add logic"
}

verilog_code = engine.render_string(template, context)
```

---

## Troubleshooting

### Common Issues

#### 1. Import Error

**Problem**: `ModuleNotFoundError: No module named 'verilog_flow'`

**Solution**: Ensure installation in correct directory:

```bash
cd verilog-flow
pip install -e .
python -m verilog_flow.cli.main --help
```

#### 2. Yosys Not Found

**Problem**: `Yosys not found`

**Solution**: Install Yosys:

```bash
# Ubuntu/Debian
sudo apt-get install yosys

# macOS
brew install yosys

# Windows (MSYS2)
pacman -S yosys
```

#### 3. Simulator Not Found

**Problem**: `iverilog: command not found`

**Solution**: Install Icarus Verilog:

```bash
# Ubuntu/Debian
sudo apt-get install iverilog

# macOS
brew install icarus-verilog
```

#### 4. YAML Parse Error

**Problem**: YAML file parsing fails

**Solution**: Check YAML syntax:
- Use correct indentation (spaces, not tabs)
- Ensure quotes are paired
- Escape special characters

#### 5. Waveform Diff Failure

**Problem**: Waveform diff shows many differences

**Solution**:
- Check timing alignment
- Verify signal names
- Adjust tolerance: `WaveformDiffAnalyzer(tolerance_ps=500)`

### Debug Tips

1. **Enable verbose output**: Most commands support `-v` or `--verbose`

2. **Check generated files**:
   ```bash
   # Stage 2
   cat golden_trace.json

   # Stage 3
   cat output/sync_fifo.v

   # Stage 4
   cat sim_output/simulation.log

   # Stage 5
   cat synth_output/synthesis_result.json
   ```

3. **Use Python interactive debugging**:
   ```python
   from verilog_flow import parse_yaml_scenario

   with open("scenario.yaml") as f:
       scenario = parse_yaml_scenario(f.read())

   # Check parsed result
   print(scenario.phases)
   print(scenario.to_dict())
   ```

---

## Project Structure

```
verilog_flow/
├── verilog_flow/                 # Main package
│   ├── __init__.py
│   ├── common/                   # Shared utilities
│   │   ├── kpi.py               # KPI tracking
│   │   ├── experience_db.py     # Experience database
│   │   └── logger.py            # Logging utilities
│   ├── stage1/                  # Micro-architecture spec
│   │   ├── spec_generator.py    # Spec generator
│   │   └── architect.py         # Architecture designer
│   ├── stage2/                  # Virtual timing modeling
│   │   ├── yaml_dsl.py          # YAML DSL parser
│   │   ├── validator.py         # Schema validation
│   │   ├── golden_trace.py      # Trace generation
│   │   └── wavedrom_gen.py      # Waveform generation
│   ├── stage3/                  # Code generation
│   │   ├── code_generator.py    # RTL generator
│   │   ├── lint_checker.py      # Lint checker
│   │   ├── skill_d.py           # Logic depth/CDC analysis
│   │   └── template_engine.py   # Template engine
│   ├── stage4/                  # Simulation
│   │   ├── testbench.py         # Testbench generator
│   │   ├── sim_runner.py        # Simulation runner
│   │   ├── waveform_diff.py     # Waveform comparison
│   │   └── assertion_checker.py # Assertion checker
│   ├── stage5/                  # Synthesis
│   │   ├── synthesis_runner.py  # Synthesis runner
│   │   ├── timing_analyzer.py   # Timing analysis
│   │   ├── area_estimator.py    # Area estimation
│   │   └── yosys_interface.py   # Yosys interface
│   └── cli/                     # Command-line interface
│       ├── main.py              # Main CLI
│       ├── codegen.py           # Code generation CLI
│       ├── simulate.py          # Simulation CLI
│       └── synthesize.py        # Synthesis CLI
├── examples/                     # Example scenarios
├── schemas/                      # JSON schemas
├── templates/                    # Code templates
├── tests/                        # Test suite
└── docs/                         # Documentation
```

---

## Contributing

Contributions are welcome! Please ensure:

1. Code follows PEP 8 style
2. Add appropriate tests
3. Update documentation

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## Contact

- Issues: [GitHub Issues](https://github.com/veriflow/verilog-flow/issues)
- Discussions: [GitHub Discussions](https://github.com/veriflow/verilog-flow/discussions)
- Email: contact@veriflow.dev

---

**VeriFlow-Agent 3.0** - *Shifting-left hardware design, one stage at a time.*
