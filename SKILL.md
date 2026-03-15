---
name: verilog-flow-skill
description: Industrial-grade Verilog design pipeline with script-controlled orchestration and LLM-executed stages. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when the user mentions Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "6.0.0"
  category: hardware-design
---

# VeriFlow-Agent 6.0 — Orchestrator Architecture

## Architecture Change (v6.0)

Previous versions (v3–v5) relied on the LLM to control the entire 7-stage workflow via prompt rules. This caused:
- Stage skipping and rule violations in long conversations
- Attention decay on 500+ lines of rules
- Inconsistent output formats

**v6.0 solution**: A Python orchestrator script controls stage sequencing and validation. Claude Code acts as the execution agent within each stage, receiving a focused, short prompt with only the rules relevant to that stage.

```
veriflow_orchestrator.py (deterministic control)
  ├── Stage 0: claude -p prompts/stage0_init.md
  │   └── validate_stage(0) ← script checks dirs/config exist
  ├── Stage 1: claude -p prompts/stage1_spec.md
  │   └── validate_stage(1) ← script checks JSON schema + requirement validation
  ├── Stage 2: claude -p prompts/stage2_timing.md
  │   └── validate_stage(2) ← script checks YAML scenarios exist
  ├── Stage 3: claude -p prompts/stage3_codegen.md
  │   └── validate_stage(3) ← script runs lint + iverilog compilation
  ├── Stage 4: claude -p prompts/stage4_sim.md
  │   └── validate_stage(4) ← script checks sim logs for PASS/FAIL
  ├── Stage 5: claude -p prompts/stage5_synth.md
  │   └── validate_stage(5) ← script checks synthesis output
  └── Stage 6: claude -p prompts/stage6_close.md
      └── validate_stage(6) ← script checks final report
```

## How to Use

### Option A: Run the full pipeline
```bash
python veriflow_orchestrator.py --project-dir /path/to/project
```

### Option B: Run a single stage
```bash
python veriflow_orchestrator.py --project-dir /path/to/project --stage 3
```

### Option C: Resume from last completed stage
```bash
python veriflow_orchestrator.py --project-dir /path/to/project
# Auto-detects last completed stage and continues from there
```

### Option D: Use within Claude Code session (manual mode)
If the user invokes this skill within a Claude Code session (not via the orchestrator), follow these rules:

1. Check `.veriflow/stage_completed/` to find the last completed stage
2. Read the appropriate prompt file from `prompts/stageN_*.md`
3. Execute that stage's tasks
4. The orchestrator's validation logic is in `veriflow_orchestrator.py` — you can read it to understand what will be checked

## Key Design Principles

1. **Script controls flow** — stage ordering, retry logic, and validation are deterministic
2. **LLM controls content** — RTL generation, testbench creation, debugging are creative tasks for the agent
3. **Short focused prompts** — each stage prompt is ~50 lines, not 500
4. **Validation between stages** — script catches errors before they propagate
5. **Retry with feedback** — if validation fails, the error is fed back to the LLM for correction (max 3 retries)

## File Layout

```
verilog-flow-skill/
├── SKILL.md                          ← this file
├── veriflow_orchestrator.py          ← main orchestrator script
├── prompts/
│   ├── stage0_init.md                ← focused prompt for Stage 0
│   ├── stage1_spec.md                ← focused prompt for Stage 1
│   ├── stage2_timing.md              ← focused prompt for Stage 2
│   ├── stage3_codegen.md             ← focused prompt for Stage 3
│   ├── stage4_sim.md                 ← focused prompt for Stage 4
│   ├── stage5_synth.md               ← focused prompt for Stage 5
│   └── stage6_close.md               ← focused prompt for Stage 6
└── verilog_flow/                     ← Python utilities (lint, validation, etc.)
    ├── common/
    │   ├── requirement_validator.py  ← pre-generation spec validation
    │   ├── stage_gate.py             ← stage gate checks
    │   └── lint_checker.py → stage3/
    ├── stage3/
    │   ├── lint_checker.py           ← 17-rule regex lint
    │   └── interface_checker.py      ← spec-vs-RTL port validation
    └── defaults/
        ├── coding_style/             ← vendor coding style docs
        └── templates/                ← reusable Verilog templates
```

## Coding Style (Quick Reference)

For the LLM agent within each stage:

- Verilog-2005 only (no SystemVerilog)
- `resetall` / `timescale 1ns/1ps` / `default_nettype none` / module / endmodule / `resetall`
- Async active-low reset: `always @(posedge clk or negedge rst_n)`
- snake_case signals, UPPER_CASE parameters, ANSI ports, 4-space indent
- Combinational: `always @*` with `=`, sequential: `<=`
- `output wire` + `assign`, never `output reg`
- No placeholders, no TODO, no truncated lookup tables
- Crypto modules: document byte order in comments

## Error Reference

| Error | Fix |
|-------|-----|
| `cannot be driven by continuous assignment` | Change `reg` to `wire` |
| `Unable to bind wire/reg/memory` | Move declaration before use |
| `Variable declaration in unnamed block` | Name the block or move to module level |
| Simulation hangs | Add `$finish` and timeout watchdog |
| NIST test vector fails | Check byte order: s[0]=[127:120], s[15]=[7:0] |
| Exit code 127 on Windows | Add oss-cad-suite/lib to PATH |
