---
name: verilog-flow-skill
description: Industrial-grade Verilog code generation system with timing and micro-architecture awareness. Generates RTL code from YAML timing scenarios, runs lint checks, simulates with golden trace verification, and performs synthesis analysis. Includes project layout management, vendor-specific coding styles, stage gate quality checks, structured execution logging, and post-run self-evolution analysis. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when the user mentions Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "3.1.0"
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

### Stage 3: Code Generation with Coding Style

```python
from verilog_flow import RTLCodeGenerator, ProjectLayout, CodingStyleManager
from pathlib import Path

layout = ProjectLayout(Path("."))
style = CodingStyleManager(layout).get_style("xilinx")
generator = RTLCodeGenerator(coding_style=style)
module = generator.generate_fifo(depth=16, data_width=32)
module.save(layout.get_dir(3, "rtl"))
```

### Stage 4: Physical Simulation & Verification

```python
from verilog_flow import TestbenchGenerator, TestbenchConfig, SimulationRunner
config = TestbenchConfig(module_name="sync_fifo")
tb_gen = TestbenchGenerator(config)
runner = SimulationRunner(simulator="iverilog", output_dir="sim_output")
result = runner.run(design_files=["rtl/sync_fifo.v"],
                    testbench_file="tb.sv", top_module="tb_sync_fifo")
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

Built-in presets: `generic` (async active-low, 4-space), `xilinx` (sync active-high, UG901), `intel` (async active-low, 3-space).

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

### StageGateChecker — Quality Gates

```python
from verilog_flow import StageGateChecker
checker = StageGateChecker(layout)
results = checker.check_all()
result = checker.check_transition(3, 4)  # Can we move from stage 3 to 4?
```

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

## Troubleshooting

### Import Error
```bash
cd verilog_flow && pip install -e .
```

### Yosys / Simulator Not Found
Install Yosys (`apt install yosys` / `brew install yosys`) or Icarus Verilog (`apt install iverilog`).

## License

MIT License
