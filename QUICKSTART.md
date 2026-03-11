# VeriFlow 快速入门指南

## 目录结构说明

```
Verilog_flow_skill/
├── verilog_flow/               # ⭐ 主要代码目录
│   ├── README.md              # 中文文档
│   ├── README_EN.md           # 英文文档
│   ├── TUTORIAL.md            # 完整教程
│   ├── stage1/ ~ stage5/     # 五个阶段的代码
│   ├── cli/                   # 命令行工具
│   └── ...
│
├── verilog-flow-skill/        # Agent Skill 格式
│   └── SKILL.md               # 用于 Claude Code Skill 系统
│
├── example_project/           # ⭐ 示例项目（推荐从这里开始）
│   ├── README.md
│   ├── run_all.py            # 一键运行所有步骤
│   ├── 01_define_spec.py     # 步骤1：定义架构
│   ├── 02_generate_rtl.py    # 步骤2：生成RTL
│   ├── 03_run_simulation.py  # 步骤3：仿真
│   └── 04_run_synthesis.py   # 步骤4：综合
│
└── request.md                 # 原始需求文档
```

## 快速开始（3分钟上手）

### 方式1：运行示例项目（推荐）

```bash
# 进入示例项目
cd example_project

# 方式A：一键运行所有步骤
python run_all.py

# 方式B：逐步运行
python 01_define_spec.py      # 定义架构
python 02_generate_rtl.py      # 生成RTL代码
python 03_run_simulation.py    # 运行仿真
python 04_run_synthesis.py     # 运行综合
```

### 方式2：使用命令行工具

```bash
# 进入代码目录
cd ../verilog_flow

# 安装
pip install -e .

# 生成FIFO
python -m verilog_flow.cli.codegen fifo --depth 16 --width 32 --output rtl/

# 运行Lint检查
python -m verilog_flow.cli.codegen lint rtl/simple_fifo.v
```

### 方式3：使用Python API

```python
# example.py
import sys
sys.path.insert(0, '../verilog_flow')

from verilog_flow import RTLCodeGenerator

# 生成FIFO
generator = RTLCodeGenerator()
module = generator.generate_fifo(
    module_name="my_fifo",
    depth=16,
    data_width=32
)

# 保存
module.save("rtl/")
print(f"Generated: {module.file_path}")
```

## 工作流程（5个阶段）

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: 定义架构 (Define Architecture)                    │
│  - 创建项目需求                                             │
│  - 生成微架构规范                                           │
│  - 输出: spec.json                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: 虚拟时序建模 (Virtual Timing Modeling)           │
│  - 编写YAML测试场景                                         │
│  - 生成Golden Trace                                         │
│  - 输出: scenario.yaml, golden_trace.json                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: 代码生成 (Code Generation)                       │
│  - 生成RTL代码                                              │
│  - 运行Lint检查                                             │
│  - 静态分析（逻辑深度/CDC）                                 │
│  - 输出: .v 文件                                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: 仿真验证 (Simulation)                            │
│  - 生成测试台                                               │
│  - 运行仿真                                                 │
│  - 对比Golden Trace                                         │
│  - 输出: waveform.vcd, 仿真报告                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 5: 综合验证 (Synthesis)                             │
│  - 运行综合                                                 │
│  - 时序分析                                                 │
│  - 面积估算                                                 │
│  - 输出: 综合报告, 网表文件                                 │
└─────────────────────────────────────────────────────────────┘
```

## 下一步

1. **运行示例项目**了解完整流程
2. **阅读TUTORIAL.md**获取详细教程
3. **查看API文档**了解所有功能
4. **创建自己的项目**

## 常见问题

**Q: 我需要安装什么？**
A: Python 3.9+, 然后 `pip install -e .` 安装VeriFlow

**Q: 我需要安装Yosys吗？**
A: 只有运行综合(Stage 5)时才需要，其他功能不需要

**Q: 如何获取帮助？**
A: 查看 `README.md`, `TUTORIAL.md`, 或运行 `python script.py --help`
