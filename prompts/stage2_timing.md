# Stage 2: Virtual Timing Modeling

You are a Verilog RTL design agent. Your task is to create timing scenarios, golden traces, AND (if cocotb is enabled) Cocotb test files.

## Working Directory
{{PROJECT_DIR}}

## Requirement Document
{{REQUIREMENT}}

## Spec JSON
{{SPEC_JSON}}

## Pre-Flight: Read Project Config

Before starting, read `.veriflow/project_config.json` and extract:
- `enable_cocotb`: whether to generate cocotb verification library (default: false)
- `testbench_depth`: "minimal" | "standard" | "thorough" (default: "standard")

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

### 3.5 Generate Requirements Coverage Matrix (CONDITIONAL — cocotb only)

**IMPORTANT**: If `enable_cocotb` is `false` in project_config.json, SKIP this task and all of Task 4. Proceed directly to Task 5.

If `enable_cocotb` is `true`:

Read `stage_1_spec/specs/structured_requirements.json` and generate a requirements-to-test traceability matrix at `stage_2_timing/cocotb/requirements_coverage_matrix.json`:

```json
{
  "generated_from": "structured_requirements.json",
  "matrix": [
    {
      "req_id": "REQ-FUNC-001",
      "category": "functional",
      "description": "Short requirement description",
      "cocotb_tests": ["test_directed_basic", "test_constrained_random"],
      "coverpoints": ["data_range", "req_func_001_operation"],
      "yaml_scenarios": ["single_operation.yaml", "back_to_back.yaml"],
      "status": "not_run"
    }
  ],
  "coverage_summary": {
    "total_requirements": 0,
    "testable_requirements": 0,
    "covered_requirements": 0,
    "coverage_pct": 0.0
  }
}
```

**Rules**:
- Every requirement with `testable: true` from structured_requirements.json must appear in the matrix
- Each testable requirement must map to at least one `cocotb_tests` entry (non-empty)
- Each testable requirement should map to at least one `coverpoints` entry
- `status` is initialized to `"not_run"` — it will be updated after simulation in Stage 4
- `coverage_summary.coverage_pct` = covered / testable * 100

### 4. Generate Cocotb Verification Library (CONDITIONAL — UVM-like Architecture)

**IMPORTANT**: If `enable_cocotb` is `false` in project_config.json, SKIP this entire Task 4. Proceed directly to Task 5.

If `enable_cocotb` is `true`:

Generate a complete UVM-like cocotb verification library in `stage_2_timing/cocotb/` with the following directory structure:

```
stage_2_timing/cocotb/
  vf_bfm/
    __init__.py
    base_bfm.py            # Transaction dataclass + abstract BFM base class
    valid_ready_bfm.py     # ValidReadyDriver + ValidReadyMonitor
    valid_only_bfm.py      # ValidOnlyDriver + ValidOnlyMonitor
  vf_scoreboard.py         # Scoreboard: golden model queue comparison
  vf_coverage.py           # CoverageCollector: manual bin functional coverage
  vf_test_factory.py       # ConstrainedRandom: seed-controlled constrained random
  golden_model.py          # GoldenModel (extracted as standalone file)
  timing_checker.py        # TimingChecker (extracted as standalone file)
  test_integration.py      # Integration tests using full Driver/Monitor/Scoreboard
  test_unit_<module>.py    # Unit tests per module
  Makefile                 # Enhanced: regression + seed control
```

#### 4.1 BFM Infrastructure (`vf_bfm/`)

Generate the `vf_bfm/` directory with the following files:

**`vf_bfm/__init__.py`**:
```python
from .base_bfm import Transaction
from .valid_ready_bfm import ValidReadyDriver, ValidReadyMonitor
from .valid_only_bfm import ValidOnlyDriver, ValidOnlyMonitor
```

