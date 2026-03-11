# VeriFlow-Agent 3.0 使用指南

工业级 Verilog 代码生成系统，具有时序和微架构感知能力。

**English**: [README_EN.md](README_EN.md)

---

## 目录

- [概述](#概述)
- [安装](#安装)
- [快速开始](#快速开始)
- [五阶段工作流程](#五阶段工作流程)
- [CLI 命令参考](#cli-命令参考)
- [Python API 使用](#python-api-使用)
- [高级功能](#高级功能)
- [故障排除](#故障排除)

---

## 概述

VeriFlow-Agent 3.0 解决了 Verilog 代码生成中的常见问题：**"逻辑正确，物理失败"**。通过采用"左移"理念，它将微架构规划和物理时序估计带到了代码生成之前的阶段。

### 核心特性

- **5 阶段流水线**：从需求到综合的完整工作流程
- **YAML DSL**：参数化的时序场景描述
- **Golden Trace**：用于验证的周期精确参考
- **WaveDrom 集成**：自动生成波形图
- **经验数据库**：从失败和成功中学习
- **KPI 追踪**：整个流程中的可观察指标

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    VeriFlow-Agent 3.0                           │
├─────────────────────────────────────────────────────────────────┤
│ Stage 1 & 1.5: 微架构规范                                          │
│   - 流水线拓扑决策                                                 │
│   - 时序预算分配                                                   │
│   - 接口协议规范                                                   │
├─────────────────────────────────────────────────────────────────┤
│ Stage 2: 虚拟时序建模                                               │
│   - YAML DSL 场景描述                                             │
│   - WaveDrom 波形生成                                             │
│   - Golden Trace 生成                                             │
├─────────────────────────────────────────────────────────────────┤
│ Stage 3: 代码生成与静态分析                                          │
│   - RTL 代码生成                                                  │
│   - Lint 检查                                                     │
│   - Skill D (逻辑深度/CDC 分析)                                    │
├─────────────────────────────────────────────────────────────────┤
│ Stage 4: 物理仿真与验证                                              │
│   - 测试台执行                                                     │
│   - 波形差异分析                                                   │
│   - 断言检查                                                       │
├─────────────────────────────────────────────────────────────────┤
│ Stage 5: 综合级验证                                                 │
│   - Yosys 综合                                                    │
│   - 时序/面积估算                                                  │
│   - KPI 仪表板更新                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 安装

### 环境要求

- Python 3.9 或更高版本
- (可选) Yosys - 用于综合功能
- (可选) Icarus Verilog 或 Verilator - 用于仿真功能

### 从源码安装

```bash
git clone https://github.com/veriflow/verilog-flow.git
cd verilog-flow
pip install -e ".[dev]"
```

### 验证安装

```bash
python -c "from verilog_flow import __version__; print(f'VeriFlow {__version__} installed successfully')"
```

---

## 快速开始

### 1. 定义时序场景

创建一个 YAML 文件描述你的测试场景：

```yaml
# fifo_write_scenario.yaml
scenario: "FIFO_Write_Burst"
description: "Test FIFO write operations with burst transfers"

parameters:
  DEPTH: 4
  DATA_WIDTH: 32

clocks:
  clk:
    period: "5ns"  # 200MHz

phases:
  - name: "Reset_Phase"
    duration_ns: 50
    signals:
      rst_n: 0
      wr_en: 0
      rd_en: 0
    assertions:
      - "full == 0"
      - "empty == 1"

  - name: "Write_Phase"
    duration_ns: 20
    repeat:
      count: "$DEPTH"
      var: "i"
    signals:
      rst_n: 1
      wr_en: 1
      wr_data: "$i * 2"
    assertions:
      - "full == 0 until i == $DEPTH-1"
```

### 2. 验证场景

```bash
python -m verilog_flow.cli.main validate fifo_write_scenario.yaml
```

### 3. 生成波形图

```bash
python -m verilog_flow.cli.main waveform fifo_write_scenario.yaml --output waveform.html
```

### 4. 生成 Golden Trace

```bash
python -m verilog_flow.cli.main trace fifo_write_scenario.yaml --output golden_trace.json
```

---

## 五阶段工作流程

### Stage 1 & 1.5: 微架构规范

定义模块的微架构规范：

```python
from verilog_flow import SpecGenerator, MicroArchitect

# 使用自动化架构设计
architect = MicroArchitect()
spec = architect.design_from_requirements(
    module_name="my_fifo",
    requirements={
        "target_frequency_mhz": 200,
        "data_width": 32,
        "fifo_depth": 16,
        "interface_type": "axi4-lite"
    }
)

# 保存规范
spec.save("output/")

# 查看设计决策
print(architect.explain_design(spec))
```

### Stage 2: 虚拟时序建模

解析 YAML 场景并生成参考波形：

```python
from verilog_flow import parse_yaml_scenario, generate_golden_trace, generate_wavedrom

# 从 YAML 加载场景
with open("scenario.yaml") as f:
    scenario = parse_yaml_scenario(f.read())

# 生成 Golden Trace
trace = generate_golden_trace(scenario)
trace.save("golden_trace.json")

# 生成波形图
html = generate_wavedrom(scenario, output_path="waveform.html")
```

### Stage 3: 代码生成与静态分析

生成 RTL 代码并运行静态检查：

```bash
# 从规范生成代码
python -m verilog_flow.cli.codegen generate spec.json --output rtl/ --lint --analyze

# 生成标准 FIFO
python -m verilog_flow.cli.codegen fifo --depth 16 --width 32 --output rtl/

# 生成握手寄存器
python -m verilog_flow.cli.codegen handshake --width 64 --output rtl/

# 运行 lint 检查
python -m verilog_flow.cli.codegen lint rtl/sync_fifo.v
```

### Stage 4: 物理仿真与验证

运行仿真并对比 Golden Trace：

```bash
# 生成测试台并运行仿真
python -m verilog_flow.cli.simulate run \
    rtl/sync_fifo.v \
    scenario.yaml \
    --top sync_fifo \
    --simulator iverilog \
    --output sim_output/

# 对比波形
python -m verilog_flow.cli.simulate diff \
    sim_output/golden_trace.json \
    sim_output/waveform.vcd
```

### Stage 5: 综合级验证

运行综合并分析时序/面积：

```bash
# 运行综合
python -m verilog_flow.cli.synthesize run \
    rtl/sync_fifo.v \
    --top sync_fifo \
    --target generic \
    --freq 200 \
    --output synth_output/

# 详细分析（时序 + 面积）
python -m verilog_flow.cli.synthesize analyze \
    rtl/sync_fifo.v \
    --top sync_fifo \
    --target ice40 \
    --freq 100
```

---

## CLI 命令参考

### 主命令 (verilog-flow)

| 命令 | 描述 | 示例 |
|------|------|------|
| `validate` | 验证 YAML 场景 | `verilog-flow validate scenario.yaml` |
| `waveform` | 生成波形图 | `verilog-flow waveform scenario.yaml -o wave.html` |
| `trace` | 生成 Golden Trace | `verilog-flow trace scenario.yaml -o trace.json` |
| `dashboard` | 显示 KPI 仪表板 | `verilog-flow dashboard` |

### 代码生成命令 (vf-codegen)

| 命令 | 描述 | 示例 |
|------|------|------|
| `generate` | 从规范生成 RTL | `vf-codegen generate spec.json -o rtl/` |
| `fifo` | 生成 FIFO 模块 | `vf-codegen fifo --depth 16 --width 32` |
| `handshake` | 生成握手寄存器 | `vf-codegen handshake --width 64` |
| `lint` | 运行 lint 检查 | `vf-codegen lint design.v` |

**generate 选项：**
- `--output, -o`: 输出目录
- `--lint/--no-lint`: 是否运行 lint 检查（默认：是）
- `--analyze`: 运行逻辑深度和 CDC 分析

### 仿真命令 (vf-sim)

| 命令 | 描述 | 示例 |
|------|------|------|
| `run` | 运行仿真 | `vf-sim run design.v scenario.yaml -t top` |
| `diff` | 对比波形 | `vf-sim diff golden.json waveform.vcd` |
| `trace` | 生成 Golden Trace | `vf-sim trace scenario.yaml` |

**run 选项：**
- `--top, -t`: 顶层模块名称
- `--simulator, -s`: 仿真器选择（iverilog/verilator）
- `--golden-trace`: Golden Trace 文件路径

### 综合命令 (vf-synth)

| 命令 | 描述 | 示例 |
|------|------|------|
| `run` | 运行综合 | `vf-synth run design.v -t top -f 200` |
| `analyze` | 详细分析 | `vf-synth analyze design.v -t top` |
| `report` | 显示报告 | `vf-synth report result.json` |

**run/analyze 选项：**
- `--top, -t`: 顶层模块名称（必需）
- `--target`: 目标器件（generic/ice40/ecp5/xilinx）
- `--freq, -f`: 目标频率（MHz，默认：100）
- `--output, -o`: 输出目录

---

## Python API 使用

### 基础用法

```python
from verilog_flow import (
    RTLCodeGenerator,
    TestbenchGenerator,
    TestbenchConfig,
    SynthesisRunner
)

# 生成 FIFO
generator = RTLCodeGenerator()
module = generator.generate_fifo(depth=16, data_width=32)
module.save("output/")

# 生成测试台
config = TestbenchConfig(module_name="sync_fifo")
tb_gen = TestbenchGenerator(config)
tb_code = tb_gen.generate_from_scenario(scenario)

# 运行综合
runner = SynthesisRunner(output_dir="synth/")
result = runner.run(
    verilog_files=["rtl/sync_fifo.v"],
    top_module="sync_fifo",
    target_frequency_mhz=200
)

print(f"Estimated Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
print(f"Cell count: {result.cell_count}")
```

### 高级用法：自定义代码生成

```python
from verilog_flow import RTLCodeGenerator
from verilog_flow.stage1 import MicroArchSpec

# 加载微架构规范
spec = MicroArchSpec.from_file("my_design_spec.json")

# 生成代码
generator = RTLCodeGenerator()
module = generator.generate_from_spec(spec)

# 查看生成的代码
print(module.verilog_code)

# 获取元数据
print(f"Lines of code: {module.lines_of_code}")
print(f"Parameters: {module.parameters}")
print(f"Ports: {module.ports}")
```

### 静态分析

```python
from verilog_flow import LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth, analyze_cdc

# Lint 检查
lint_checker = LintChecker()
with open("design.v") as f:
    result = lint_checker.check(f.read(), "design.v")

print(f"Errors: {result.error_count}")
print(f"Warnings: {result.warning_count}")

for issue in result.issues:
    print(f"[{issue.severity}] {issue.rule_id}: {issue.message}")

# 逻辑深度分析
depth_result = analyze_logic_depth(verilog_code, target_depth=10)
print(f"Violations: {depth_result['violation_count']}")

# CDC 分析
cdc_result = analyze_cdc(verilog_code)
print(f"Unsafe crossings: {len(cdc_result.unsafe_crossings)}")
```

---

## YAML DSL 规范

### 完整场景示例

```yaml
scenario: "Complete_Test"
description: "A comprehensive test scenario"

# 参数定义
parameters:
  DATA_WIDTH: 32
  ADDR_WIDTH: 8
  DEPTH: 16

# 时钟定义
clocks:
  clk:
    period: "5ns"      # 周期
    duty_cycle: 50     # 占空比百分比
    jitter_ps: 100     # 抖动（皮秒）

# 测试阶段
phases:
  - name: "Reset"
    duration_ns: 100
    description: "Initial reset phase"
    signals:
      rst_n: 0
      wr_en: 0
      rd_en: 0
    assertions:
      - expression: "empty == 1"
        severity: "error"
      - expression: "full == 0"
        severity: "error"

  - name: "Write_Burst"
    duration_ns: 80
    repeat:
      count: "$DEPTH"
      var: "i"
    signals:
      rst_n: 1
      wr_en: 1
      wr_data: "$i * 4 + 16"
    assertions:
      - expression: "full == 0 until i == $DEPTH-1"
        type: "delayed"

  - name: "Read_Burst"
    duration_ns: 80
    repeat:
      count: "$DEPTH"
      var: "j"
    signals:
      rd_en: 1
    assertions:
      - expression: "rd_data == $j * 4 + 16"
        type: "immediate"

# 全局断言（贯穿整个仿真）
global_assertions:
  - expression: "!(full && empty)"
    description: "FIFO cannot be full and empty simultaneously"
    severity: "error"
```

### 信号值表达式

| 语法 | 描述 | 示例 |
|------|------|------|
| 常量 | 直接数值 | `wr_data: 42` |
| 变量引用 | `$var` | `wr_data: "$i * 2"` |
| 二进制 | `0b` 前缀 | `mode: 0b1010` |
| 十六进制 | `0x` 前缀 | `addr: 0xFF00` |

### 断言类型

| 类型 | 描述 | 用途 |
|------|------|------|
| `immediate` | 立即检查 | 组合逻辑检查 |
| `delayed` | 延迟检查 | 时序逻辑检查 |
| `eventual` | 最终检查 | 验证事件最终发生 |
| `never` | 永不检查 | 验证条件永不发生 |

---

## 高级功能

### 1. KPI 追踪

```python
from verilog_flow import KPITracker

tracker = KPITracker()

# 开始追踪
run = tracker.start_run(
    run_id="run_001",
    module_name="my_fifo",
    target_frequency_mhz=200
)

# 追踪各个阶段
stage = tracker.start_stage("code_generation")
# ... 生成代码 ...
tracker.end_stage(success=True, token_count=1500)

# 结束并保存
tracker.end_run(
    pass_at_1=True,
    timing_closure=True
)

# 查看摘要
summary = tracker.get_summary(n_runs=10)
print(f"Pass@1 rate: {summary['pass_at_1_rate']*100:.1f}%")
```

### 2. 自定义模板

```python
from verilog_flow.stage3 import TemplateEngine

engine = TemplateEngine()

template = """
module {{ module_name }} (
    input clk,
    input rst_n,
    {% for port in ports %}
    {{ port.direction }} [{{ port.width-1 }}:0] {{ port.name }}{% if not loop.last %},{% endif %}
    {% endfor %}
);
    // Implementation
    {{ implementation }}
endmodule
"""

context = {
    "module_name": "my_module",
    "ports": [
        {"name": "data_in", "direction": "input", "width": 32},
        {"name": "data_out", "direction": "output", "width": 32}
    ],
    "implementation": "// TODO: Add logic"
}

verilog_code = engine.render_string(template, context)
```

---

## 故障排除

### 常见问题

#### 1. 导入错误

**问题**: `ModuleNotFoundError: No module named 'verilog_flow'`

**解决**: 确保在正确的目录中安装和运行：

```bash
cd verilog-flow
pip install -e .
python -m verilog_flow.cli.main --help
```

#### 2. Yosys 未找到

**问题**: `Yosys not found`

**解决**: 安装 Yosys：

```bash
# Ubuntu/Debian
sudo apt-get install yosys

# macOS
brew install yosys

# Windows (使用 MSYS2)
pacman -S yosys
```

#### 3. 仿真器未找到

**问题**: `iverilog: command not found`

**解决**: 安装 Icarus Verilog：

```bash
# Ubuntu/Debian
sudo apt-get install iverilog

# macOS
brew install icarus-verilog
```

#### 4. YAML 解析错误

**问题**: YAML 文件解析失败

**解决**: 检查 YAML 语法：
- 使用正确的缩进（空格，不是制表符）
- 确保引号成对出现
- 特殊字符需要转义

#### 5. 波形对比失败

**问题**: Waveform diff 显示大量差异

**解决**:
- 检查时序是否匹配
- 验证信号名称是否正确
- 调整时间容差：`WaveformDiffAnalyzer(tolerance_ps=500)`

### 调试技巧

1. **启用详细输出**：大多数命令支持 `-v` 或 `--verbose` 选项

2. **检查生成的文件**：
   ```bash
   # Stage 2
   cat golden_trace.json

   # Stage 3
   cat output/sync_fifo.v

   # Stage 4
   cat sim_output/simulation.log

   # Stage 5
   cat synth_output/synthesis_result.json
   ```

3. **使用 Python 交互式调试**：
   ```python
   from verilog_flow import parse_yaml_scenario

   with open("scenario.yaml") as f:
       scenario = parse_yaml_scenario(f.read())

   # 检查解析结果
   print(scenario.phases)
   print(scenario.to_dict())
   ```

---

## 项目结构

```
verilog_flow/
├── verilog_flow/                 # 主包
│   ├── __init__.py
│   ├── common/                   # 共享工具
│   │   ├── kpi.py               # KPI 追踪
│   │   ├── experience_db.py     # 经验数据库
│   │   └── logger.py            # 日志工具
│   ├── stage1/                  # 微架构规范
│   │   ├── spec_generator.py    # 规范生成器
│   │   └── architect.py         # 架构设计器
│   ├── stage2/                  # 虚拟时序建模
│   │   ├── yaml_dsl.py          # YAML DSL 解析器
│   │   ├── validator.py         # 模式验证
│   │   ├── golden_trace.py      # Trace 生成
│   │   └── wavedrom_gen.py      # 波形生成
│   ├── stage3/                  # 代码生成
│   │   ├── code_generator.py    # RTL 生成器
│   │   ├── lint_checker.py      # Lint 检查
│   │   ├── skill_d.py           # 逻辑深度/CDC 分析
│   │   └── template_engine.py   # 模板引擎
│   ├── stage4/                  # 仿真
│   │   ├── testbench.py         # 测试台生成
│   │   ├── sim_runner.py        # 仿真运行器
│   │   ├── waveform_diff.py     # 波形对比
│   │   └── assertion_checker.py # 断言检查
│   ├── stage5/                  # 综合
│   │   ├── synthesis_runner.py  # 综合运行器
│   │   ├── timing_analyzer.py   # 时序分析
│   │   ├── area_estimator.py    # 面积估算
│   │   └── yosys_interface.py   # Yosys 接口
│   └── cli/                     # 命令行界面
│       ├── main.py              # 主 CLI
│       ├── codegen.py           # 代码生成 CLI
│       ├── simulate.py          # 仿真 CLI
│       └── synthesize.py        # 综合 CLI
├── examples/                     # 示例场景
├── schemas/                      # JSON 模式
├── templates/                    # 代码模板
├── tests/                        # 测试套件
└── docs/                         # 文档
```

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！请确保：

1. 代码符合 PEP 8 规范
2. 添加适当的测试
3. 更新文档

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 联系方式

- Issues: [GitHub Issues](https://github.com/veriflow/verilog-flow/issues)
- Discussions: [GitHub Discussions](https://github.com/veriflow/verilog-flow/discussions)
- Email: contact@veriflow.dev

---

**VeriFlow-Agent 3.0** - *Shifting-left hardware design, one stage at a time.*
