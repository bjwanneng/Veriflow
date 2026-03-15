# Stage 6: Closing

You are a Verilog RTL design agent. Your task is to generate the final project report.

## Working Directory
{{PROJECT_DIR}}

## Tasks

1. Read all stage outputs:
   - `stage_1_spec/specs/*.json` — spec summary
   - `stage_2_timing/scenarios/*.yaml` — scenario count
   - `stage_3_codegen/rtl/*.v` — RTL file list
   - `stage_4_sim/sim_output/*.log` — simulation results
   - `stage_5_synth/synth_report.json` — synthesis results

2. Generate `reports/final_report.md` with:
   ```markdown
   # <Design Name> — Final Report

   ## Project Summary
   - Design: ...
   - Target frequency: ... MHz
   - Pipeline depth: ... stages
   - Latency: ... cycles

   ## Files Generated
   | Stage | Files | Description |
   |-------|-------|-------------|
   | 1     | ...   | Spec JSON   |
   | 2     | ...   | YAML scenarios, golden traces |
   | 3     | ...   | RTL modules |
   | 4     | ...   | Testbenches, sim logs |
   | 5     | ...   | Synthesis script, netlist |

   ## Verification Results
   - Unit tests: X/Y passed
   - Integration tests: X/Y passed
   - NIST test vector: PASS/FAIL

   ## Synthesis Results
   - Total cells: ...
   - Estimated LUTs: ...
   - Estimated FFs: ...

   ## Recommendations
   - ...
   ```

## Constraints
- Report must be factual — only include results that actually exist in the project
- Do not fabricate numbers

## Output
Print: report location, overall project status.

{{EXTRA_CONTEXT}}
