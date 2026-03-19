# Stage 2: Virtual Timing Modeling

You are a Verilog RTL design agent. Your task is to create timing scenarios, golden traces, AND Cocotb test files.

## Working Directory
{{PROJECT_DIR}}

## Spec JSON
{{SPEC_JSON}}

## Tasks

### 1. Read Specification JSON

Read the specification JSON file from `stage_1_spec/specs/`.

### 2. Create YAML Timing Scenarios

Create YAML timing scenarios in `stage_2_timing/scenarios/`. Create at least the following scenarios:
- `reset_sequence.yaml` — Reset behavior, initialization sequence
- `single_operation.yaml` — Single block operation using standard test vectors
- `back_to_back.yaml` — Continuous blocks, varying data patterns
- `config_mode.yaml` — Configuration sequence (if applicable)
- `random_stall.yaml` — (Boundary condition) Backpressure from downstream random ready deassertion
- `input_bubble.yaml` — (Boundary condition) Upstream intermittent data with valid toggling

Each YAML file follows this structure, with critical path estimation at the header.
**IMPORTANT**: Read `.veriflow/project_config.json` `coding_style.reset_signal` and `coding_style.reset_type` to determine the correct reset signal name and polarity. The examples below use `rst_n` (async active-low) as default — adapt to match your project config (e.g., use `rst` with active-high polarity if configured).
```yaml
scenario: <name>
description: <what_this_tests>
critical_path_hint: "expected_max_logic_level_description"
clocks:
  clk: {period_ns: 3.33}
phases:
  - name: reset
    duration_cycles: 5
    signals:
      rst_n: 0
      i_valid: 0
    assertions:
      o_valid: 0
  - name: drive_input
    duration_cycles: 1
    signals:
      rst_n: 1
      i_valid: 1
      i_data: "32'h12345678"
      i_cfg: "8'h00"
  - name: wait_pipeline
    duration_cycles: 5
    signals:
      i_valid: 0
    assertions:
      o_valid: {at_cycle: 5, value: 1}
      o_data: {at_cycle: 5, value: "32'h87654321"}
```

### 3. Generate Golden Trace JSON

Generate golden trace JSON files in `stage_2_timing/golden_traces/`:
- For each scenario, create `<scenario_name>_trace.json` containing expected signal values per cycle
- Include standard test vectors from the design requirements

### 4. Generate Cocotb Test Files (NEW)

Generate Cocotb Python test files in `stage_2_timing/cocotb/` directory:

#### 4.1 Generate Unit Tests for Each Module

For each module in spec JSON, create `test_<module_name>.py`.
**IMPORTANT**: Use the reset signal name from project config (`coding_style.reset_signal`). Examples below use `rst_n` — adapt accordingly.

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer
from cocotb.types import LogicArray

async def reset_dut(dut, reset_n: str = "rst_n", clock: str = "clk"):
    """Reset DUT"""
    getattr(dut, reset_n).value = 0
    await Timer(50, units="ns")
    getattr(dut, reset_n).value = 1
    await Timer(50, units="ns")

@cocotb.test()
async def test_basic_reset(dut):
    """Test basic reset behavior"""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    # Check post-reset state
    # ... add checks ...

    dut._log.info("Reset test passed!")
