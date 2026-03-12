# VeriFlow-Agent 3.0 使用指南

工业级 Verilog 代码生成系统，具有时序和微架构感知能力。

---

## 概述

VeriFlow-Agent 3.0 解决了 Verilog 代码生成中的常见问题：**"逻辑正确，物理失败"**。通过"左移"理念，将微架构规划和物理时序估计提前至代码生成之前。

### 核心特性

- **5 阶段流水线**：从需求到综合的完整工作流程
- **YAML DSL**：参数化的时序场景描述
- **Golden Trace**：用于验证的周期精确参考
- **WaveDrom 集成**：自动生成波形图
- **经验数据库**：从失败和成功中学习
- **KPI 追踪**：整个流程中的可观察指标
- **标准目录布局**：`stage_N_xxx/` 统一组织输出
- **Coding Style 系统**：按厂家分类的 RTL 编码规范（generic / Xilinx / Intel）
- **Stage 门禁检查**：stage 间质量门禁
- **结构化执行日志**：JSON 格式运行日志
- **执行后分析**：自我进化能力（失败模式检测、性能回归分析）

---

## 安装

```bash
git clone https://github.com/bjwanneng/Veriflow.git
cd Veriflow/verilog_flow
pip install -e ".[dev]"
```

可选依赖：Yosys（综合）、Icarus Verilog / Verilator（仿真）

---

## 快速开始

### 初始化项目

```bash
# 初始化标准目录结构 + coding style
verilog-flow init --vendor xilinx

# 运行门禁检查
verilog-flow check

# 运行执行后分析
verilog-flow analyze --runs 10
```

### Python API

```python
from verilog_flow import (
    ProjectLayout, CodingStyleManager, StageGateChecker,
    ExecutionLogger, PostRunAnalyzer,
    RTLCodeGenerator, LintChecker,
)
from pathlib import Path

# 初始化项目
layout = ProjectLayout(Path("."))
layout.initialize()

# 加载 coding style
mgr = CodingStyleManager(layout)
style = mgr.get_style("xilinx")

# 带 coding style 生成 RTL
gen = RTLCodeGenerator(coding_style=style)
module = gen.generate_fifo(depth=16, data_width=32)
module.save(layout.get_dir(3, "rtl"))

# 门禁检查
checker = StageGateChecker(layout)
for r in checker.check_all():
    print(f"Stage {r.stage}: {'PASS' if r.passed else 'FAIL'}")

# 执行日志
logger = ExecutionLogger(layout)
run = logger.start_run("my_project")
with logger.stage(3, "codegen") as slog:
    slog.metrics["files"] = 1
logger.end_run(success=True)

# 执行后分析
analyzer = PostRunAnalyzer(layout)
report = analyzer.analyze(n_recent=10)
for ins in report.insights:
    print(f"[{ins.severity}] {ins.message}")
```

---

## 标准目录布局

`verilog-flow init` 后的项目结构：

```
project_root/
  .veriflow/                          # 隐藏元数据目录
    logs/                             # 结构化执行日志
    experience_db/                    # 设计模式 & 失败案例
    coding_style/                     # Verilog coding style 规范
      generic/*.md
      xilinx/*.md
      intel/*.md
    templates/                        # RTL 代码模板（.v 文件，按厂家分类）
      generic/*.v                     # sync_fifo, async_fifo, fsm, ram 等
  stage_1_spec/specs/                 # 微架构规格 JSON
  stage_2_timing/                     # 虚拟时序建模
    scenarios/                        # YAML 场景
    golden_traces/                    # 金参考
    waveforms/                        # 波形 HTML
  stage_3_codegen/rtl/                # 生成的 RTL
    common/ crypto/ tx/ rx/
  stage_4_sim/                        # 仿真验证
    tb/                               # testbench
    sim/                              # 仿真输出
  stage_5_synth/synth/                # 综合结果
  reports/                            # 跨 stage 报告
```

---

## 五阶段工作流程

### Stage 1: 微架构规范

