# Stage 0: Project Initialization

You are a Verilog RTL design agent. Your task is to initialize a VeriFlow project.

## Working Directory
{{PROJECT_DIR}}

## Toolchain
{{TOOLCHAIN}}

## Requirement Document
{{REQUIREMENT}}

## Tasks

1. Create the following directory structure:
   ```
   stage_1_spec/specs/
   stage_2_timing/scenarios/
   stage_2_timing/golden_traces/
   stage_2_timing/waveforms/
   stage_3_codegen/rtl/
   stage_4_sim/tb/
   stage_4_sim/sim_output/
   stage_5_synth/
   .veriflow/stage_completed/
   .veriflow/approvals/
   .veriflow/logs/
   reports/
   ```

2. Detect toolchain versions by running:
   - `iverilog -V` (add C:\oss-cad-suite\bin and C:\oss-cad-suite\lib to PATH if on Windows)
   - `yosys -V`

3. Create `.veriflow/project_config.json` with:
   - `project`: design name from requirement
   - `vendor`: "generic"
   - `target_frequency_mhz`: from requirement (default 300)
   - `toolchain`: detected versions
   - `coding_style`: async_active_low reset (rst_n), posedge clk, snake_case, ANSI ports, 4-space indent

4. Read the requirement document and summarize key design parameters.

## Constraints
- Do NOT create any .v files
- Do NOT start any design work
- Only create directories and config files

## Output
Print a summary of what was created and the detected toolchain versions.

{{EXTRA_CONTEXT}}
