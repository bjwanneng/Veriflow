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
   yosys -s stage_5_synth/synth.ys 2>&1 | tee stage_5_synth/synth.log
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

## Output
Print: synthesis status, cell count, wire count, any warnings.

{{EXTRA_CONTEXT}}
