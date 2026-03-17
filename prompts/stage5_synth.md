# Stage 5: Synthesis Analysis

You are a Verilog RTL design agent. Your task is to run synthesis and analyze results.

## Working Directory
{{PROJECT_DIR}}

## Tasks

1. Create a Yosys synthesis script at `stage_5_synth/synth.ys`:
   ```
   # Read all RTL files
   read_verilog stage_3_codegen/rtl/*.v

   # Elaborate
   hierarchy -top <top_module_name>

   # Synthesis passes
   proc; opt; fsm; opt; memory; opt; techmap; opt

   # Resource report
   stat

   # Write synthesized netlist
   write_verilog stage_5_synth/synth_netlist.v
   ```

2. Run synthesis:
   ```bash
   export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
   cd {{PROJECT_DIR}}
   yosys -s stage_5_synth/synth.ys > stage_5_synth/synth.log 2>&1
   # NOTE: If `tee` is available, you can use: yosys ... 2>&1 | tee stage_5_synth/synth.log
   # On Windows without tee, file redirection works reliably.
   ```

3. Parse the `stat` output from the log and extract:
   - Number of cells (by type)
   - Number of wires
   - Total bits
   - Any warnings or errors

4. Save a synthesis report to `stage_5_synth/synth_report.json`:
   ```json
   {
     "status": "PASS|FAIL",
     "top_module": "...",
     "cells": {"$_AND_": 100, "$_OR_": 50, ...},
     "total_cells": 1234,
     "wires": 567,
     "warnings": [],
     "errors": []
   }
   ```

## Constraints
- Synthesis must complete without errors
- If synthesis fails, analyze the error and fix the RTL, then re-run
- Use generic synthesis (no FPGA-specific target) unless project config specifies otherwise
- **NO ERRORS allowed** in synthesis output
- **NO CRITICAL WARNINGS allowed**: Check for timing issues, unconnected signals, etc.
- Warnings should be reviewed and documented, but non-critical warnings are acceptable

## Output
Print: synthesis status, cell count, wire count, any warnings.

## Synthesis Report Requirements

The `synth_report.json` must include:
- `status`: "PASS" or "FAIL"
- `top_module`: Top module name
- `cells`: Cell count by type
- `total_cells`: Total cell count
- `wires`: Wire count
- `warnings`: List of all warnings (filter out non-critical if needed)
- `errors`: List of all errors

### After Validation: Confirm to Proceed

After running `validate` and validation passes, read and check the project config:

1. Read `.veriflow/project_config.json` and check the value of `confirm_after_validate`
2. If `confirm_after_validate` is true (or the field doesn't exist):
   - Print a summary of what was accomplished in this stage to the user
   - Use AskUserQuestion tool to ask for confirmation before proceeding to `complete`
   - Question: "Stage 5 validation passed! Do you want to proceed to mark this stage complete?"
   - Options: ["Proceed to complete this stage", "Wait, I want to review the outputs first"]
3. If `confirm_after_validate` is false:
   - Automatically proceed to `complete` without asking for user confirmation

{{EXTRA_CONTEXT}}
