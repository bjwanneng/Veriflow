# Stage 1: Micro-Architecture Specification

You are a Verilog RTL design agent. Your task is to create the detailed micro-architecture specification.

## Working Directory
{{PROJECT_DIR}}

## Requirement Document
{{REQUIREMENT}}

## Project Config
Check .veriflow/project_config.json for execution_mode (automatic or parameterized).

## Coding Style Rules
Incorporate naming best practices from the coding style guidelines and apply them to the JSON design:
{{CODING_STYLE}}

## Base Mandatory Constraints
- Reset: **per project config** — read `.veriflow/project_config.json` `coding_style.reset_type` and `coding_style.reset_signal` to determine reset polarity and signal name. Default: async active-low (`rst_n`)
- Naming: snake_case for modules/signals, UPPER_CASE for parameters
- Port style: ANSI
- Combinational: `always @*` with blocking `=`
- Sequential: use `always @(posedge clk or negedge rst_n)` for async reset, or `always @(posedge clk)` for sync reset — match the project config `coding_style.reset_type`
- Verilog-2005 only, no SystemVerilog

## Tasks

### 1. Analyze Requirements and Module Partitioning

Analyze the requirement document and decompose the design into multiple modules.

#### Parameterized Mode - If project_config.execution_mode == "parameterized"
Before proceeding, use AskUserQuestion tool to confirm:
1. Module partitioning scheme
2. Function description for each module

#### Automatic Mode
Proceed with module partitioning based on best practices.

### 2. Generate Detailed Specification JSON

Generate the complete architecture specification at `stage_1_spec/specs/<design_name>_spec.json`:

```json
{
  "design_name": "design_name",
  "description": "design_description",
  "target_frequency_mhz": 300,
  "data_width": 32,
  "byte_order": "MSB_FIRST",
  "byte_mapping_note": "byte_mapping_description",

  "modules": [
    {
      "name": "module_name",
      "description": "detailed_module_description",
      "module_type": "top|processing|control|memory|interface",
      "hierarchy_level": 0,
      "parent": "parent_module_name (except for top)",
      "submodules": ["submodule1", "submodule2"],
      "instantiation_count": 1,
      "clock_domains": [
        {
          "name": "main_clk",
          "clock_port": "clk",
          "reset_port": "rst_n",
          "frequency_mhz": 300,
          "reset_type": "async_active_low"
        }
      ],
      "ports": [
        {
          "name": "clk",
          "direction": "input",
          "width": 1,
          "protocol": "clock",
          "clock_edge": "posedge",
          "description": "system_clock"
        },
        {
          "name": "rst_n",
          "direction": "input",
          "width": 1,
          "protocol": "reset",
          "reset_active": "low",
          "description": "async_reset_active_low"
        },
        {
          "name": "i_data",
          "direction": "input",
          "width": 32,
          "protocol": "data",
          "byte_order": "MSB_FIRST",
          "description": "input_data_description",
          "valid_when": "i_valid == 1",
          "data_format": "data_format_description"
        },
        {
          "name": "i_valid",
          "direction": "input",
          "width": 1,
          "protocol": "handshake",
          "description": "input_data_valid",
          "handshake_relation": "handshake_description"
        },
        {
          "name": "o_data",
          "direction": "output",
          "width": 32,
          "protocol": "data",
          "byte_order": "MSB_FIRST",
          "description": "output_data_description",
          "latency_cycles": 1,
          "valid_when": "o_valid == 1",
          "combinational": false,
          "data_format": "data_format_description"
        }
      ],
      "interface_interactions": [
        {
          "source": "source_signal_or_module",
          "destination": "destination_signal_or_module",
          "handshake_type": "valid-based|ready-valid|none",
          "latency_cycles": 0,
          "description": "interaction_description"
        }
      ],
      "config_sequence": [
        {
          "phase": "idle",
          "signal_values": {"cfg_en": 0},
          "description": "idle_phase_description"
        }
      ],
      "fsm_spec": {
        "states": ["IDLE", "WORK", "DONE"],
        "transitions": [
          {"from": "IDLE", "to": "WORK", "condition": "i_valid == 1"},
          {"from": "WORK", "to": "DONE", "condition": "work_done == 1"},
          {"from": "DONE", "to": "IDLE", "condition": "1"}
        ]
      },
      "internal_signals": [
        {
          "name": "state_q",
          "width": 2,
          "description": "FSM_current_state_register"
        }
      ],
      "interface_timing": [
        {
          "signal": "cfg_addr",
          "relative_to": "cfg_we",
          "setup_ns": 1,
          "hold_ns": 1,
          "description": "timing_description"
        }
      ],
      "pipeline_stages_detail": [
        {
          "stage_id": 0,
          "name": "stage_name",
          "operations": ["operation_list"],
          "registers": ["register_list"],
          "stall_condition": "stall_condition_description",
          "flush_condition": "flush_condition_description",
          "input_from": "input_source",
          "output_to": "output_destination"
        }
      ],
      "memory_type": "distributed_ram|lutram|register_file|block_ram",
      "depth": 256,
      "width": 8,
      "reset_behavior": "reset_behavior_description",
      "estimated_complexity": "low|medium|high"
    }
  ],

  "module_connectivity": [
    {
      "source": "source_module.source_port",
      "destination": "destination_module.destination_port",
      "bus_width": 32,
      "connection_type": "direct|pipeline|mux",
      "description": "connection_description"
    }
  ],

  "data_flow_sequences": [
    {
      "name": "main_data_flow",
      "steps": [
        "i_data -> stage0 -> state0",
        "state0 -> stage1 -> state1"
      ],
      "latency_cycles": 2,
      "throughput": "32 bits/cycle",
      "initial_latency_note": "initial_latency_description"
    }
  ],

  "pipeline_stages": [
    {
      "stage_id": 0,
      "name": "stage_name",
      "operations": ["operation_list"]
    }
  ],

  "timing_constraints": [
    {
      "constraint_type": "clock_period",
      "target": "clk",
      "value": 3.33
    }
  ],

  "architecture_summary": "architecture_summary_with_byte_order"
}
```

