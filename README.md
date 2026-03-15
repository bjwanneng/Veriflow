# VeriFlow-Agent v6.0

工业级 Verilog RTL 设计流水线，采用**脚本编排 + LLM 执行**架构。

## 核心思想

> 确定性的归脚本，创造性的归模型。

| 职责 | 由谁负责 | 为什么 |
|------|---------|--------|
| Stage 顺序控制 | `veriflow_orchestrator.py` | 脚本不会跳过 stage |
| 产出格式校验 | `veriflow_orchestrator.py` | JSON schema / lint / 编译检查 |
| 失败重试 | `veriflow_orchestrator.py` | 最多 3 次，带错误反馈 |
| RTL 代码生成 | Claude Code (LLM) | 创造性任务 |
| Testbench 编写 | Claude Code (LLM) | 创造性任务 |
| 调试修复 | Claude Code (LLM) | 需要理解错误语义 |

## 7-Stage 流水线

```
Stage 0: Project Initialization     — 创建目录、检测工具链
Stage 1: Micro-Architecture Spec    — 生成 JSON 规格文档
Stage 2: Virtual Timing Modeling    — 生成 YAML 时序场景 + golden trace
Stage 3: RTL Code Generation + Lint — 生成 .v 文件、lint、编译
Stage 4: Simulation & Verification  — 单元测试 + 集成测试
Stage 5: Synthesis Analysis          — Yosys 综合分析
Stage 6: Closing                     — 生成最终报告
```

## 快速开始

### 前置条件

- [Claude Code CLI](https://github.com/anthropics/claude-code) 已安装且在 PATH 中
- Python 3.10+
- iverilog + yosys（推荐 [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)）

### 运行完整流水线

```bash
# 在项目目录下放一个 requirement.md 描述设计需求
python veriflow_orchestrator.py --project-dir /path/to/project
```

### 从指定 stage 开始

```bash
# 自动检测上次完成的 stage，从下一个继续
python veriflow_orchestrator.py -d /path/to/project

# 从 Stage 3 开始
python veriflow_orchestrator.py -d /path/to/project --start-stage 3

# 只跑 Stage 4
python veriflow_orchestrator.py -d /path/to/project --stage 4
```

### 预览模式

```bash
python veriflow_orchestrator.py -d /path/to/project --dry-run
```

## 目录结构

```
verilog-flow-skill/
├── SKILL.md                      # Claude Code skill 定义（123 行）
├── veriflow_orchestrator.py      # 主控脚本（471 行）
├── prompts/                      # 每个 stage 的独立 prompt
│   ├── stage0_init.md
│   ├── stage1_spec.md
│   ├── stage2_timing.md
│   ├── stage3_codegen.md
│   ├── stage4_sim.md
│   ├── stage5_synth.md
│   └── stage6_close.md
└── verilog_flow/                 # Python 工具库
    ├── common/
    │   ├── coding_style.py       # 厂商编码风格管理
    │   ├── requirement_validator.py  # 需求预检
    │   ├── stage_gate.py         # Stage 门控检查
    │   └── toolchain_detect.py   # 工具链检测
    ├── stage3/
    │   ├── lint_checker.py       # 17 条 regex lint 规则
    │   └── interface_checker.py  # spec-vs-RTL 端口校验
    ├── defaults/
    │   ├── coding_style/         # generic / xilinx / intel 编码规范
    │   └── templates/            # 11 个可复用 Verilog 模板
    └── cli/main.py               # CLI 工具（validate / waveform / trace）
```

## 项目目录结构（运行后生成）

```
your-project/
├── requirement.md                # 你的设计需求文档
├── stage_1_spec/specs/           # JSON 规格文档
├── stage_2_timing/
│   ├── scenarios/                # YAML 时序场景
│   └── golden_traces/            # 期望值 trace
├── stage_3_codegen/rtl/          # 生成的 .v 文件
├── stage_4_sim/
│   ├── tb/                       # Testbench 文件
│   └── sim_output/               # 仿真日志
├── stage_5_synth/                # 综合脚本和报告
├── reports/                      # 最终报告
└── .veriflow/
    └── stage_completed/          # Stage 完成标记
```

## 与 v5.0 的区别

| 维度 | v5.0 | v6.0 |
|------|------|------|
| 流程控制 | LLM 读 500 行规则自行控制 | Python 脚本硬编码控制 |
| 每次 LLM 上下文 | 500+ 行规则 + 长对话 | ~50 行 stage prompt |
| 产出校验 | 靠 LLM 自觉 | 脚本强制校验（lint/compile/schema） |
| 失败恢复 | LLM 可能越改越乱 | 脚本控制重试 + 错误反馈 |
| Stage 跳过风险 | 高（注意力衰减） | 零（脚本不允许） |

## License

MIT