```

#### 4.2 Generate Integration Tests

Create `test_integration.py` with complete design integration tests:

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray

# ── Golden Model ──────────────────────────────────────────────────────────
# Cycle-accurate reference model. Must mirror the RTL pipeline structure.
PIPELINE_DEPTH = 3  # Adjust to match spec timing_contracts.latency_cycles

class GoldenModel:
    """Cycle-accurate golden reference for pipeline/FSM designs."""

    def __init__(self):
        self.pipeline = [None] * PIPELINE_DEPTH
        self.pipeline_valid = [False] * PIPELINE_DEPTH
        self.output_data = 0
        self.output_valid = False

    def reset(self):
        """Clear all pipeline state."""
        self.pipeline = [None] * PIPELINE_DEPTH
        self.pipeline_valid = [False] * PIPELINE_DEPTH
        self.output_data = 0
        self.output_valid = False

    def tick(self, i_valid, i_data, o_ready=True):
        """Advance one clock cycle. Returns expected output signals dict."""
        if o_ready:
            # Shift pipeline: last stage -> output
            self.output_valid = self.pipeline_valid[-1]
            self.output_data = self._compute(self.pipeline[-1]) if self.pipeline_valid[-1] else 0
            # Shift stages
            for i in range(PIPELINE_DEPTH - 1, 0, -1):
                self.pipeline[i] = self.pipeline[i - 1]
                self.pipeline_valid[i] = self.pipeline_valid[i - 1]
            # Capture input
            self.pipeline[0] = i_data if i_valid else None
            self.pipeline_valid[0] = bool(i_valid)
        # When stalled (o_ready==0), all registers hold
        return {
            "o_valid": int(self.output_valid),
            "o_data": self.output_data,
            "i_ready": int(o_ready),
        }

    def _compute(self, data):
        """Core computation — MUST implement the actual algorithm from spec."""
        if data is None:
            return 0
        # ... fill in the real algorithm here ...
        return data

# ── Timing Checker ────────────────────────────────────────────────────────
class TimingChecker:
    """Cycle-by-cycle comparison of DUT outputs vs GoldenModel."""

    def __init__(self, golden: GoldenModel):
        self.golden = golden
        self.cycle = 0
        self.mismatches = []

    def check(self, dut_signals: dict, expected: dict):
        """Compare DUT signals against golden model for current cycle."""
        for sig_name, exp_val in expected.items():
            dut_val = dut_signals.get(sig_name)
            if dut_val is not None and int(dut_val) != int(exp_val):
                self.mismatches.append({
                    "cycle": self.cycle,
                    "signal": sig_name,
                    "expected": int(exp_val),
                    "actual": int(dut_val),
                    "error_type": "value_mismatch",
                })
        self.cycle += 1

    def report(self):
        """Return structured timing diff report."""
        return {
            "total_cycles": self.cycle,
            "mismatch_count": len(self.mismatches),
            "mismatches": self.mismatches,
            "pass": len(self.mismatches) == 0,
        }

# Standard test vectors
TEST_VECTOR_INPUT = 0x12345678
golden = GoldenModel()
golden.reset()
# Pre-compute expected output
for _ in range(PIPELINE_DEPTH):
    golden.tick(0, 0)
golden.tick(1, TEST_VECTOR_INPUT)
for _ in range(PIPELINE_DEPTH - 1):
    golden.tick(0, 0)
TEST_VECTOR_EXPECTED = golden.output_data
golden.reset()


async def reset_dut(dut):
    dut.rst_n.value = 0
    await Timer(50, units="ns")
    dut.rst_n.value = 1
    await Timer(50, units="ns")

@cocotb.test()
async def test_basic_operation(dut):
    """Test basic operation with GoldenModel cycle-by-cycle comparison."""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    gm = GoldenModel()
    gm.reset()
    tc = TimingChecker(gm)

    # Drive input
    dut.i_data.value = TEST_VECTOR_INPUT
    dut.i_valid.value = 1
    expected = gm.tick(1, TEST_VECTOR_INPUT)
    await RisingEdge(dut.clk)

    dut_signals = {"o_valid": dut.o_valid.value, "o_data": dut.o_data.value}
    tc.check(dut_signals, expected)

    dut.i_valid.value = 0

    # Wait for pipeline flush
    for _ in range(PIPELINE_DEPTH):
        expected = gm.tick(0, 0)
        await RisingEdge(dut.clk)
        dut_signals = {"o_valid": dut.o_valid.value, "o_data": dut.o_data.value}
        tc.check(dut_signals, expected)

    report = tc.report()
    assert report["pass"], f"Timing mismatches: {report['mismatches']}"
    dut._log.info("Basic operation test passed with cycle-accurate golden model check!")

@cocotb.test()
async def test_back_to_back(dut):
    """Test continuous input throughput with golden model."""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())

    await reset_dut(dut)

    gm = GoldenModel()
    gm.reset()
    tc = TimingChecker(gm)

    # Continuous input of two blocks
    dut.i_data.value = TEST_VECTOR_INPUT
    dut.i_valid.value = 1
    expected = gm.tick(1, TEST_VECTOR_INPUT)
    await RisingEdge(dut.clk)
    tc.check({"o_valid": dut.o_valid.value, "o_data": dut.o_data.value}, expected)

    # Second block
    dut.i_data.value = TEST_VECTOR_INPUT ^ 0xFFFFFFFF
    expected = gm.tick(1, TEST_VECTOR_INPUT ^ 0xFFFFFFFF)
    await RisingEdge(dut.clk)
    tc.check({"o_valid": dut.o_valid.value, "o_data": dut.o_data.value}, expected)

    dut.i_valid.value = 0

    for _ in range(PIPELINE_DEPTH + 1):
        expected = gm.tick(0, 0)
        await RisingEdge(dut.clk)
        tc.check({"o_valid": dut.o_valid.value, "o_data": dut.o_data.value}, expected)

    report = tc.report()
    assert report["pass"], f"Timing mismatches: {report['mismatches']}"
    dut._log.info("Back-to-back test passed!")
```

