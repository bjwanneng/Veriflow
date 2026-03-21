# VeriFlow Changelog

## v8.2.0 - 2026-03-21 - Multi-Mode Architecture

### ✨ New Features

#### 1. Three Execution Modes

- **Quick Mode** (`quick`)
  - Stages: 0 → 1 → 3 → 4 → 6 (5 stages)
  - For: Simple modules, prototyping, quick iteration
  - Features: Minimal validation, no cocotb, no synthesis
  - Time estimate: ~30-60 min for simple designs

- **Standard Mode** (`standard`) - **Default**
  - Stages: 0 → 1 → 2 → 3 → 4 → 5 → 6 (7 stages)
  - For: Most projects, balanced quality and speed
  - Features: Full validation, cocotb, requirements matrix, synthesis
  - Time estimate: 2-4 hours for medium designs

- **Enterprise Mode** (`enterprise`)
  - Stages: All 7 stages with sub-stages (1.5, 3.5)
  - For: Critical projects, high-reliability designs
  - Features: Code review, formal verification, multi-seed regression, power analysis
  - Time estimate: 1-2 days for complex designs

#### 2. Mode-Aware Validation

- Validation rules defined per mode in `VALIDATION_RULES`
- Minimal: Basic file existence and compilation checks
- Standard: Full quality gates (spec validity, lint, simulation)
- Strict: Enterprise gates (reviews, formal checks, coverage)

#### 3. Mode-Specific Prompts

- Quick mode uses concise prompts (~2000 tokens)
- Standard mode uses full prompts (~4000 tokens)
- Enterprise mode uses detailed prompts with examples (~8000 tokens)
- New `stage1_spec_quick.md` for fast specification

#### 4. Project Configuration Templates

- New `verilog_flow/defaults/project_templates.json`
- Defines all three modes with complete settings
- Includes validation levels, features, prompt styles

#### 5. New Commands

- `veriflow_ctl.py init` - Initialize project with mode selection
- `veriflow_ctl.py mode` - Get or set current mode

### 🔧 Improvements

#### Simplified SKILL.md

- Reduced verbosity by ~60%
- Removed mandatory "speak out loud" requirements
- Clear, concise 4-step loop
- Mode selection guidance

#### Streamlined Controller

- `veriflow_ctl.py` rewritten for multi-mode support
- Mode-aware validation and prompting
- Cleaner code structure

### 🐛 Bug Fixes

- Fixed: Prompt builder now correctly filters content by mode
- Fixed: Validation correctly checks mode-specific requirements

### 📁 New Files

```
verilog_flow/defaults/project_templates.json   # Mode definitions
prompts/stage1_spec_quick.md                     # Quick mode Stage 1
CHANGELOG.md                                      # This file
```

### 📝 Modified Files

```
SKILL.md                   # Simplified, multi-mode documentation
veriflow_ctl.py            # Rewritten for multi-mode support
prompts/stage0_init.md      # Updated with mode selection
```

### 🔜 Migration Guide

For existing projects:

```bash
# Check current config
python veriflow_ctl.py mode -d ./my_project

# Switch to quick mode for faster iteration
python veriflow_ctl.py mode -d ./my_project quick

# Or keep standard mode (default)
python veriflow_ctl.py mode -d ./my_project standard
```

### 📊 Performance Comparison

| Mode | Stages | Avg Time | Best For |
|------|--------|----------|----------|
| Quick | 5 | 30-60 min | Simple modules, prototypes |
| Standard | 7 | 2-4 hrs | Most designs, default choice |
| Enterprise | 7+ | 1-2 days | Critical, high-reliability |

---

## Previous Versions

### v8.1.0 - Timing Contract Chain
- Introduced full-link timing quality improvements
- Added timing_contracts, cycle_behavior_tables to Stage 1 spec
- Required TIMING CONTRACT / TIMING SELF-CHECK comments in Stage 3 RTL

### v8.0.0 - Requirement-Driven Verification
- Added requirements traceability and coverage matrix
- structured_requirements.json in Stage 1
- requirements_coverage_matrix.json in Stage 2
- requirements_coverage_report.json in Stage 4

### v7.x and earlier
- See git history for earlier changes
