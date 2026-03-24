# VeriFlow 8.2 Architecture Refactoring Summary

## Overview
Completed the Control Flow Inversion architecture refactoring as specified in the plan.

Date: 2026-03-23
Version: 8.2.0

## Changes Made

### 1. Directory Structure (Phase 1 ✅)
- Created `tools/` - ACI tool wrapper layer
- Created `workspace/` with subdirectories:
  - `docs/` - for spec.json
  - `rtl/` - for Verilog source files
  - `sim/` - for simulation outputs

### 2. ACI Tools (Phase 2 ✅)
- `tools/run_lint.sh` - Syntax checking with iverilog
  - Supports mock mode when EDA tools unavailable
  - Returns formatted JSON results
- `tools/run_sim.sh` - Simulation with iverilog + vvp
  - Supports mock mode when EDA tools unavailable
  - Returns PASS/FAIL status with logs

### 3. Prompt Refactoring (Phase 3 ✅)
New prompts (3 instead of 7):
- `stage1_architect.md` - Architecture specification node
- `stage3_coder.md` - RTL code generation node
- `stage4_debugger.md` - Error correction node

Old prompts backed up with `.bak` suffix:
- `stage0_init.md.bak`
- `stage1_spec_quick.md.bak`
- `stage2_timing.md.bak`
- `stage5_synth.md.bak`
- `stage6_close.md.bak`

### 4. Core Controller Rewrite (Phase 4 ✅)
Completely rewrote `veriflow_ctl.py`:

**Removed:**
- All old CLI subcommands (`next`, `validate`, `complete`, `rollback`, `info`)
- Old stage tracking system
- Complex prompt building with templates

**Added:**
- New `run` subcommand as single entry point
- `--mode` parameter support (quick/standard/enterprise)
- `--project-dir` parameter for project location
- Main state machine `run_project(mode, project_dir)`
- `call_claude(prompt_file, context)` function using subprocess
- `stage1_architect()`, `stage3_coder()`, `stage4_simulation_loop()`
- Error handling and retry mechanism in Stage 4
- `run_lint()` and `run_sim()` functions calling ACI tools
- Mock mode for testing without Claude CLI

**Key Functions:**
```python
def run_project(mode, project_dir):
    # Main state machine
    for stage in MODE_STAGES[mode]:
        if stage == 1: stage1_architect(...)
        if stage == 3: stage3_coder(...)
        if stage == 4: stage4_simulation_loop(...)

def call_claude(prompt_file, context):
    # Call Claude CLI via subprocess
    subprocess.run(["claude", "--print", prompt], ...)

def stage4_simulation_loop(...):
    # Debug loop: lint -> if fail -> debugger -> retry
    for iteration in range(max_iterations):
        if run_lint(): break
        else: call_debugger(...)
```

### 5. Documentation Updates (Phase 5 ✅)

**Rewrote `SKILL.md`:**
- Updated to reflect new Control Flow Inversion architecture
- Simplified execution to single `run` command
- Added architecture diagram showing Python as master, LLM as worker
- Updated mode descriptions
- Added tool command reference
- Updated project structure to include workspace/
- Added update log for v8.2.0

**Created `README.md`:**
- Comprehensive documentation with architecture diagram
- Quick start guide
- Installation instructions
- Command reference with examples
- Execution modes comparison table
- State machine flow diagram
- Troubleshooting section
- License and contributing info

## Architecture Comparison

### Old Architecture (v8.1)
```
LLM (via SKILL.md)
    │
    ├── calls "python veriflow_ctl.py next"
    ├── reads prompt from stageX.md
    ├── executes tasks
    ├── calls "python veriflow_ctl.py validate"
    └── calls "python veriflow_ctl.py complete"
```

### New Architecture (v8.2)
```
Python Controller (veriflow_ctl.py)
    │
    ├── calls "claude --print @prompt" (Stage 1 - Architect)
    ├── calls "claude --print @prompt" (Stage 3 - Coder)
    └── enters loop:
            ├── calls "./tools/run_lint.sh"
            ├── if fail: calls "claude --print @prompt" (Stage 4 - Debugger)
            ├── calls "./tools/run_sim.sh"
            └── if fail: calls "claude --print @prompt" (Stage 4 - Debugger)
```