**`vf_bfm/base_bfm.py`** — Transaction dataclass and abstract BFM base:
```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class Transaction:
    """Single bus transaction."""
    valid: bool = False
    data: int = 0
    ready: bool = True
    metadata: dict = field(default_factory=dict)

class BaseDriver:
    """Abstract driver base class."""
    def __init__(self, dut, clk_name="clk"):
        self.dut = dut
        self.clk_name = clk_name

    async def send(self, data: int, **kwargs):
        raise NotImplementedError

class BaseMonitor:
    """Abstract monitor base class."""
    def __init__(self, dut, clk_name="clk"):
        self.dut = dut
        self.clk_name = clk_name
        self.transactions = []

    async def start(self):
        raise NotImplementedError
```

**`vf_bfm/valid_ready_bfm.py`** — ValidReadyDriver + ValidReadyMonitor:
```python
import cocotb
from cocotb.triggers import RisingEdge
from .base_bfm import BaseDriver, BaseMonitor, Transaction

class ValidReadyDriver(BaseDriver):
    """Drive valid+data, wait for ready handshake."""
    def __init__(self, dut, clk_name="clk",
                 valid_signal="i_valid", data_signal="i_data", ready_signal="o_ready"):
        super().__init__(dut, clk_name)
        self.valid_signal = valid_signal
        self.data_signal = data_signal
        self.ready_signal = ready_signal

    async def send(self, data: int, **kwargs):
        clk = getattr(self.dut, self.clk_name)
        getattr(self.dut, self.valid_signal).value = 1
        getattr(self.dut, self.data_signal).value = data
        while True:
            await RisingEdge(clk)
            if int(getattr(self.dut, self.ready_signal).value) == 1:
                break
        getattr(self.dut, self.valid_signal).value = 0

class ValidReadyMonitor(BaseMonitor):
    """Background coroutine: sample output on valid&ready."""
    def __init__(self, dut, clk_name="clk",
                 valid_signal="o_valid", data_signal="o_data", ready_signal="o_ready"):
        super().__init__(dut, clk_name)
        self.valid_signal = valid_signal
        self.data_signal = data_signal
        self.ready_signal = ready_signal

    async def start(self):
        clk = getattr(self.dut, self.clk_name)
        while True:
            await RisingEdge(clk)
            if (int(getattr(self.dut, self.valid_signal).value) == 1 and
                int(getattr(self.dut, self.ready_signal).value) == 1):
                txn = Transaction(
                    valid=True,
                    data=int(getattr(self.dut, self.data_signal).value),
                    ready=True,
                )
                self.transactions.append(txn)
```

**`vf_bfm/valid_only_bfm.py`** — ValidOnlyDriver + ValidOnlyMonitor (for designs without ready):
```python
import cocotb
from cocotb.triggers import RisingEdge
from .base_bfm import BaseDriver, BaseMonitor, Transaction

class ValidOnlyDriver(BaseDriver):
    """Drive valid+data for one cycle (no handshake)."""
    def __init__(self, dut, clk_name="clk",
                 valid_signal="i_valid", data_signal="i_data"):
        super().__init__(dut, clk_name)
        self.valid_signal = valid_signal
        self.data_signal = data_signal

    async def send(self, data: int, **kwargs):
        clk = getattr(self.dut, self.clk_name)
        getattr(self.dut, self.valid_signal).value = 1
        getattr(self.dut, self.data_signal).value = data
        await RisingEdge(clk)
        getattr(self.dut, self.valid_signal).value = 0

class ValidOnlyMonitor(BaseMonitor):
    """Background coroutine: sample output when valid is asserted."""
    def __init__(self, dut, clk_name="clk",
                 valid_signal="o_valid", data_signal="o_data"):
        super().__init__(dut, clk_name)
        self.valid_signal = valid_signal
        self.data_signal = data_signal

    async def start(self):
        clk = getattr(self.dut, self.clk_name)
        while True:
            await RisingEdge(clk)
            if int(getattr(self.dut, self.valid_signal).value) == 1:
                txn = Transaction(
                    valid=True,
                    data=int(getattr(self.dut, self.data_signal).value),
                )
                self.transactions.append(txn)
```

Select the appropriate BFM based on the spec's `timing_contracts.protocol_type`:
- If `valid_ready` → use `ValidReadyDriver` / `ValidReadyMonitor`
- If `valid_only` or no ready signal → use `ValidOnlyDriver` / `ValidOnlyMonitor`

#### 4.2 Scoreboard (`vf_scoreboard.py`)

