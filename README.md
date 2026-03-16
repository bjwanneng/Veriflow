# VeriFlow-Agent v8.0

工业级 Verilog RTL 设计流水线 — **脚本做门禁，LLM 做执行**。

## 核心架构

```
Claude Code (LLM)          veriflow_ctl.py (脚本)
    │                            │
    │  1. 调用 next             │
    │ ─────────────────────────>│ 检查前置 stage → 输出 prompt
    │                            │
    │  2. 执行 stage 任务        │
    │  (生成代码/spec/TB...)     │
    │                            │
    │  3. 调用 validate          │
    │ ─────────────────────────>│ 确定性检查 → PASS/FAIL
    │                            │
    │  4. 调用 complete          │
    │ ─────────────────────────>│ 验证通过才标记完成
    │                            │
    │  回到 1                    │
```

LLM 负责创造性工作（写 Verilog、设计架构、调试），脚本负责"能不能过"的硬判断。LLM 无法跳过 stage、无法绕过验证。

## 7-Stage 流水线

| Stage | 名称 | 关键产出 |
|-------|------|----------|
| 0 | Project Initialization | 目录结构, project_config.json |
| 1 | Micro-Architecture Spec | `stage_1_spec/specs/*_spec.json` |
| 2 | Virtual Timing Modeling | YAML 场景, golden trace, Cocotb 测试 |
| 3 | RTL Code Generation + Lint | `stage_3_codegen/rtl/*.v`, 自动 testbench |
| 4 | Simulation & Verification | 单元/集成测试, 仿真日志 (全 PASS) |
| 5 | Synthesis Analysis | Yosys 综合, synth_report.json |
| 6 | Closing | `reports/final_report.md` |

## 使用方式

### 前置条件

- Claude Code CLI 已安装
- Python 3.10+
- iverilog + yosys（推荐 [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)）

### 作为 Claude Code Skill 使用（推荐）

1. 将本目录放在 `~/.claude/skills/verilog-flow-skill/`
2. 在项目目录下创建 `requirement.md` 描述设计需求
3. 在 Claude Code 中提及 Verilog/RTL 设计，skill 自动触发
4. Claude Code 按照 SKILL.md 中的循环协议自动执行全流程

### 手动使用 veriflow_ctl.py

```bash
CTL="~/.claude/skills/verilog-flow-skill/veriflow_ctl.py"

# 查看进度
python $CTL status -d ./my_project

# 获取下一个 stage 的任务 prompt
python $CTL next -d ./my_project

# 验证 stage 产出
python $CTL validate -d ./my_project 3

# 标记 stage 完成（验证不过会拒绝）
python $CTL complete -d ./my_project 3

# 回退到某个 stage
python $CTL rollback -d ./my_project 1

# 查看 stage 详情
python $CTL info -d ./my_project 3
```

## 目录结构

```
verilog-flow-skill/
├── SKILL.md                          # Claude Code skill 定义
├── veriflow_ctl.py                   # 门禁控制器（status/next/validate/complete/rollback）
├── prompts/                          # 每个 stage 的任务 prompt
│   ├── stage0_init.md
│   ├── stage1_spec.md
│   ├── stage2_timing.md
│   ├── stage3_codegen.md
│   ├── stage4_sim.md
│   ├── stage5_synth.md
│   └── stage6_close.md
└── verilog_flow/
    ├── common/
    │   ├── kpi.py                    # KPI 追踪（Pass@1, 时序收敛率）
    │   └── experience_db.py          # 经验库（失败案例记录与检索）
    ├── defaults/
    │   ├── coding_style/             # generic / xilinx / intel 编码规范
    │   └── templates/                # 11 个可复用 Verilog 模板
    └── stage1/schemas/
        └── arch_spec_v2.json         # 架构规格 JSON Schema
```

## 项目目录结构（运行后生成）

```
your-project/
├── requirement.md                    # 设计需求文档（用户提供）
├── stage_1_spec/specs/               # JSON 架构规格
├── stage_2_timing/
│   ├── scenarios/                    # YAML 时序场景
│   ├── golden_traces/                # 期望值 trace
│   └── cocotb/                       # Cocotb 测试文件
├── stage_3_codegen/
│   ├── rtl/                          # 生成的 .v 文件
│   └── tb_autogen/                   # 自动生成的 testbench
├── stage_4_sim/
│   ├── tb/                           # Testbench 文件
│   └── sim_output/                   # 仿真日志
├── stage_5_synth/                    # 综合脚本和报告
├── reports/                          # 最终报告 + stage 摘要
└── .veriflow/
    └── stage_completed/              # Stage 完成标记（门禁依据）
```

## License

MIT
