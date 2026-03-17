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

## Constraints
- ALL testbenches must have self-checking (PASS/FAIL) — no waveform-only tests
- ALL testbenches must have $finish and timeout watchdog
- Save simulation logs to `stage_4_sim/sim_output/*.log`
- Unit tests must all pass before running integration test
- **Coverage required**: All testbenches must generate VCD files in `stage_4_sim/coverage/`
- **Simulation must complete**: All simulations must run to completion with "ALL TESTS PASSED" or equivalent

## Output
Print: unit test results (per-module PASS/FAIL), integration test results, overall verdict.

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