## Key Improvements

| Aspect | v8.1 | v8.2 |
|--------|------|------|
| Control Flow | LLM-driven | Python-driven |
| Prompts | 7 complex prompts | 3 focused prompts |
| Commands | next, validate, complete, rollback, info | run |
| Stage Logic | LLM understands flow | Python controls flow |
| Debug Loop | Manual intervention | Automatic retry with Debugger |
| LLM Interface | CLI commands | Subprocess calls |

## Files Changed

### New Files
- `tools/run_lint.sh` - ACI lint tool
- `tools/run_sim.sh` - ACI simulation tool
- `prompts/stage1_architect.md` - Architect prompt
- `prompts/stage3_coder.md` - Coder prompt
- `prompts/stage4_debugger.md` - Debugger prompt
- `README.md` - Main documentation
- `REFACTOR_SUMMARY.md` - This file

### Modified Files
- `veriflow_ctl.py` - Completely rewritten
- `SKILL.md` - Rewritten for new architecture

### Backup Files (old prompts)
- `prompts/stage0_init.md.bak`
- `prompts/stage1_spec_quick.md.bak`
- `prompts/stage2_timing.md.bak`
- `prompts/stage5_synth.md.bak`
- `prompts/stage6_close.md.bak`

## Testing Recommendations

1. **Basic Test** - Quick mode with simple counter:
   ```bash
   mkdir test_counter && cd test_counter
   echo "# 4-bit Counter\n\nDesign a 4-bit counter." > requirement.md
   python ../veriflow_ctl.py run --mode quick -d .
   ```

2. **Full Test** - Standard mode with AES:
   ```bash
   mkdir test_aes && cd test_aes
   # Create detailed AES requirement.md
   python ../veriflow_ctl.py run --mode standard -d .
   ```

3. **Mock Mode Test** (without Claude CLI):
   - Should automatically use mock execution
   - Check output for "MOCK_MODE" indicators

## Known Limitations

1. **Claude CLI Dependency**: Requires `claude` CLI installed for full functionality. Without it, runs in mock mode.

2. **EDA Tools**: Requires `iverilog` and `vvp` for actual lint/simulation. Without them, runs in mock mode.

3. **Stage 2 and 5**: Timing modeling and synthesis stages are placeholders in this version (marked as TODO for future releases).

4. **Platform**: ACI scripts are bash-based. Windows users need Git Bash or WSL.

## Future Enhancements

1. Implement full Stage 2 (Virtual Timing Modeling) with YAML scenarios
2. Implement full Stage 5 (Synthesis) with Yosys integration
3. Add Stage 6 (Closing) with final reporting
4. Add Windows-native ACI scripts (PowerShell)
5. Add Docker support for reproducible EDA environments
6. Add progress persistence for resuming interrupted pipelines
7. Add parallel execution for independent stages

## Migration Guide (v8.1 → v8.2)

### For Users

**Old way (v8.1):**
```bash
# Multiple commands, driven by LLM
python veriflow_ctl.py next -d ./project
# ... wait for LLM ...
python veriflow_ctl.py validate -d ./project 1
python veriflow_ctl.py complete -d ./project 1
# ... repeat for each stage ...
```

**New way (v8.2):**
```bash
# Single command, Python-driven
python veriflow_ctl.py run --mode quick -d ./project
# Done!
```

### For Developers

**Key changes:**
1. `call_claude()` now uses subprocess instead of being called by user
2. State machine is in Python, not in SKILL.md
3. Prompts are simpler - just the task, no "next/validate/complete" instructions
4. ACI tools are shell scripts called by Python, not run by user

---

## Conclusion

The Control Flow Inversion architecture refactoring has been successfully completed. The new architecture provides:

1. **Simpler UX**: Single `run` command instead of multiple `next/validate/complete`
2. **Better Reliability**: Python-controlled state machine vs LLM-driven flow
3. **Automatic Debugging**: Built-in retry loop with Debugger LLM
4. **Clearer Architecture**: Python as master, LLM as worker, ACI as interface

The refactoring maintains backward compatibility in terms of inputs (still reads `requirement.md`) and outputs (still generates RTL in `workspace/rtl/`), but completely changes the execution model for better reliability and maintainability.