```python
from verilog_flow import MicroArchitect

architect = MicroArchitect()
spec = architect.design_from_requirements("my_fifo", {
    "target_frequency_mhz": 200,
    "data_width": 32,
    "fifo_depth": 16,
})
spec.save(layout.get_dir(1, "specs"))
```

### Stage 2: 虚拟时序建模

```bash
verilog-flow validate scenario.yaml
verilog-flow waveform scenario.yaml -o waveform.html
verilog-flow trace scenario.yaml -o golden_trace.json
```

### Stage 3: 代码生成与静态分析

```bash
vf-codegen fifo --depth 16 --width 32 --output rtl/
vf-codegen lint rtl/sync_fifo.v
```

### Stage 4: 仿真验证

```bash
vf-sim run rtl/sync_fifo.v scenario.yaml --top sync_fifo --simulator iverilog
vf-sim diff golden.json waveform.vcd
```

### Stage 5: 综合验证

```bash
vf-synth run rtl/sync_fifo.v --top sync_fifo --freq 200
```

---

## CLI 命令参考

| 命令 | 描述 |
|------|------|
| `verilog-flow init [--vendor V]` | 初始化项目目录 + coding style |
| `verilog-flow check [--stage N]` | 运行门禁检查 |
| `verilog-flow analyze [--runs N]` | 执行后分析 |
| `verilog-flow validate` | 验证 YAML 场景 |
| `verilog-flow waveform` | 生成波形图 |
| `verilog-flow trace` | 生成 Golden Trace |
| `verilog-flow dashboard` | 显示 KPI 仪表板 |
| `vf-codegen generate` | 从规范生成 RTL |
| `vf-codegen fifo / handshake` | 生成标准模块 |
| `vf-codegen lint` | 运行 lint 检查 |
| `vf-sim run / diff / trace` | 仿真与波形对比 |
| `vf-synth run / analyze / report` | 综合与时序分析 |

---

## Coding Style 系统

内置三套编码规范：

| 厂家 | Reset 风格 | 缩进 | 特点 |
|------|-----------|------|------|
| `generic` | async active-low | 4 空格 | 通用 Verilog-2005 |
| `xilinx` | sync active-high | 4 空格 | UG901 推荐，BRAM/DSP 推断 |
| `intel` | async active-low | 3 空格 | Intel FPGA 推荐 |

```python
mgr = CodingStyleManager(layout)
mgr.initialize_defaults()  # 复制默认 .md 和 .v 文件到项目
style = mgr.get_style("xilinx")

# 获取编码规范文档（Markdown）
doc = mgr.get_style_doc("xilinx")

# 获取模板
tpl = mgr.get_template("template_sync_fifo", "generic")
templates = mgr.list_templates("generic")

# 验证代码风格
issues = mgr.validate_code(verilog_code, style)
```

---

## 项目结构

```
verilog_flow/
├── __init__.py                # 公共 API 导出
├── common/                    # 共享基础设施
│   ├── project_layout.py     # 目录布局管理
│   ├── coding_style.py       # 编码规范管理
│   ├── stage_gate.py         # Stage 门禁检查
│   ├── execution_log.py      # 结构化执行日志
│   ├── post_run_analyzer.py  # 执行后分析
│   ├── experience_db.py      # 经验数据库
│   ├── kpi.py                # KPI 追踪
│   └── logger.py             # 日志工具
├── defaults/                  # 包级默认资源（随仓库发布）
│   ├── coding_style/         # 编码规范文档（.md，按厂家分类）
│   └── templates/            # RTL 模板（.v，按厂家分类）
├── stage1/                    # 微架构规范
├── stage2/                    # 虚拟时序建模
├── stage3/                    # 代码生成与静态分析
├── stage4/                    # 仿真验证
├── stage5/                    # 综合分析
├── cli/                       # 命令行界面
└── examples/                  # 示例场景
```

---

## 故障排除

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError: No module named 'verilog_flow'` | `cd verilog_flow && pip install -e .` |
| `Yosys not found` | 安装 Yosys（仅 Stage 5 需要） |
| `iverilog: command not found` | 安装 Icarus Verilog（仅 Stage 4 需要） |

---

## 许可证

MIT License
