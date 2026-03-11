---
name: verilog-flow-skill
description: Industrial-grade Verilog code generation system with timing and micro-architecture awareness. Generates RTL code from YAML timing scenarios, runs lint checks, simulates with golden trace verification, and performs synthesis analysis. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when the user mentions Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "3.0.0"
  category: hardware-design
---

# VeriFlow-Agent 3.0

Industrial-grade Verilog code generation system with timing and micro-architecture awareness.

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

## Quick Start

### 1. Define a Timing Scenario (YAML)

Create a YAML file describing your test scenario:

```yaml
# scenario.yaml
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
python -m verilog_flow.cli.main validate scenario.yaml
```

### 3. Generate Waveform

```bash
python -m verilog_flow.cli.main waveform scenario.yaml --output waveform.html
```

### 4. Generate RTL Code

```bash
# Generate a FIFO module
python -m verilog_flow.cli.codegen fifo --depth 16 --width 32 --output rtl/

# Or generate from specification
python -m verilog_flow.cli.codegen generate spec.json --output rtl/ --lint
```

### 5. Run Lint Checks

```bash
python -m verilog_flow.cli.codegen lint rtl/sync_fifo.v
```

### 6. Run Simulation

```bash
python -m verilog_flow.cli.simulate run \
    rtl/sync_fifo.v \
    scenario.yaml \
    --top sync_fifo \
    --simulator iverilog \
    --output sim_output/
```

### 7. Run Synthesis

```bash
python -m verilog_flow.cli.synthesize run \
    rtl/sync_fifo.v \
    --top sync_fifo \
    --target generic \
    --freq 200 \
    --output synth_output/
```

## Five-Stage Workflow

### Stage 1 & 1.5: Micro-Architecture Specification

Define module micro-architecture specification:

```python
from verilog_flow import MicroArchitect

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

spec.save("output/")
print(architect.explain_design(spec))
```

### Stage 2: Virtual Timing Modeling

Parse YAML scenario and generate reference waveforms:

```python
from verilog_flow import parse_yaml_scenario, generate_golden_trace, generate_wavedrom

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

```python
from verilog_flow import RTLCodeGenerator, LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth, analyze_cdc

# Generate code
generator = RTLCodeGenerator()
module = generator.generate_fifo(depth=16, data_width=32)
module.save("output/")

# Lint check
lint_checker = LintChecker()
result = lint_checker.check(module.verilog_code, "sync_fifo.v")

# Logic depth analysis
depth_result = analyze_logic_depth(module.verilog_code, target_depth=10)

# CDC analysis
cdc_result = analyze_cdc(module.verilog_code)
```

### Stage 4: Physical Simulation & Verification

Run simulation and compare against Golden Trace:

```python
from verilog_flow import TestbenchGenerator, TestbenchConfig
from verilog_flow import SimulationRunner, WaveformDiffAnalyzer

# Generate testbench
config = TestbenchConfig(module_name="sync_fifo")
tb_gen = TestbenchGenerator(config)
tb_code = tb_gen.generate_from_scenario(scenario)

# Run simulation
runner = SimulationRunner(simulator="iverilog", output_dir="sim_output")
result = runner.run(
    design_files=["rtl/sync_fifo.v"],
    testbench_file="sim_output/tb_sync_fifo.sv",
    top_module="tb_sync_fifo"
)

# Compare waveforms
analyzer = WaveformDiffAnalyzer()
diff_result = analyzer.compare(golden_trace, Path("sim_output/waveform.vcd"))
```

### Stage 5: Synthesis-Level Verification

Run synthesis and analyze timing/area:

```python
from verilog_flow import SynthesisRunner, TimingAnalyzer, AreaEstimator

# Run synthesis
runner = SynthesisRunner(output_dir="synth_output")
result = runner.run(
    verilog_files=["rtl/sync_fifo.v"],
    top_module="sync_fifo",
    target_frequency_mhz=200
)