Generate `vf_scoreboard.py`:

```python
import json
from collections import deque

class Scoreboard:
    """Golden model queue-based comparison scoreboard."""

    def __init__(self, golden_model):
        self.golden = golden_model
        self.expected_queue = deque()
        self.matches = 0
        self.mismatches = []

    def add_expected(self, input_data):
        """Feed input into golden model, enqueue expected output."""
        expected_output = self.golden.compute(input_data)
        self.expected_queue.append({
            "input": input_data,
            "expected_output": expected_output,
        })

    def check(self, actual_output):
        """Pop queue head and compare with actual DUT output."""
        if not self.expected_queue:
            self.mismatches.append({
                "type": "unexpected_output",
                "actual": actual_output,
            })
            return False
        expected = self.expected_queue.popleft()
        if int(actual_output) == int(expected["expected_output"]):
            self.matches += 1
            return True
        else:
            self.mismatches.append({
                "type": "value_mismatch",
                "input": expected["input"],
                "expected": expected["expected_output"],
                "actual": int(actual_output),
            })
            return False

    def report(self):
        """Return structured comparison report as dict (JSON-serializable)."""
        return {
            "matches": self.matches,
            "mismatches": len(self.mismatches),
            "details": self.mismatches,
            "pending": len(self.expected_queue),
            "pass": len(self.mismatches) == 0 and len(self.expected_queue) == 0,
        }
```

#### 4.3 Functional Coverage (`vf_coverage.py`)

Generate `vf_coverage.py` — pure Python, no external dependencies:

```python
import json

class CoverageCollector:
    """Manual-bin functional coverage collector."""

    def __init__(self):
        self.coverpoints = {}

    def add_coverpoint(self, name, bins):
        """Define a coverpoint with named bins.
        bins: dict mapping bin_name -> (low, high) range or list of values.
        Example: {"zero": (0, 0), "small": (1, 255), "large": (256, 65535)}
        """
        self.coverpoints[name] = {
            "bins": bins,
            "hits": {b: 0 for b in bins},
        }

    def sample(self, name, value):
        """Sample a value against a coverpoint's bins."""
        if name not in self.coverpoints:
            return
        cp = self.coverpoints[name]
        for bin_name, bin_range in cp["bins"].items():
            if isinstance(bin_range, (list, tuple)) and len(bin_range) == 2:
                if bin_range[0] <= value <= bin_range[1]:
                    cp["hits"][bin_name] += 1
            elif isinstance(bin_range, list):
                if value in bin_range:
                    cp["hits"][bin_name] += 1

    def report(self):
        """Return coverage report as dict (JSON-serializable)."""
        result = {}
        for name, cp in self.coverpoints.items():
            bins_total = len(cp["bins"])
            bins_hit = sum(1 for h in cp["hits"].values() if h > 0)
            result[name] = {
                "bins_hit": bins_hit,
                "bins_total": bins_total,
                "coverage_pct": round(100.0 * bins_hit / bins_total, 1) if bins_total > 0 else 0.0,
                "bin_details": dict(cp["hits"]),
            }
        return result
```

The following coverpoints MUST be defined in the integration test:
- `data_range`: bins for zero / small / mid / large / max values based on data width
- `protocol_corner_cases`: bins for back-to-back valid, valid after idle, valid with backpressure, etc.
- **Requirement-derived coverpoints**: Read `stage_1_spec/specs/structured_requirements.json` and dynamically generate additional coverpoints:
  - For each **functional** requirement (`category: "functional"`): create a coverpoint verifying the specific operation or data transformation described
  - For each **performance** requirement (`category: "performance"`): create a coverpoint tracking the performance metric (e.g., throughput bins, latency bins)
  - For each **interface** requirement (`category: "interface"`): create a coverpoint for the protocol behavior described (e.g., handshake compliance, backpressure handling)
  - Coverpoint names should reference the `req_id` (e.g., `req_func_001_operation`, `req_perf_001_throughput`)

#### 4.4 Constrained Random (`vf_test_factory.py`)

Generate `vf_test_factory.py`:

