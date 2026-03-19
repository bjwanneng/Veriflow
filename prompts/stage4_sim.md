# Stage 4: Simulation & Verification

You are a Verilog RTL design agent. Your task is to create testbenches, run simulations, and verify correctness.

## Working Directory
{{PROJECT_DIR}}

## Spec JSON
{{SPEC_JSON}}

## Tasks

### Part A: Unit Testbenches

1. For each non-top module in `stage_3_codegen/rtl/`, create a unit testbench `stage_4_sim/tb/tb_unit_<module_name>.v`.

2. Each unit testbench must include:
   - Complete DUT instantiation with all ports connected
   - Clock generation: `always #5 clk = ~clk;`
   - Reset sequence: assert reset for 10 cycles, then deassert (use the reset signal name from `.veriflow/project_config.json` `coding_style.reset_signal`)
   - Test stimulus: zero-input, all-ones, and at least one pattern test
   - Self-checking: compare output vs expected, print PASS/FAIL
   - `$finish` to prevent hang
   - Timeout watchdog: `initial begin #50000; $display("[TIMEOUT]"); $finish; end`

3. Compile and run each unit test:
   ```bash
   export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
   iverilog -g2005 -o stage_4_sim/sim_output/sim_unit_X.vvp stage_3_codegen/rtl/X.v stage_4_sim/tb/tb_unit_X.v
   timeout 30 vvp stage_4_sim/sim_output/sim_unit_X.vvp > stage_4_sim/sim_output/unit_X.log 2>&1
   # NOTE: On Windows without `timeout`, run vvp directly (testbench watchdog handles timeout).
   # If `tee` is unavailable, use file redirection: > file.log 2>&1
   ```

### Part B: Integration Testbench

4. Create `stage_4_sim/tb/tb_<top_module>.v` with:
   - Full DUT instantiation (all ports, names/widths match RTL exactly)
   - Standard test vector verification from project requirements
   - Test cases: single operation, round-trip, back-to-back (4+ blocks as applicable)
   - Self-checking with PASS/FAIL for each test
   - Timeout watchdog
   - `$finish`

5. Compile and run integration test WITH COVERAGE:
   ```bash
   # Compile with coverage flags
   iverilog -g2005 -o stage_4_sim/sim_output/sim_top.vvp stage_3_codegen/rtl/*.v stage_4_sim/tb/tb_*.v
   # Run with VCD output for coverage (ensure testbench has $dumpfile/$dumpvars)
   timeout 60 vvp stage_4_sim/sim_output/sim_top.vvp > stage_4_sim/sim_output/sim_top.log 2>&1
   # NOTE: On Windows without `timeout`, run vvp directly (testbench watchdog handles timeout).
   # If `tee` is unavailable, use file redirection: > file.log 2>&1
   ```

6. Generate Coverage Data

   All testbenches must include VCD dump commands:
   ```verilog
   initial begin
       $dumpfile("stage_4_sim/coverage/tb_<module_name>.vcd");
       $dumpvars(0, tb_<module_name>);
   end
   ```

   Coverage outputs to save:
   - `stage_4_sim/coverage/*.vcd` - Waveform dump files
   - `stage_4_sim/coverage/*.saif` - Switching activity information (if available)
   - `stage_4_sim/coverage/*.dat` - Coverage data files (if available)

7. If any test FAILS, analyze the output, fix the RTL or testbench, and re-run until all PASS.

### Part C: Timing-Specific Verification

8. Create timing-specific tests in `stage_4_sim/tb/` alongside the integration testbench:

#### 8.1 Off-by-One Latency Detection Test
Create a test that sends a single-cycle pulse on `i_valid` and precisely counts the number of clock cycles until `o_valid` is asserted. Compare against the `EXPECTED_LATENCY` from the spec's `timing_contracts.latency_cycles`.

```verilog
// Latency detection test pattern:
// 1. After reset, drive i_valid=1 for exactly 1 cycle with known data
// 2. Count cycles until o_valid==1
// 3. Compare measured_latency vs EXPECTED_LATENCY
// 4. FAIL if off by even 1 cycle
task test_latency_detection;
    integer cycle_count;
    begin
        $display("[TEST] Latency Detection");
        @(posedge clk);
        i_valid = 1;
        i_data = 32'hDEADBEEF;
        @(posedge clk);
        i_valid = 0;
        cycle_count = 0;
        while (o_valid !== 1 && cycle_count < 100) begin
            @(posedge clk);
            cycle_count = cycle_count + 1;
        end
        if (cycle_count !== EXPECTED_LATENCY) begin
            $display("[FAIL] Latency mismatch: expected %0d cycles, measured %0d", EXPECTED_LATENCY, cycle_count);
            $finish;
        end
        $display("[PASS] Latency = %0d cycles (matches spec)", cycle_count);
    end
endtask
```

#### 8.2 Backpressure Stress Test
If the design has a ready/backpressure signal, create a test that:
- Continuously drives valid data at the input
- Randomly deasserts `o_ready` (or asserts backpressure) using a PRBS or LFSR pattern
- After all data is sent, verifies that every input word appears at the output (no data loss)
- Verifies data ordering is preserved

```verilog
// Backpressure stress test pattern:
// 1. Send N data words continuously (i_valid=1 every cycle)
// 2. Randomly toggle o_ready with ~50% probability each cycle
// 3. Collect all outputs, verify count == N and data matches
task test_backpressure_stress;
    // ... implement with random ready toggling ...
endtask
```

#### 8.3 Pipeline Bubble Test
Test intermittent valid input (bubbles in the pipeline):
- Drive `i_valid` with a pattern like 1,0,0,1,0,1,1,0 (gaps between valid data)
- Verify that bubbles propagate correctly and do not corrupt adjacent data
- Verify output data matches input data in order

