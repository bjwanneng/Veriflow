# VeriFlow-Agent 3.0 - Quick Start Guide

## Overview

VeriFlow-Agent 3.0 is an industrial-grade Verilog code generation system with timing and micro-architecture awareness.

## Installation

### From Source

```bash
cd verilog-flow
pip install -e ".[dev]"
```

## Quick Demo

### 1. Run the Stage 2 Demo

```bash
python verilog-flow/examples/demo_stage2.py
```

This will demonstrate:
- YAML DSL parsing
- WaveDrom waveform generation
- Golden Trace generation

### 2. Use the CLI

```bash
# Validate a YAML scenario
verilog-flow validate examples/fifo_write_scenario.yaml

# Generate waveform
verilog-flow waveform examples/fifo_write_scenario.yaml --output wave.html

# Generate golden trace
verilog-flow trace examples/fifo_write_scenario.yaml --output trace.json
```

### 3. Python API Usage

```python
from verilog_flow.stage2 import parse_yaml_scenario, validate_scenario
from verilog_flow.stage2 import generate_wavedrom, generate_golden_trace

# Parse YAML
with open("scenario.yaml") as f:
    scenario = parse_yaml_scenario(f.read())

# Validate
result = validate_scenario(scenario.to_dict())
print(f"Valid: {result.valid}")

# Generate waveform
html = generate_wavedrom(scenario, output_path="wave.html")

# Generate golden trace
trace = generate_golden_trace(scenario)
trace.save("trace.json")
```

## Project Structure

```
verilog-flow/
├── verilog_flow/           # Main package
│   ├── stage1/            # Micro-architecture specification
│   ├── stage2/            # Virtual timing modeling (YAML DSL)
│   ├── stage3/            # Code generation
│   ├── stage4/            # Simulation
│   ├── stage5/            # Synthesis
│   ├── common/            # Shared utilities
│   └── cli/               # Command-line interface
├── examples/               # Example scenarios
├── tests/                  # Test suite
└── docs/                   # Documentation
```

## Next Steps

1. Read the [full documentation](docs/)
2. Explore the [examples](examples/)
3. Try implementing a simple module (e.g., FIFO, AXI Slave)
4. Review the [YAML DSL specification](docs/yaml-dsl.md)

## Support

- Issues: [GitHub Issues](https://github.com/veriflow/verilog-flow/issues)
- Discussions: [GitHub Discussions](https://github.com/veriflow/verilog-flow/discussions)

---

**VeriFlow-Agent 3.0** - *Shifting-left hardware design, one stage at a time.*
