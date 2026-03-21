# Stage 1: Micro-Architecture Specification (Quick Mode)

Create a simplified architecture specification for the design.

## Working Directory
{{PROJECT_DIR}}

## Requirements
{{REQUIREMENT}}

## Tasks

### 1. Read Requirements

Read `requirement.md` and extract:
- Design name and purpose
- Key functionality
- Interface requirements (ports, protocols)
- Target frequency (default: 300MHz if not specified)

### 2. Define Module Structure

Identify modules needed:
- Top module name
- Sub-modules (if any)
- Module hierarchy

### 3. Generate Specification JSON

Create `stage_1_spec/specs/{design_name}_spec.json`:

```json
{
  "design_name": "module_name",
  "description": "Brief description of what this module does",
  "target_frequency_mhz": 300,
  "modules": [
    {
      "name": "module_name",
      "description": "Module functionality",
      "module_type": "top",
      "ports": [
        {
          "name": "clk",
          "direction": "input",
          "width": 1,
          "protocol": "clock"
        },
        {
          "name": "rst_n",
          "direction": "input",
          "width": 1,
          "protocol": "reset"
        },
        {
          "name": "i_data",
          "direction": "input",
          "width": 32,
          "protocol": "data"
        },
        {
          "name": "o_data",
          "direction": "output",
          "width": 32,
          "protocol": "data"
        }
      ]
    }
  ]
}
```

### 4. Create Architecture Document (Optional but Recommended)

Create `stage_1_spec/docs/architecture.md` with:
- Design overview
- Module block diagram (text-based)
- Key algorithms or state machines
- Interface descriptions

## Constraints (Quick Mode)

- Verilog-2005 only (no SystemVerilog)
- Async active-low reset (rst_n)
- ANSI-style port declarations
- Snake_case for signals, UPPER_SNAKE_CASE for parameters

## Output Checklist

- [ ] `stage_1_spec/specs/*_spec.json` created with valid JSON
- [ ] Module name matches design
- [ ] Ports defined with direction, width, protocol
- [ ] Clock and reset ports specified
