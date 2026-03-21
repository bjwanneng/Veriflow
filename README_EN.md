# VeriFlow-Agent v8.2

Industrial-grade Verilog RTL design pipeline — **Script as gatekeeper, LLM as executor.**

Cross-platform: Linux / macOS / Windows (Git Bash, MSYS2, native CMD)

## Architecture

```
Claude Code (LLM)          veriflow_ctl.py (Script)
    |                            |
    |  1. call next             |
    | =========================>| Check prerequisites -> output prompt
    |                            |
    |  2. Execute stage tasks    |
    |  (generate code/spec/TB..)|
    |                            |
    |  3. call validate          |
    | =========================>| Deterministic checks -> PASS/FAIL
    |                            |
    |  4. call complete          |
    | =========================>| Mark done only if validation passed
    |                            |
    |  Back to 1                 |
```

The LLM handles creative work (writing Verilog, designing architecture, debugging). The script handles hard pass/fail decisions. The LLM cannot skip stages or bypass validation.

## Three Execution Modes (v8.2 New Feature)

| Mode | Stages | Use Case | Validation Level | Typical Time |
|------|--------|----------|------------------|--------------|
| **Quick** | 0→1→3→4→6 (5 stages) | Simple modules, prototyping, fast iteration | Minimal | 30-60 minutes |
| **Standard** | 0→1→2→3→4→5→6 (7 stages) | Most projects, recommended default | Standard | 2-4 hours |
| **Enterprise** | 7+ stages with sub-stages | Critical projects, industrial quality | Strict | 1-2 days |

### Stage Flow Comparison

| Stage | Quick | Standard | Enterprise | Description |
|-------|-------|----------|------------|-------------|
| 0 | ✅ | ✅ | ✅ | Project Initialization |
| 1 | ✅(simplified) | ✅ | ✅(with review) | Architecture Spec |
| 1.5 | ❌ | ❌ | ✅ | Architecture Review |
| 2 | ❌ | ✅ | ✅ | Virtual Timing Modeling |
| 3 | ✅ | ✅ | ✅(with review) | RTL Code Generation |
| 3.5 | ❌ | ❌ | ✅ | Code Review & Optimization |
| 4 | ✅(simplified) | ✅ | ✅ | Simulation Verification |
| 5 | ❌ | ✅ | ✅ | Synthesis Analysis |
| 6 | ✅ | ✅ | ✅ | Project Closing |

## 7-Stage Pipeline

| Stage | Name | Key Output |
|-------|------|------------|
| 0 | Project Initialization | Directory structure, project_config.json |
| 1 | Micro-Architecture Spec | `*_spec.json`, `structured_requirements.json` |
| 2 | Virtual Timing Modeling | YAML scenarios, golden traces, Cocotb tests, `requirements_coverage_matrix.json` |
| 3 | RTL Code Generation + Lint | `stage_3_codegen/rtl/*.v`, auto testbenches |
| 4 | Simulation & Verification | Unit/integration tests, sim logs, `requirements_coverage_report.json` |
| 5 | Synthesis Analysis | Yosys synthesis, synth_report.json |
| 6 | Closing | `reports/final_report.md` |

## What's New in v8.2

### Multi-Mode Architecture (v8.2.0)

**Three Execution Modes**:
- **Quick Mode**: 5 stages (0→1→3→4→6), skips timing modeling and synthesis, ideal for fast prototyping
- **Standard Mode**: 7 complete stages, recommended default
- **Enterprise Mode**: with sub-stages (1.5 architecture review, 3.5 code review), strict validation

**Mode-Aware Validation**:
- Minimal: Basic file existence and compilation checks
- Standard: Full quality gates (spec validity, lint, simulation)
- Strict: Enterprise gates (reviews, formal checks, coverage)

**New Commands**:
- `veriflow_ctl.py init` - Interactive project initialization with mode selection
- `veriflow_ctl.py mode` - Get or set current mode

### Requirements-Driven Verification — Traceability + Coverage Matrix

Before v8.2, `requirement.md` was only read in Stage 0/1 and then lost. Cocotb tests were generic (data_range, protocol_corner_cases) without extracting specific functional points, performance metrics, or interface constraints from requirements. v8.2 establishes full traceability from requirements to verification.