```python
import os
import random

class ConstrainedRandom:
    """Seed-controlled constrained random stimulus generator."""

    def __init__(self, seed=None):
        if seed is None:
            seed = int(os.environ.get("COCOTB_RANDOM_SEED", "42"))
        self.seed = seed
        self.rng = random.Random(seed)

    def random_data(self, width, constraints=None):
        """Generate constrained random data value.
        constraints: dict with optional keys 'min', 'max', 'exclude'.
        """
        max_val = (1 << width) - 1
        min_val = 0
        exclude = set()
        if constraints:
            min_val = constraints.get("min", 0)
            max_val = constraints.get("max", max_val)
            exclude = set(constraints.get("exclude", []))
        while True:
            val = self.rng.randint(min_val, max_val)
            if val not in exclude:
                return val

    def random_valid_pattern(self, length, density=0.5):
        """Generate random valid assertion pattern.
        density: probability of valid=1 each cycle.
        """
        return [1 if self.rng.random() < density else 0 for _ in range(length)]

    def random_ready_pattern(self, length, density=0.7):
        """Generate random backpressure pattern (ready signal).
        density: probability of ready=1 each cycle.
        """
        return [1 if self.rng.random() < density else 0 for _ in range(length)]
```

The seed is read from environment variable `COCOTB_RANDOM_SEED` (default: 42).

#### 4.5 Integration Tests (`test_integration.py`)

Rewrite `test_integration.py` to use the full Driver/Monitor/Scoreboard architecture:

```python
import cocotb
import json
import os
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# Import verification library
from vf_bfm import ValidReadyDriver, ValidReadyMonitor  # or ValidOnly variants
from vf_scoreboard import Scoreboard
from vf_coverage import CoverageCollector
from vf_test_factory import ConstrainedRandom
from golden_model import GoldenModel
from timing_checker import TimingChecker

PIPELINE_DEPTH = 3  # Adjust to match spec timing_contracts.latency_cycles

async def reset_dut(dut, reset_n="rst_n"):
    getattr(dut, reset_n).value = 0
    await Timer(50, units="ns")
    getattr(dut, reset_n).value = 1
    await Timer(50, units="ns")

@cocotb.test()
async def test_directed_basic(dut):
    """Directed test using Driver/Monitor/Scoreboard."""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    gm = GoldenModel()
    gm.reset()
    sb = Scoreboard(gm)
    driver = ValidReadyDriver(dut)
    monitor = ValidReadyMonitor(dut)
    cocotb.start_soon(monitor.start())

    # Send directed test vectors
    test_vectors = [0x00000000, 0x12345678, 0xDEADBEEF, 0xFFFFFFFF]
    for vec in test_vectors:
        sb.add_expected(vec)
        await driver.send(vec)

    # Wait for pipeline flush
    for _ in range(PIPELINE_DEPTH + 2):
        await RisingEdge(dut.clk)

    # Check all monitored transactions
    for txn in monitor.transactions:
        sb.check(txn.data)

    report = sb.report()
    assert report["pass"], f"Scoreboard mismatches: {report['details']}"
    dut._log.info("Directed basic test PASSED")

@cocotb.test()
async def test_constrained_random(dut):
    """100+ constrained random transactions with coverage collection."""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    gm = GoldenModel()
    gm.reset()
    sb = Scoreboard(gm)
    driver = ValidReadyDriver(dut)
    monitor = ValidReadyMonitor(dut)
    cocotb.start_soon(monitor.start())

    cr = ConstrainedRandom()
    cov = CoverageCollector()
    data_width = 32  # Adjust to match spec

    # Define coverpoints
    max_val = (1 << data_width) - 1
    cov.add_coverpoint("data_range", {
        "zero": (0, 0),
        "small": (1, 255),
        "mid": (256, 65535),
        "large": (65536, max_val - 1),
        "max": (max_val, max_val),
    })
    cov.add_coverpoint("protocol_corner_cases", {
        "back_to_back": (1, 1),
        "after_idle": (2, 2),
        "with_backpressure": (3, 3),
    })

    # Send 100+ random transactions
    num_txns = 120
    for i in range(num_txns):
        data = cr.random_data(data_width)
        cov.sample("data_range", data)
        sb.add_expected(data)
        await driver.send(data)

    # Wait for pipeline flush
    for _ in range(PIPELINE_DEPTH + 5):
        await RisingEdge(dut.clk)

    for txn in monitor.transactions:
        sb.check(txn.data)

    report = sb.report()
    assert report["pass"], f"Random test mismatches: {report['details']}"

    # Write coverage report
    cov_report = cov.report()
    cov_path = os.path.join(os.path.dirname(__file__), "coverage_report.json")
    with open(cov_path, "w") as f:
        json.dump(cov_report, f, indent=2)

    dut._log.info(f"Constrained random test PASSED ({num_txns} transactions)")

@cocotb.test()
async def test_backpressure_random(dut):
    """Random backpressure stress test."""
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    gm = GoldenModel()
    gm.reset()
    sb = Scoreboard(gm)
    cr = ConstrainedRandom()
    driver = ValidReadyDriver(dut)
    monitor = ValidReadyMonitor(dut)
    cocotb.start_soon(monitor.start())

    # Generate random backpressure pattern
    num_txns = 50
    ready_pattern = cr.random_ready_pattern(num_txns * 3, density=0.5)

    sent = 0
    cycle = 0
    while sent < num_txns:
        if cycle < len(ready_pattern):
            dut.o_ready.value = ready_pattern[cycle]
        data = cr.random_data(32)
        sb.add_expected(data)
        await driver.send(data)
        sent += 1
        cycle += 1

    # Flush
    dut.o_ready.value = 1
    for _ in range(PIPELINE_DEPTH + 10):
        await RisingEdge(dut.clk)

    for txn in monitor.transactions:
        sb.check(txn.data)

    report = sb.report()
    assert report["pass"], f"Backpressure test mismatches: {report['details']}"
    dut._log.info("Backpressure random test PASSED")
```