print(f"Estimated Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
print(f"Cell count: {result.cell_count}")
print(f"Timing met: {result.timing_met}")
```

## CLI Command Reference

### Main Commands (verilog-flow)

| Command | Description | Example |
|---------|-------------|---------|
| `validate` | Validate YAML scenario | `verilog-flow validate scenario.yaml` |
| `waveform` | Generate waveform | `verilog-flow waveform scenario.yaml -o wave.html` |
| `trace` | Generate Golden Trace | `verilog-flow trace scenario.yaml -o trace.json` |
| `dashboard` | Display KPI dashboard | `verilog-flow dashboard` |

### Code Generation (vf-codegen)

| Command | Description | Example |
|---------|-------------|---------|
| `generate` | Generate RTL from spec | `vf-codegen generate spec.json -o rtl/` |
| `fifo` | Generate FIFO module | `vf-codegen fifo --depth 16 --width 32` |
| `handshake` | Generate handshake register | `vf-codegen handshake --width 64` |
| `lint` | Run lint check | `vf-codegen lint design.v` |

### Simulation (vf-sim)

| Command | Description | Example |
|---------|-------------|---------|
| `run` | Run simulation | `vf-sim run design.v scenario.yaml -t top` |
| `diff` | Compare waveforms | `vf-sim diff golden.json waveform.vcd` |
| `trace` | Generate Golden Trace | `vf-sim trace scenario.yaml` |

### Synthesis (vf-synth)

| Command | Description | Example |
|---------|-------------|---------|
| `run` | Run synthesis | `vf-synth run design.v -t top -f 200` |
| `analyze` | Detailed analysis | `vf-synth analyze design.v -t top` |
| `report` | Display report | `vf-synth report result.json` |

## YAML DSL Specification

### Complete Example

```yaml
scenario: "Complete_Test"
description: "A comprehensive test scenario"

parameters:
  DATA_WIDTH: 32
  ADDR_WIDTH: 8
  DEPTH: 16

clocks:
  clk:
    period: "5ns"
    duty_cycle: 50
    jitter_ps: 100

phases:
  - name: "Reset"
    duration_ns: 100
    description: "Initial reset phase"
    signals:
      rst_n: 0
      wr_en: 0
      rd_en: 0
    assertions:
      - expression: "empty == 1"
        severity: "error"

  - name: "Write_Burst"
    duration_ns: 80
    repeat:
      count: "$DEPTH"
      var: "i"
    signals:
      rst_n: 1
      wr_en: 1
      wr_data: "$i * 4 + 16"
    assertions:
      - expression: "full == 0 until i == $DEPTH-1"
        type: "delayed"

global_assertions:
  - expression: "!(full && empty)"
    description: "FIFO cannot be full and empty simultaneously"
    severity: "error"
```

### Signal Value Expressions

| Syntax | Description | Example |
|--------|-------------|---------|
| Constant | Direct value | `wr_data: 42` |
| Variable | `$var` | `wr_data: "$i * 2"` |
| Binary | `0b` prefix | `mode: 0b1010` |
| Hexadecimal | `0x` prefix | `addr: 0xFF00` |

### Assertion Types

| Type | Description | Use Case |
|------|-------------|----------|
| `immediate` | Immediate check | Combinational logic |
| `delayed` | Delayed check | Sequential logic |
| `eventual` | Eventually true | Verify event happens |
| `never` | Must never happen | Verify condition never occurs |

## Troubleshooting

### Import Error

**Problem**: `ModuleNotFoundError: No module named 'verilog_flow'`

**Solution**: Install from source:
```bash
cd verilog-flow
pip install -e .
```

### Yosys Not Found

**Problem**: `Yosys not found`

**Solution**: Install Yosys:
```bash
# Ubuntu/Debian
sudo apt-get install yosys

# macOS
brew install yosys
```

### Simulator Not Found

**Problem**: `iverilog: command not found`

**Solution**: Install Icarus Verilog:
```bash
# Ubuntu/Debian
sudo apt-get install iverilog

# macOS
brew install icarus-verilog
```

## References

- [README.md](README.md) - Full documentation
- [README_EN.md](README_EN.md) - English documentation
- [examples/](examples/) - Example scenarios

## License

MIT License - See [LICENSE](LICENSE) file for details.