**Stage 1: Requirements Structuring**
- New Task 0 (before architecture analysis): parse requirement.md → `structured_requirements.json`
- Clarity check: evaluates completeness across functional/performance/interface/constraints; asks user to revise if vague
- Each requirement has `req_id` (REQ-{FUNC|PERF|IF|CONS}-NNN), `category`, `testable`, `acceptance_criteria`
- Validator checks: valid JSON, non-empty requirements, at least 1 functional, testable requirements have acceptance_criteria

**Stage 2: Requirements Coverage Matrix**
- requirement.md injected into Stage 2 prompt via `{{REQUIREMENT}}` placeholder
- New Section 3.5: generates `requirements_coverage_matrix.json`, mapping each testable requirement to cocotb tests, coverpoints, YAML scenarios
- CoverageCollector adds requirement-derived coverpoints (functional→operation coverage, performance→metric coverage, interface→protocol coverage)
- test_integration.py updates matrix status after test execution
- Validator checks: non-empty matrix, each entry has cocotb_tests, coverage_pct > 0

**Stage 4: Requirements Coverage Report**
- New Part E Step 16: generates `requirements_coverage_report.json`
- Summarizes verification status (verified/failed/not_run) per requirement, with per-category coverage stats
- Validator checks: requirements_coverage_pct > 0

**Data Flow**:
```
requirement.md
    ↓ (Stage 1)
structured_requirements.json    ←── Requirements structuring
    ↓ (Stage 2)
requirements_coverage_matrix.json  ←── Requirements → test mapping
    ↓ (Stage 4)
requirements_coverage_report.json  ←── Verification results summary
```

## What's New in v8.1

### Cross-Platform Compatibility
- Controller forces UTF-8 stdout/stderr on startup, fixing `UnicodeEncodeError` on Windows GBK terminals
- Toolchain detection (`_get_toolchain_env`) auto-searches common install paths on Windows / macOS (Homebrew) / Linux
- `iverilog` compile check uses `tempfile` instead of platform-specific `/dev/null` vs `NUL`
- `requirement.md` reading supports encoding auto-detection (utf-8 -> utf-8-sig -> gbk -> gb2312 -> latin-1)
- All prompt templates use file redirection (`> file.log 2>&1`) instead of `tee`/`head`/`timeout`

### Configurable Coding Style
- Reset signal type and name are read from `project_config.json` `coding_style` field, no longer hardcoded to `rst_n`
- Supports 4 reset styles: `async_active_low`, `async_active_high`, `sync_active_low`, `sync_active_high`
- `build_prompt()` automatically injects `coding_style` config into the `{{CODING_STYLE}}` placeholder
- All prompt templates (stage1~stage4) include instructions to read reset config from project config

### Enhanced Validation
- Stage 3: testbench reset signal check supports multiple reset names (`rst`, `rst_n`, `reset`)
- Stage 4: simulation log verification now checks for positive completion indicators (`ALL TESTS PASSED`, `PASSED`, etc.)
- `glob()` results wrapped with `list()`, fixing `TypeError` on Python 3.12+

### Safe Output
- All emoji characters in summary generators replaced with ASCII equivalents ([DONE], [OK], [WARN])

## Getting Started

### Prerequisites

- Claude Code CLI installed
- Python 3.10+
- iverilog + yosys (recommended: [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build))

### Toolchain Search Paths

The controller automatically searches these paths:

| Platform | Search Paths |
|----------|-------------|
| Windows | `C:/oss-cad-suite/bin`, `C:/oss-cad-suite/lib` |
| macOS | `/opt/homebrew/bin`, `/usr/local/bin` |
| Linux | `/opt/oss-cad-suite/bin`, `/usr/bin` |
| Universal | `~/oss-cad-suite/bin`, `~/oss-cad-suite/lib` |

If tools are not in the above paths, add them manually:
```bash
# Windows (Git Bash / MSYS2)
export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
# macOS
export PATH="/opt/homebrew/bin:$PATH"
# Linux
export PATH="/opt/oss-cad-suite/bin:$PATH"
```

### As a Claude Code Skill (Recommended)