### 3. Generate Interface Timing Diagram (Optional but Recommended)

Create WaveDrom format interface timing diagram file (.json or .wavedrom) in `stage_1_spec/docs/` directory.

### 4. Module Specification Requirements

- Every module that will generate a .v file must be listed in the `modules` array
- Every port must have complete definition: name, direction, width, protocol, description
- For crypto designs: must include `byte_order` field (MSB_FIRST or LSB_FIRST)
- Must describe byte mapping in architecture_summary
- Must include `pipeline_stages_detail` with stall_condition and flush_condition for each stage
- Must include `module_connectivity` describing inter-module connections
- Must include `data_flow_sequences` describing data flow
- Must include `fsm_spec` (if has FSM) with explicit state enumeration and transition conditions
- Must include `internal_signals` to pre-define internal key registers and wire names to prevent spelling or connection errors
- **architecture_summary must be detailed**: include module partitioning overview, interface descriptions, and interconnection explanation
- **Reset style must match project config**: Read `.veriflow/project_config.json` `coding_style.reset_type` and `coding_style.reset_signal`. Use the configured values in `clock_domains[].reset_port`, `clock_domains[].reset_type`, and port definitions. The JSON template above uses `rst_n`/`async_active_low` as examples — adapt to match your project config.

### 5. Generate Documentation (Optional but Recommended)

Create architecture documentation in `stage_1_spec/docs/`:
- Timing diagram in WaveDrom format (.json or .wavedrom)
- Architecture block diagram or markdown documentation

### 5. Parameterized Mode User Confirmation Points (Parameterized Mode Only)

If execution_mode == "parameterized", use AskUserQuestion to confirm before generating final JSON:

1. Module partitioning confirmation: display suggested module list, ask if needs additions/deletions/modifications
2. Interface definition confirmation: display interface list for each module, confirm signal widths, directions, descriptions
3. Interconnection confirmation: display inter-module connection diagram, confirm data flow direction

## Constraints
- Do NOT create any .v files in this stage
- The spec JSON must be valid JSON (parseable by `json.load()`)
- Every port must have name, direction, width, protocol, and description
- Module names must be snake_case
- One module must have `\"module_type\": \"top\"`
- All fields shown in the JSON example should be included when applicable

## Output
Print a summary: module count, pipeline depth, estimated resource usage, and whether user approvals were obtained (if in parameterized mode).

### After Validation: Confirm to Proceed

After running `validate` and validation passes, read and check the project config:

1. Read `.veriflow/project_config.json` and check the value of `confirm_after_validate`
2. If `confirm_after_validate` is true (or the field doesn't exist):
   - Print a summary of what was accomplished in this stage to the user
   - Use AskUserQuestion tool to ask for confirmation before proceeding to `complete`
   - Question: "Stage 1 validation passed! Do you want to proceed to mark this stage complete?"
   - Options: ["Proceed to complete this stage", "Wait, I want to review the outputs first"]
3. If `confirm_after_validate` is false:
   - Automatically proceed to `complete` without asking for user confirmation

{{EXTRA_CONTEXT}}