#### 4.3 Generate Makefile

Create Makefile in `stage_2_timing/cocotb/`:

```makefile
# Cocotb Makefile for Design Verification
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../stage_3_codegen/rtl/*.v

TOPLEVEL := <top_module_name>
MODULE := test_integration

include $(shell cocotb-config --makefiles)/Makefile.sim

# Run single test
test_%:
	MODULE=test_$* make

# Run all tests
.PHONY: all
all:
	@echo "Running all Cocotb tests..."
	MODULE=test_integration make

.PHONY: clean
clean::
	rm -rf sim_build __pycache__ *.vcd *.log
```

### 5. Generate WaveDrom Timing Diagram (Optional)

Create WaveDrom format timing diagram HTML or JSON files in `stage_2_timing/waveforms/` directory.

## Constraints
- Do NOT create any .v files in this stage
- YAML must be valid (parseable by PyYAML)
- All hex values must use Verilog notation: `32'hXXXX`
- Include assertions for expected output values
- Every scenario must have a reset phase first
- Each boundary condition scenario must verify handshake protocol (ready-valid or stall/flush behavior)
- Cocotb tests must be valid Python
- Must include standard test vectors in Cocotb tests
- (Very important) In Cocotb `test_integration.py`, must include a Python `GoldenModel` class with `tick()` and `reset()` methods that model the pipeline cycle-by-cycle
- (Very important) Must include a `TimingChecker` class (or equivalent) that compares DUT outputs against GoldenModel on every cycle and records mismatches with cycle number, signal name, expected/actual values
- Generate `timing_assertions.py` alongside `test_integration.py` containing the `TimingChecker` class if it is not embedded in `test_integration.py`

## Output
Print: number of scenarios created, golden traces generated, Cocotb test files created, and test vectors included.

### After Validation: Confirm to Proceed

After running `validate` and validation passes, read and check the project config:

1. Read `.veriflow/project_config.json` and check the value of `confirm_after_validate`
2. If `confirm_after_validate` is true (or the field doesn't exist):
   - Print a summary of what was accomplished in this stage to the user
   - Use AskUserQuestion tool to ask for confirmation before proceeding to `complete`
   - Question: "Stage 2 validation passed! Do you want to proceed to mark this stage complete?"
   - Options: ["Proceed to complete this stage", "Wait, I want to review the outputs first"]
3. If `confirm_after_validate` is false:
   - Automatically proceed to `complete` without asking for user confirmation

{{EXTRA_CONTEXT}}