1. Place this directory at `~/.claude/skills/verilog-flow-skill/`
2. Create a `requirement.md` in your project directory describing the design
3. Mention Verilog/RTL design in Claude Code — the skill triggers automatically
4. Claude Code follows the loop protocol in SKILL.md to execute the full pipeline

### Manual Usage with veriflow_ctl.py

```bash
CTL="~/.claude/skills/verilog-flow-skill/veriflow_ctl.py"

# Initialize new project (interactive wizard with mode selection)
python "$CTL" init -d ./my_project

# View/switch execution mode
python "$CTL" mode -d ./my_project              # View current mode
python "$CTL" mode -d ./my_project quick        # Switch to Quick mode
python "$CTL" mode -d ./my_project standard     # Switch to Standard mode
python "$CTL" mode -d ./my_project enterprise   # Switch to Enterprise mode

# Check progress
python "$CTL" status -d ./my_project

# Get the next stage's task prompt
python "$CTL" next -d ./my_project

# Validate stage output
python "$CTL" validate -d ./my_project 3

# Mark stage complete (refused if validation fails)
python "$CTL" complete -d ./my_project 3

# Rollback to a previous stage
python "$CTL" rollback -d ./my_project 1

# View stage details
python "$CTL" info -d ./my_project 3
```

## Coding Style Configuration

During Stage 0 initialization, a `coding_style` field is written to `.veriflow/project_config.json`:

```json
{
  "coding_style": {
    "reset_type": "sync_active_high",
    "reset_signal": "rst",
    "clock_edge": "posedge",
    "naming": "snake_case",
    "port_style": "ANSI",
    "indent": 4
  }
}
```

Supported `reset_type` values:
- `async_active_low` — Async active-low (`rst_n`), default
- `async_active_high` — Async active-high (`rst`)
- `sync_active_low` — Sync active-low (`rst_n`)
- `sync_active_high` — Sync active-high (`rst`)

All subsequent stages (spec generation, RTL coding, testbenches, validation) read the reset style from this config, ensuring consistency across the entire pipeline.

## Directory Structure

```
verilog-flow-skill/
├── SKILL.md                          # Claude Code skill entry point
├── README.md                         # Chinese documentation
├── README_EN.md                      # English documentation
├── CHANGELOG.md                      # Changelog
├── readme_first.md                   # Project status memo
├── veriflow_ctl.py                   # Gate controller v8.2 (cross-platform)
├── prompts/                          # Task prompts for each stage
│   ├── stage0_init.md
│   ├── stage1_spec.md
│   ├── stage1_spec_quick.md         # Quick mode simplified version
│   ├── stage2_timing.md
│   ├── stage3_codegen.md
│   ├── stage4_sim.md
│   ├── stage5_synth.md
│   └── stage6_close.md
└── verilog_flow/
    ├── common/
    │   ├── kpi.py                    # KPI tracking (Pass@1, timing convergence)
    │   └── experience_db.py          # Experience DB (failure case recording & retrieval)
    └── defaults/
        ├── coding_style/             # generic / xilinx / intel coding standards
        ├── templates/                # Reusable Verilog templates
        └── project_templates.json    # Three mode configuration templates
```

## Project Directory Structure (Generated at Runtime)

```
your-project/
├── requirement.md                    # Design requirements (user-provided)
├── .veriflow/
│   ├── project_config.json           # Project config (includes coding_style)
│   └── stage_completed/              # Stage completion markers (gate control)
├── stage_1_spec/specs/               # JSON architecture spec + structured_requirements.json
├── stage_2_timing/
│   ├── scenarios/                    # YAML timing scenarios
│   ├── golden_traces/                # Expected value traces
│   └── cocotb/                       # Cocotb test files + requirements_coverage_matrix.json
├── stage_3_codegen/
│   ├── rtl/                          # Generated .v files
│   ├── tb_autogen/                   # Auto-generated testbenches
│   └── reports/                      # Lint reports
├── stage_4_sim/
│   ├── tb/                           # Unit/integration testbenches
│   ├── sim_output/                   # Simulation logs
│   ├── cocotb_regression/            # Cocotb regression tests
│   ├── coverage/                     # VCD waveform files
│   └── requirements_coverage_report.json  # Requirements coverage report
├── stage_5_synth/                    # Synthesis scripts, netlist, reports
└── reports/                          # Final report + stage summaries
```

## License

MIT
