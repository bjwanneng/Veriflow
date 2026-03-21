# Stage 0: Project Initialization

Initialize the VeriFlow project with mode selection and configuration.

## Working Directory
{{PROJECT_DIR}}

## Tasks

### 1. Mode Selection (Required)

Ask the user to select execution mode using AskUserQuestion:

**Question**: "Select execution mode for this project"

**Options**:
- **Quick**: Fast mode for simple modules and prototyping. Stages: 0→1→3→4→6. Minimal validation, no cocotb.
- **Standard**: Recommended for most projects. Full 7-stage pipeline with complete validation.
- **Enterprise**: Industrial-grade with strict validation, code reviews, formal verification.

**Default**: Standard

### 2. Configuration Confirmation

Based on selected mode, confirm key settings:

**Question**: "Confirm project configuration"

Settings to display:
- **Mode**: [selected mode]
- **Validation Level**: [minimal/standard/strict]
- **Testbench Depth**: [minimal/standard/thorough]
- **Features**: [list enabled features like cocotb, timing contracts, etc.]

**Options**:
- Accept and proceed
- Go back to change mode

### 3. Create Project Configuration

Create `.veriflow/project_config.json`:

```json
{
  "project": "{{PROJECT_NAME}}",
  "version": "8.2.0",
  "mode": "[selected_mode]",
  "target_frequency_mhz": 300,
  "vendor": "generic",
  "created_at": "[ISO8601 timestamp]",
  "toolchain": {
    "iverilog": "[version]",
    "yosys": "[version]"
  },
  "features": {
    "cocotb": [true/false],
    "timing_contracts": [true/false],
    "requirements_matrix": [true/false],
    "uvm_like_lib": [true/false],
    "synthesis": [true/false]
  },
  "validation_level": "[minimal/standard/strict]",
  "testbench_depth": "[minimal/standard/thorough]",
  "confirm_after_validate": false,
  "coding_style": {
    "reset_type": "async_active_low",
    "reset_signal": "rst_n",
    "clock_edge": "posedge",
    "naming": "snake_case",
    "port_style": "ANSI",
    "indent": 4
  }
}
```

### 4. Copy veriflow_ctl.py to Project Directory

**CRITICAL**: Copy the veriflow_ctl.py script from the skill directory to the project directory so it can be run easily.

First, find the skill directory (where this prompt is located), then copy:
```bash
# From the skill directory, copy to project
cp veriflow_ctl.py "{{PROJECT_DIR}}/"
```

### 5. Create Directory Structure

Create directories based on selected mode:

**Common (all modes)**:
- `stage_1_spec/specs/`
- `stage_1_spec/docs/`
- `stage_3_codegen/rtl/`
- `stage_3_codegen/tb_autogen/`
- `stage_4_sim/tb/`
- `stage_4_sim/sim_output/`
- `.veriflow/stage_completed/`
- `reports/`

**Standard/Enterprise only**:
- `stage_2_timing/scenarios/`
- `stage_2_timing/golden_traces/`
- `stage_2_timing/cocotb/`
- `stage_5_synth/`

### 5. Check requirement.md

Verify that `requirement.md` exists in the project directory. If not, warn the user:

```
⚠️  Warning: requirement.md not found in project directory.
   Please create requirement.md before proceeding to Stage 1.
```

## Output

Print summary:
```
================================================================
  Stage 0: Project Initialization - COMPLETE
================================================================

Configuration:
  Mode: [selected_mode]
  Project: [project_name]
  Target Frequency: 300 MHz

Directories Created:
  [list of created directories]

Features Enabled:
  [list of enabled features]

Next Steps:
  1. Review requirement.md
  2. Run: python veriflow_ctl.py next -d [project_dir]

================================================================
```

{{EXTRA_CONTEXT}}
