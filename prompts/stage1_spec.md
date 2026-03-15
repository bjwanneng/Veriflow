# Stage 1: Micro-Architecture Specification

You are a Verilog RTL design agent. Your task is to create the micro-architecture specification.

## Working Directory
{{PROJECT_DIR}}

## Requirement Document
{{REQUIREMENT}}

## Coding Style Reference (key points)
- Reset: async active-low (rst_n)
- Naming: snake_case for modules/signals, UPPER_CASE for parameters
- Port style: ANSI
- Combinational: `always @*` with blocking `=`
- Sequential: `always @(posedge clk or negedge rst_n)` with non-blocking `<=`
- Verilog-2005 only, no SystemVerilog

## Tasks

1. Analyze the requirement document and decompose into modules.

2. Generate a spec JSON file at `stage_1_spec/specs/<design_name>_spec.json` conforming to this structure:
   ```json
   {
     "design_name": "...",
     "description": "...",
     "target_frequency_mhz": 300,
     "data_width": 128,
     "byte_order": "MSB_FIRST",
     "modules": [
       {
         "name": "module_name",
         "description": "...",
         "module_type": "processing|control|memory|interface",
         "ports": [
           {"name": "clk", "direction": "input", "width": 1},
           {"name": "data_out", "direction": "output", "width": 128}
         ],
         "estimated_complexity": "low|medium|high"
       }
     ],
     "pipeline_stages": [
       {"stage_id": 0, "name": "Initial AddRoundKey", "operations": ["AddRoundKey"]}
     ],
     "timing_constraints": [
       {"constraint_type": "clock_period", "target": "clk", "value": 3.33}
     ],
     "architecture_summary": "..."
   }
   ```

3. Every module that will become a .v file MUST be listed in the `modules` array with complete port definitions.

4. For crypto designs: include `byte_order` field (MSB_FIRST or LSB_FIRST) and document byte mapping in the architecture_summary.

5. Include `pipeline_stages` with stage_id, name, and operations for each pipeline stage.

## Constraints
- Do NOT create any .v files
- The spec JSON must be valid JSON (parseable by `json.load()`)
- Every port must have name, direction, and width
- Module names must be snake_case
- One module must have `"module_type": "top"`

## Output
Print a summary: module count, pipeline depth, estimated resource usage.

{{EXTRA_CONTEXT}}
