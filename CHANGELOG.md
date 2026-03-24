# VeriFlow Changelog

## v8.3.1 - 2026-03-24 - 代码质量优化 + verilog_flow 支持库接入

### 接入 verilog_flow/ 支持库
- `project_templates.json` 现在驱动 `MODE_STAGES`，模式配置不再硬编码
- `coding_style/generic/base_style.md` + `templates/generic/*.v` 注入 Stage 3 prompt
  - quick 模式关闭模板注入（节省 token），standard/enterprise 开启
- `arch_spec_v2.json` 用于 `cmd_validate --stage 1` 的 JSON Schema 校验
  - 优先使用 `jsonschema` 库做完整 Draft-7 校验，未安装则 fallback 手动检查
- `kpi.py` 接入 pipeline，记录每个 stage 耗时和成功状态，持久化至 `.veriflow/kpi.json`
  - pipeline 结束时打印本次运行 KPI 汇总 + 历史统计（pass@1 率、timing closure 率）

### 新功能
- `--resume` 标志：跳过 `pipeline_state.json` 中已完成的 stage，支持断点续跑
- Stage 2 支持 `--feedback` 参数，与 Stage 1/3 保持一致
- `cmd_validate` 补全：Stage 2 增加 YAML 内容校验（`design`/`scenarios` 字段）；新增 Stage 2.5/5 支持

### Bug 修复
- `_check_skill_d_gates` / `_print_kpi_dashboard` 直接调用 `sys.exit(1)` 绕过 pipeline 状态保存 → 改为返回 bool
- 非 Windows 路径 `call_claude` 文件句柄未关闭 → 显式 close
- `stage4_simulation_loop` 中 `[B]ack to Stage 2` 选项永远返回 False（死代码）→ 移除

### 代码清理
- 删除未使用的 legacy prompt 文件：`stage3_codegen.md`、`stage4_sim.md`
- 删除根目录空 `workspace/` 文件夹
- 删除过时文档：`README_EN.md`、`REFACTOR_SUMMARY.md`、`request.md`、`SKILL.md`
- 统一延迟 import：`hashlib`、`traceback` 移至顶层；`yaml` 改为可选顶层 import
- 移除 `SKILL_DIR` 冗余别名
- 移除 `run_sim` 内重复 `import tempfile`

---

## v8.3.0 - 2026-03-24 - 完整 5 阶段架构

### 新增
- Stage 2：虚拟时序建模（`timing_model.yaml` + testbench 生成）
- Stage 3.5：Skill D 静态质量分析（逻辑深度/CDC/Latch 风险）
- Stage 2.5：人工门控（Stage 2 后暂停，用户确认行为规格）
- Stage 5：Yosys 综合 + KPI 比对（Enterprise 模式专属）
- Stage 1 交互化：REPL 模式 + 哨兵文件握手协议
- `validate` / `complete` 子命令供 Claude 在 REPL 中自调用
- TB 防篡改保护：Debugger 调用前后 MD5 快照，自动还原

---

## v8.2.0 - 2026-03-23 - 控制权反转架构

### 新增
- Python 主控 + LLM Worker 架构（Control Flow Inversion）
- 三种执行模式：quick / standard / enterprise
- `run` 命令替代旧的 `next/validate/complete`
- `project_templates.json` 定义三种模式完整配置

---

## v8.1.0 - Timing Contract Chain
- 引入 timing_contracts、cycle_behavior_tables 到 Stage 1 spec
- RTL 中强制 TIMING CONTRACT / TIMING SELF-CHECK 注释

## v8.0.0 - Requirement-Driven Verification
- 需求可追溯性与覆盖矩阵
- structured_requirements.json / requirements_coverage_matrix.json

## v7.x 及更早
- 详见 git history


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
