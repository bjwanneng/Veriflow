# VeriFlow 示例项目

这是一个完整的 VeriFlow 工作流程示例，展示如何进行大型 Verilog 项目开发。

## 快速开始

### 1. 安装依赖

```bash
# 安装 VeriFlow
cd ../verilog_flow
pip install -e .

# 安装仿真工具（可选，但推荐）
# Ubuntu/Debian:
sudo apt-get install iverilog

# macOS:
brew install icarus-verilog
```

### 2. 运行完整流程

```bash
cd example_project

# 方式1：运行所有步骤
python run_all.py

# 方式2：逐步运行
python 01_define_spec.py
python 02_generate_rtl.py
python 03_run_simulation.py
python 04_run_synthesis.py
```

## 项目结构

```
example_project/
├── README.md                  # 本文件
├── run_all.py                # 一键运行所有步骤
├── requirements.json         # 项目需求定义
│
├── 01_define_spec.py         # 步骤1：定义架构
├── 01_architecture/          # 架构规范输出
│   └── simple_fifo_spec.json
│
├── 02_generate_rtl.py        # 步骤2：生成RTL
├── 02_rtl/                   # RTL代码输出
│   └── simple_fifo.v
│
├── 03_run_simulation.py      # 步骤3：运行仿真
├── 03_simulation/            # 仿真结果
│   ├── tb_simple_fifo.sv
│   ├── waveform.vcd
│   └── simulation.log
│
├── 04_run_synthesis.py       # 步骤4：运行综合
└── 04_synthesis/             # 综合结果
    ├── synthesis_result.json
    └── synthesized.v
```

## 工作流程详解

### 步骤1：架构定义 (Stage 1)

定义项目需求和微架构规范：

```python
# 01_define_spec.py
from verilog_flow import MicroArchitect

requirements = {
    "module_name": "simple_fifo",
    "target_frequency_mhz": 200,
    "data_width": 32,
    "fifo_depth": 16
}

architect = MicroArchitect()
spec = architect.design_from_requirements(
    requirements["module_name"],
    requirements
)

spec.save("01_architecture")
```

### 步骤2：RTL生成 (Stage 3)

生成Verilog代码并运行静态分析：

```python
# 02_generate_rtl.py
from verilog_flow import RTLCodeGenerator, LintChecker

generator = RTLCodeGenerator()
module = generator.generate_fifo(
    module_name="simple_fifo",
    depth=16,
    data_width=32
)

module.save("02_rtl")

# 运行Lint检查
lint_checker = LintChecker()
result = lint_checker.check(module.verilog_code, "simple_fifo.v")
```

### 步骤3：仿真验证 (Stage 4)

生成测试台并运行仿真：

```python
# 03_run_simulation.py
from verilog_flow import TestbenchGenerator, SimulationRunner

# 生成测试台
config = TestbenchConfig(module_name="simple_fifo")
tb_gen = TestbenchGenerator(config)
tb_code = tb_gen.generate_from_scenario(scenario)

# 运行仿真
runner = SimulationRunner(simulator="iverilog", output_dir="03_simulation")
result = runner.run(
    design_files=["02_rtl/simple_fifo.v"],
    testbench_file="03_simulation/tb_simple_fifo.sv",
    top_module="tb_simple_fifo"
)
```

### 步骤4：综合验证 (Stage 5)

运行综合并分析时序：

```python
# 04_run_synthesis.py
from verilog_flow import SynthesisRunner

runner = SynthesisRunner(output_dir="04_synthesis")
result = runner.run(
    verilog_files=["02_rtl/simple_fifo.v"],
    top_module="simple_fifo",
    target_frequency_mhz=200,
    target_device="generic"
)

print(f"Est. Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
print(f"Timing met: {result.timing_met}")
```

## 扩展：大型项目开发

对于大型项目，建议：

1. **模块化设计**：每个模块独立开发和验证
2. **层次化验证**：单元测试 → 集成测试 → 系统测试
3. **持续集成**：自动化运行所有测试
4. **版本控制**：使用Git管理代码和配置

## 故障排除

### 常见问题

1. **ImportError**: 确保已安装VeriFlow (`pip install -e .`)
2. **Iverilog not found**: 安装Icarus Verilog
3. **Yosys not found**: 安装Yosys (可选，用于综合)

### 获取帮助

- 查看 `../verilog_flow/README.md` 获取完整文档
- 查看 `../verilog_flow/TUTORIAL.md` 获取详细教程
- 运行 `python <script>.py --help` 获取脚本帮助