Adapt signal names, data widths, and BFM selection to match the actual spec.

**Requirement Coverage Integration**: In `test_integration.py`, ensure:
- Each testable requirement from `structured_requirements.json` has at least one test that exercises it
- After all tests complete, update `requirements_coverage_matrix.json` — set `status` to `"covered"` for each requirement that has a passing test mapped to it
- The test should load the matrix at startup and write the updated matrix at teardown

#### 4.6 GoldenModel / TimingChecker (Extracted as Standalone Files)

Extract the GoldenModel and TimingChecker from the old inline `test_integration.py` into separate files. Content is the same as before, just in their own modules.

**`golden_model.py`**:
```python
PIPELINE_DEPTH = 3  # Adjust to match spec timing_contracts.latency_cycles

class GoldenModel:
    """Cycle-accurate golden reference for pipeline/FSM designs."""

    def __init__(self):
        self.pipeline = [None] * PIPELINE_DEPTH
        self.pipeline_valid = [False] * PIPELINE_DEPTH
        self.output_data = 0
        self.output_valid = False

    def reset(self):
        self.pipeline = [None] * PIPELINE_DEPTH
        self.pipeline_valid = [False] * PIPELINE_DEPTH
        self.output_data = 0
        self.output_valid = False

    def tick(self, i_valid, i_data, o_ready=True):
        """Advance one clock cycle. Returns expected output signals dict."""
        if o_ready:
            self.output_valid = self.pipeline_valid[-1]
            self.output_data = self._compute(self.pipeline[-1]) if self.pipeline_valid[-1] else 0
            for i in range(PIPELINE_DEPTH - 1, 0, -1):
                self.pipeline[i] = self.pipeline[i - 1]
                self.pipeline_valid[i] = self.pipeline_valid[i - 1]
            self.pipeline[0] = i_data if i_valid else None
            self.pipeline_valid[0] = bool(i_valid)
        return {
            "o_valid": int(self.output_valid),
            "o_data": self.output_data,
            "i_ready": int(o_ready),
        }

    def compute(self, data):
        """Compute expected output for Scoreboard use."""
        return self._compute(data)

    def _compute(self, data):
        """Core computation — MUST implement the actual algorithm from spec."""
        if data is None:
            return 0
        return data  # Replace with actual algorithm
```

