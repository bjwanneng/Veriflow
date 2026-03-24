# VeriFlow 项目状态备忘

> 每次打开项目时先读此文件，快速恢复上下文。

---

## 当前版本

**v8.3.1** — 2026-03-24

---

## 项目架构

控制权反转（Control Flow Inversion）：Python 主控状态机 + LLM Worker 节点。

```
veriflow_ctl.py          ← 唯一入口，主控所有阶段
prompts/                 ← 每个 stage 的 LLM 工作指令
tools/                   ← EDA 工具封装（iverilog / Yosys）
verilog_flow/
  common/kpi.py          ← KPI 追踪（已接入 pipeline）
  defaults/
    project_templates.json  ← 模式配置（驱动 MODE_STAGES）
    coding_style/generic/   ← 风格指南（注入 Stage 3）
    templates/generic/      ← Verilog 模板（注入 Stage 3）
  stage1/schemas/arch_spec_v2.json  ← spec.json schema 校验
```

---

## 阶段流程

| 模式 | 阶段序列 |
|------|---------|
| quick | 1 → 3 → 4(lint-only) |
| standard | 1 → 2 → 2.5 → 3 → 3.5 → 4(sim) |
| enterprise | 1 → 2 → 2.5 → 3 → 3.5 → 4(sim) → 5 |

阶段编号说明：
- **1** Architect（REPL 交互，生成 spec.json）
- **2** Timing Model（生成 timing_model.yaml + testbench）
- **2.5** Human Gate（人工审查 timing model）
- **3** RTL Coder（逐模块生成 Verilog）
- **3.5** Skill D（静态质量分析）
- **4** Simulation Loop（lint + 仿真，Debugger 自动修复）
- **5** Yosys Synthesis + KPI（Enterprise 专属）

---

## 关键文件

| 文件 | 用途 |
|------|------|
| `veriflow_ctl.py` | 主控制器（~2100 行） |
| `prompts/stage1_architect.md` | Stage 1 REPL 指令 |
| `prompts/stage2_timing.md` | Stage 2 时序建模指令 |
| `prompts/stage3_coder.md` | Stage 3 全量生成（含 {{CODING_STYLE}} / {{VERILOG_TEMPLATES}}） |
| `prompts/stage3_module.md` | Stage 3 单模块生成（同上） |
| `prompts/stage35_skill_d.md` | Stage 3.5 静态分析指令 |
| `prompts/stage4_debugger.md` | Stage 4 调试修复指令 |
| `README.md` | 用户文档（中文） |
| `CHANGELOG.md` | 版本变更记录 |
| `CLAUDE.md` | Claude Code 工作指引 |

---

## v8.3.1 主要改动（本次会话完成）

**代码优化（veriflow_ctl.py）：**
- 修复 `sys.exit()` 绕过 pipeline 状态保存的 bug
- 修复非 Windows 文件句柄泄漏
- 移除死代码（`[B]ack` 选项、`SKILL_DIR` 别名、重复 import）
- 统一延迟 import 到顶层（hashlib / traceback / yaml）

**功能接入：**
- `project_templates.json` → 驱动 `MODE_STAGES`
- `coding_style/` + `templates/` → 注入 Stage 3 prompt 上下文
- `arch_spec_v2.json` → Stage 1 validate 做 JSON Schema 校验
- `kpi.py` → pipeline 全程记录 metrics，结束时打印汇总

**新功能：**
- `--resume`：断点续跑，跳过已完成 stage
- Stage 2 支持 `--feedback` 参数
- `cmd_validate` 补全 Stage 2 内容校验 + Stage 2.5/5 支持

**文档清理：**
- 删除：`README_EN.md` / `REFACTOR_SUMMARY.md` / `request.md` / `SKILL.md`
- 删除：legacy prompt 文件（`stage3_codegen.md` / `stage4_sim.md`）
- 删除：根目录空 `workspace/` 文件夹

---

## 待办事项

- [ ] `jsonschema` 库未在 requirements 中声明（可选依赖，需补充说明）
- [ ] `verilog_flow/common/experience_db.py` 仍未接入（经验数据库，中期规划）
- [ ] Stage 1 超时（3600s）不可配置，可考虑加 `--timeout` 参数
- [ ] Enterprise 模式子阶段（1.5 架构评审）尚未实现（`project_templates.json` 中 enterprise 的 stages 列表暂用 Python 默认值，不从 JSON 加载）

---

## 常用命令

```bash
# 运行流水线
python veriflow_ctl.py run --mode standard -d ./my_project

# 断点续跑
python veriflow_ctl.py run --mode standard -d ./my_project --resume

# 带反馈修订
python veriflow_ctl.py run --mode standard -d ./my_project --feedback feedback.md

# 只重新生成某个模块
python veriflow_ctl.py run --mode standard -d ./my_project --stages 3 --modules uart_tx

# 验证某阶段输出
python veriflow_ctl.py validate --stage 1 -d ./my_project
```