9. Compile and run timing-specific tests:
   ```bash
   export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
   iverilog -g2005 -o stage_4_sim/sim_output/sim_timing.vvp stage_3_codegen/rtl/*.v stage_4_sim/tb/tb_timing_*.v
   timeout 60 vvp stage_4_sim/sim_output/sim_timing.vvp > stage_4_sim/sim_output/timing_tests.log 2>&1
   ```

### Part D: Cocotb-Based Regression

10. Copy the entire `stage_2_timing/cocotb/` directory to `stage_4_sim/cocotb_regression/`:
    ```bash
    cp -r stage_2_timing/cocotb/* stage_4_sim/cocotb_regression/
    ```

11. Update the Makefile in `stage_4_sim/cocotb_regression/` — change `VERILOG_SOURCES` to point to Stage 3 RTL:
    ```makefile
    VERILOG_SOURCES += $(PWD)/../../stage_3_codegen/rtl/*.v
    ```

12. Run cocotb regression with default seed:
    ```bash
    cd stage_4_sim/cocotb_regression
    export PYTHONPATH=$(pwd):$PYTHONPATH
    export COCOTB_RANDOM_SEED=42
    make sim 2>&1 | tee cocotb_default_seed.log
    ```

13. Run cocotb regression with 3 different seeds to improve coverage:
    ```bash
    for seed in 12345 67890 24680; do
        export COCOTB_RANDOM_SEED=$seed
        make sim 2>&1 | tee cocotb_seed_${seed}.log
        make clean
    done
    ```

14. Generate `cocotb_regression_report.json` in `stage_4_sim/cocotb_regression/`:
    ```json
    {
        "total_tests": <number>,
        "passed": <number>,
        "failed": <number>,
        "seeds_run": [42, 12345, 67890, 24680],
        "per_seed_results": {
            "42": {"passed": <n>, "failed": <n>},
            "12345": {"passed": <n>, "failed": <n>},
            "67890": {"passed": <n>, "failed": <n>},
            "24680": {"passed": <n>, "failed": <n>}
        },
        "coverage_summary": {
            "data_range_pct": <float>,
            "protocol_corner_cases_pct": <float>
        }
    }
    ```

15. If any cocotb test fails, analyze the failure, fix the RTL or test, and re-run until all seeds pass.

### Part E: Requirements Coverage Report

16. Generate `stage_4_sim/requirements_coverage_report.json` by reading the `requirements_coverage_matrix.json` from `stage_2_timing/cocotb/` (or `stage_4_sim/cocotb_regression/`) and updating it with actual simulation results:

```json
{
  "generated_at": "<ISO8601 timestamp>",
  "source_matrix": "requirements_coverage_matrix.json",
  "requirements": [
    {
      "req_id": "REQ-FUNC-001",
      "category": "functional",
      "description": "Requirement description",
      "verification_status": "verified",
      "cocotb_tests_run": ["test_directed_basic"],
      "cocotb_tests_passed": ["test_directed_basic"],
      "notes": ""
    }
  ],
  "summary": {
    "total_requirements": 0,
    "verified": 0,
    "failed": 0,
    "not_run": 0,
    "requirements_coverage_pct": 0.0,
    "by_category": {
      "functional": {"total": 0, "verified": 0, "coverage_pct": 0.0},
      "performance": {"total": 0, "verified": 0, "coverage_pct": 0.0},
      "interface": {"total": 0, "verified": 0, "coverage_pct": 0.0},
      "constraint": {"total": 0, "verified": 0, "coverage_pct": 0.0}
    }
  }
}
```

For each requirement in the matrix:
- If all mapped cocotb tests passed → `verification_status: "verified"`
- If any mapped cocotb test failed → `verification_status: "failed"`
- If no mapped cocotb test was run → `verification_status: "not_run"`

## Constraints
- ALL testbenches must have self-checking (PASS/FAIL) — no waveform-only tests
- ALL testbenches must have $finish and timeout watchdog
- Save simulation logs to `stage_4_sim/sim_output/*.log`
- Unit tests must all pass before running integration test
- **Coverage required**: All testbenches must generate VCD files in `stage_4_sim/coverage/`
- **Simulation must complete**: All simulations must run to completion with "ALL TESTS PASSED" or equivalent
- **Cocotb regression must run**: The cocotb-based regression from Stage 2 must be executed in `stage_4_sim/cocotb_regression/`
- **All cocotb runs must record seed**: Every cocotb run must log the `COCOTB_RANDOM_SEED` used
- **Must generate `cocotb_regression_report.json`**: Report must contain total_tests, passed, failed, seeds_run, and coverage_summary
- **Must generate `stage_4_sim/requirements_coverage_report.json`**: Report must contain requirements array with verification_status and summary with `requirements_coverage_pct > 0`

## Output
Print: unit test results (per-module PASS/FAIL), integration test results, cocotb regression results (per-seed pass/fail, coverage summary), overall verdict.

### After Validation: Confirm to Proceed

After running `validate` and validation passes, read and check the project config:

1. Read `.veriflow/project_config.json` and check the value of `confirm_after_validate`
2. If `confirm_after_validate` is true (or the field doesn't exist):
   - Print a summary of what was accomplished in this stage to the user
   - Use AskUserQuestion tool to ask for confirmation before proceeding to `complete`
   - Question: "Stage 4 validation passed! Do you want to proceed to mark this stage complete?"
   - Options: ["Proceed to complete this stage", "Wait, I want to review the outputs first"]
3. If `confirm_after_validate` is false:
   - Automatically proceed to `complete` without asking for user confirmation

{{EXTRA_CONTEXT}}