**`timing_checker.py`**:
```python
class TimingChecker:
    """Cycle-by-cycle comparison of DUT outputs vs GoldenModel."""

    def __init__(self, golden):
        self.golden = golden
        self.cycle = 0
        self.mismatches = []

    def check(self, dut_signals, expected):
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
        return {
            "total_cycles": self.cycle,
            "mismatch_count": len(self.mismatches),
            "mismatches": self.mismatches,
            "pass": len(self.mismatches) == 0,
        }
```

#### 4.7 Unit Tests (`test_unit_<module>.py`)

For each module in spec JSON, create `test_unit_<module_name>.py` (same as before):
```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

async def reset_dut(dut, reset_n="rst_n"):
    getattr(dut, reset_n).value = 0
    await Timer(50, units="ns")
    getattr(dut, reset_n).value = 1
    await Timer(50, units="ns")

@cocotb.test()
async def test_basic_reset(dut):
    clock = Clock(dut.clk, 3.33, units="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)
    # Check post-reset state ...
    dut._log.info("Reset test passed!")
```

#### 4.8 Makefile (Enhanced)

Create Makefile in `stage_2_timing/cocotb/`:

```makefile
# Cocotb Makefile for UVM-like Verification
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../stage_3_codegen/rtl/*.v

TOPLEVEL := <top_module_name>
MODULE := test_integration

# Seed control
export COCOTB_RANDOM_SEED ?= 42

# Add verification library to PYTHONPATH
export PYTHONPATH := $(PWD):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim

# Run single test module
test_%:
	MODULE=test_$* $(MAKE) sim

# Run all tests
.PHONY: all
all:
	@echo "Running all Cocotb tests..."
	MODULE=test_integration $(MAKE) sim

# Regression: run with multiple seeds
.PHONY: regression
regression:
	@echo "=== Regression: seed 42 ==="
	COCOTB_RANDOM_SEED=42 MODULE=test_integration $(MAKE) sim
	@echo "=== Regression: seed 12345 ==="
	COCOTB_RANDOM_SEED=12345 MODULE=test_integration $(MAKE) sim
	@echo "=== Regression: seed 67890 ==="
	COCOTB_RANDOM_SEED=67890 MODULE=test_integration $(MAKE) sim

.PHONY: clean
clean::
	rm -rf sim_build __pycache__ *.vcd *.log coverage_report.json
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

### Cocotb Constraints (only when `enable_cocotb` is true)
- Cocotb tests must be valid Python
- Must include standard test vectors in Cocotb tests
- (Very important) Must include a Python `GoldenModel` class with `tick()` and `reset()` methods that model the pipeline cycle-by-cycle
- (Very important) Must include a `TimingChecker` class (or equivalent) that compares DUT outputs against GoldenModel on every cycle and records mismatches with cycle number, signal name, expected/actual values
- Must have a Driver class (with `send` method) in `vf_bfm/`
- Must have a Monitor class (with `start` method) in `vf_bfm/`
- Must have a Scoreboard class (with `check` + `report` methods) in `vf_scoreboard.py`
- Must have a CoverageCollector class (with `add_coverpoint` + `sample` + `report` methods) in `vf_coverage.py`
- Must have a ConstrainedRandom class (with seed parameter) in `vf_test_factory.py`
- `test_integration.py` must write `coverage_report.json` at test end
- Generate `timing_assertions.py` alongside `test_integration.py` containing the `TimingChecker` class if it is not embedded in `test_integration.py`
- **Must generate `stage_2_timing/cocotb/requirements_coverage_matrix.json`**
- **Every testable requirement from structured_requirements.json must map to at least one cocotb test in the matrix**
- **Coverpoints must include requirement-derived coverpoints (named with req_id prefix) in addition to baseline data_range and protocol_corner_cases**

### When cocotb is disabled
- Skip all cocotb-related file generation (Task 3.5 and Task 4)
- Do NOT create `stage_2_timing/cocotb/` directory

## Output
Print: number of scenarios created, golden traces generated. If cocotb enabled: Cocotb test files created, verification library files created, and test vectors included. If cocotb disabled: state that cocotb was skipped per project config.

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
