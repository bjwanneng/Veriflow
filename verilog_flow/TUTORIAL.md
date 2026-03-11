# VeriFlow 完整工作流程教程

本文档通过一个完整的示例，展示如何使用 VeriFlow 进行大型 Verilog 项目开发。

## 示例项目：AXI4 DMA 控制器

我们将设计一个 AXI4 DMA (Direct Memory Access) 控制器，包含：
- 读写通道
- FIFO 缓冲
- 地址生成
- 突发传输支持

---

## 第一步：需求分析 (Stage 1)

### 1.1 定义项目需求

创建 `project_requirements.json`：

```json
{
  "module_name": "axi4_dma_controller",
  "target_frequency_mhz": 200,
  "data_width": 64,
  "addr_width": 32,
  "max_burst_length": 16,
  "fifo_depth": 32,
  "interfaces": [
    {
      "name": "axi4_master",
      "protocol": "AXI4",
      "direction": "master",
      "description": "AXI4 master interface for memory access"
    },
    {
      "name": "axi4_lite_slave",
      "protocol": "AXI4-Lite",
      "direction": "slave",
      "description": "AXI4-Lite slave interface for register configuration"
    }
  ],
  "features": [
    "Scatter-gather DMA",
    "Interrupt support",
    "Error handling"
  ]
}
```

### 1.2 生成微架构规范

创建 Python 脚本 `01_define_architecture.py`：

```python
#!/usr/bin/env python3
"""Step 1: Define micro-architecture specification."""

import json
from verilog_flow import MicroArchitect

def main():
    # 读取需求
    with open("project_requirements.json") as f:
        requirements = json.load(f)

    # 使用架构设计器
    architect = MicroArchitect()
    spec = architect.design_from_requirements(
        module_name=requirements["module_name"],
        requirements=requirements
    )

    # 保存规范
    output_dir = "01_architecture"
    spec.save(output_dir)

    print(f"✓ Architecture specification saved to {output_dir}/")
    print(f"  - Module: {spec.module_name}")
    print(f"  - Target frequency: {spec.timing_budget.target_frequency_mhz} MHz")
    print(f"  - Pipeline stages: {len(spec.pipeline_stages)}")

    # 输出设计说明
    print("\n" + "="*60)
    print(architect.explain_design(spec))

    return spec

if __name__ == "__main__":
    main()
```

运行：
```bash
python 01_define_architecture.py
```

输出：
```
✓ Architecture specification saved to 01_architecture/
  - Module: axi4_dma_controller
  - Target frequency: 200 MHz
  - Pipeline stages: 3

============================================================
Micro-Architecture Design: axi4_dma_controller
============================================================

Pipeline: 3 stages
  - stage_0: 5 logic levels
  - stage_1: 5 logic levels
  - stage_2: 5 logic levels

Timing Budget:
  - Target: 200.00 MHz
  - Period: 5.00 ns
...
```

---

## 第二步：定义测试场景 (Stage 2)

### 2.1 创建测试场景

创建 `02_test_scenarios/` 目录和场景文件：

**`dma_single_transfer.yaml`** - 单次传输测试：
```yaml
scenario: "DMA_Single_Transfer"
description: "Test single DMA transfer from source to destination"

parameters:
  DATA_WIDTH: 64
  ADDR_WIDTH: 32

clocks:
  clk:
    period: "5ns"  # 200MHz

phases:
  - name: "Reset"
    duration_ns: 100
    signals:
      rst_n: 0
      dma_enable: 0
      src_addr: 0
      dst_addr: 0
      transfer_len: 0
    assertions:
      - "busy == 0"
      - "irq == 0"

  - name: "Configure"
    duration_ns: 20
    signals:
      rst_n: 1
      dma_enable: 0
      src_addr: 0x1000
      dst_addr: 0x2000
      transfer_len: 4
    assertions:
      - "busy == 0"

  - name: "Start_Transfer"
    duration_ns: 10
    signals:
      dma_enable: 1
    assertions:
      - "busy == 1"

  - name: "Wait_Complete"
    duration_ns: 200
    signals:
      dma_enable: 1
    assertions:
      - "busy == 0 until time > 100"
      - "irq == 1"
```

**`dma_burst_transfer.yaml`** - 突发传输测试：
```yaml
scenario: "DMA_Burst_Transfer"
description: "Test burst DMA transfer with maximum burst length"

parameters:
  DATA_WIDTH: 64
  ADDR_WIDTH: 32
  MAX_BURST: 16

clocks:
  clk:
    period: "5ns"

phases:
  - name: "Reset"
    duration_ns: 100
    signals:
      rst_n: 0
      dma_enable: 0

  - name: "Configure_Burst"
    duration_ns: 20
    signals:
      rst_n: 1
      src_addr: 0x1000
      dst_addr: 0x2000
      transfer_len: "$MAX_BURST"
      burst_type: 1  # Incrementing burst

  - name: "Execute_Burst"
    duration_ns: 100
    signals:
      dma_enable: 1
    assertions:
      - "axi_awvalid == 1"
      - "axi_awlen == $MAX_BURST - 1"
```

### 2.2 生成 Golden Trace

创建 `02_generate_traces.py`：

```python
#!/usr/bin/env python3
"""Step 2: Generate golden traces from test scenarios."""

from pathlib import Path
from verilog_flow import parse_yaml_scenario, generate_golden_trace

def process_scenario(scenario_file, output_dir):
    """Process a single scenario file."""
    print(f"\nProcessing: {scenario_file.name}")

    # Parse YAML
    with open(scenario_file) as f:
        scenario = parse_yaml_scenario(f.read())

    print(f"  - Scenario: {scenario.name}")
    print(f"  - Phases: {len(scenario.phases)}")

    # Generate golden trace
    trace = generate_golden_trace(scenario)

    # Save trace
    output_file = output_dir / f"{scenario_file.stem}_golden.json"
    trace.save(output_file)
    print(f"  ✓ Trace saved: {output_file.name}")
    print(f"    Events: {len(trace.events)}")
    print(f"    Clock period: {trace.clock_period_ps} ps")

    return trace

def main():
    scenarios_dir = Path("02_test_scenarios")
    output_dir = Path("02_golden_traces")
    output_dir.mkdir(exist_ok=True)

    # Process all YAML files
    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        process_scenario(scenario_file, output_dir)

    print("\n" + "="*60)
    print(f"✓ All traces generated in {output_dir}/")

if __name__ == "__main__":
    main()
```

运行：
```bash
python 02_generate_traces.py
```

---

## 第三步：代码生成 (Stage 3)

### 3.1 生成模块代码

创建 `03_generate_rtl.py`：

```python
#!/usr/bin/env python3
"""Step 3: Generate RTL code."""

from pathlib import Path
from verilog_flow import RTLCodeGenerator, LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth, analyze_cdc

def generate_dma_controller():
    """Generate DMA controller with sub-modules."""
    generator = RTLCodeGenerator()
    output_dir = Path("03_rtl")
    output_dir.mkdir(exist_ok=True)

    modules = []

    # 1. 生成 FIFO 模块
    print("\n1. Generating FIFO module...")
    fifo = generator.generate_fifo(
        module_name="dma_fifo",
        depth=32,
        data_width=64
    )
    fifo_file = fifo.save(output_dir)
    modules.append(("DMA FIFO", fifo_file, fifo))
    print(f"  ✓ {fifo_file.name}")

    # 2. 生成握手寄存器
    print("\n2. Generating handshake register...")
    handshake = generator.generate_handshake_register(
        module_name="dma_handshake_reg",
        data_width=64
    )
    handshake_file = handshake.save(output_dir)
    modules.append(("Handshake Reg", handshake_file, handshake))
    print(f"  ✓ {handshake_file.name}")

    # 3. 生成 AXI4 接口适配器
    print("\n3. Generating AXI4 interface adapter...")
    # 这里可以使用模板生成更复杂的模块
    axi_adapter_code = generate_axi_adapter()
    axi_file = output_dir / "axi4_adapter.v"
    axi_file.write_text(axi_adapter_code)
    modules.append(("AXI4 Adapter", axi_file, None))
    print(f"  ✓ {axi_file.name}")

    return output_dir, modules

def generate_axi_adapter():
    """Generate AXI4 adapter code."""
    return '''//////////////////////////////////////////////////////////////////////////////
// Module: axi4_adapter
// Description: AXI4 interface adapter for DMA controller
//////////////////////////////////////////////////////////////////////////////

module axi4_adapter #(
    parameter DATA_WIDTH = 64,
    parameter ADDR_WIDTH = 32
)(
    input              clk,
    input              rst_n,

    // AXI4 Write Address Channel
    output reg [ADDR_WIDTH-1:0] axi_awaddr,
    output reg [7:0]            axi_awlen,
    output reg [2:0]            axi_awsize,
    output reg [1:0]            axi_awburst,
    output reg                  axi_awvalid,
    input                       axi_awready,

    // AXI4 Write Data Channel
    output reg [DATA_WIDTH-1:0] axi_wdata,
    output reg [DATA_WIDTH/8-1:0] axi_wstrb,
    output reg                  axi_wlast,
    output reg                  axi_wvalid,
    input                       axi_wready,

    // AXI4 Write Response Channel
    input  [1:0]                axi_bresp,
    input                       axi_bvalid,
    output reg                  axi_bready,

    // DMA Control Interface
    input                       dma_start,
    input  [ADDR_WIDTH-1:0]     src_addr,
    input  [ADDR_WIDTH-1:0]     dst_addr,
    input  [15:0]               transfer_len,
    output reg                  busy,
    output reg                  done,
    output reg                  error
);

// TODO: Implement AXI4 adapter logic

endmodule
'''

def run_lint_check(rtl_dir):
    """Run lint checks on all Verilog files."""
    print("\n" + "="*60)
    print("Running Lint Checks")
    print("="*60)

    lint_checker = LintChecker()

    for vfile in sorted(rtl_dir.glob("*.v")):
        print(f"\nLinting: {vfile.name}")
        result = lint_checker.check_file(vfile)

        if result.error_count > 0:
            print(f"  ✗ Errors: {result.error_count}")
            for issue in result.issues:
                if issue.severity == 'error':
                    print(f"    - Line {issue.line_number}: {issue.message}")
        else:
            print(f"  ✓ No errors")

        if result.warning_count > 0:
            print(f"  ⚠ Warnings: {result.warning_count}")
            for issue in result.issues:
                if issue.severity == 'warning':
                    print(f"    - Line {issue.line_number}: {issue.message}")

def run_static_analysis(rtl_dir):
    """Run logic depth and CDC analysis."""
    print("\n" + "="*60)
    print("Static Analysis")
    print("="*60)

    for vfile in sorted(rtl_dir.glob("*.v")):
        print(f"\nAnalyzing: {vfile.name}")
        code = vfile.read_text()

        # Logic depth analysis
        depth_result = analyze_logic_depth(code, target_depth=10)
        if depth_result['violation_count'] > 0:
            print(f"  ⚠ Logic depth violations: {depth_result['violation_count']}")
            for v in depth_result['violations']:
                print(f"    - {v['signal']}: depth {v['depth']}")
        else:
            print(f"  ✓ Logic depth OK")

        # CDC analysis
        cdc_result = analyze_cdc(code)
        if cdc_result.unsafe_crossings:
            print(f"  ⚠ Unsafe CDC crossings: {len(cdc_result.unsafe_crossings)}")
        else:
            print(f"  ✓ No unsafe CDC crossings")

def main():
    print("="*60)
    print("Stage 3: RTL Code Generation")
    print("="*60)

    # Generate RTL
    rtl_dir, modules = generate_dma_controller()

    print("\n" + "="*60)
    print(f"✓ Generated {len(modules)} modules in {rtl_dir}/")
    for name, fpath, mod in modules:
        if mod:
            print(f"  - {name}: {fpath.name} ({mod.lines_of_code} LOC)")
        else:
            print(f"  - {name}: {fpath.name}")

    # Run lint checks
    run_lint_check(rtl_dir)

    # Run static analysis
    run_static_analysis(rtl_dir)

    print("\n" + "="*60)
    print("Stage 3 Complete")
    print("="*60)

if __name__ == "__main__":
    main()
```

运行：
```bash
python 03_generate_rtl.py
```

---

## 第四步：仿真验证 (Stage 4)

### 4.1 生成测试台并运行仿真

创建 `04_run_simulation.py`：

```python
#!/usr/bin/env python3
"""Step 4: Generate testbenches and run simulation."""

from pathlib import Path
from verilog_flow import TestbenchGenerator, TestbenchConfig
from verilog_flow import SimulationRunner, WaveformDiffAnalyzer
from verilog_flow import parse_yaml_scenario, generate_golden_trace

def generate_testbench(scenario_file, rtl_dir, output_dir):
    """Generate testbench for a scenario."""
    print(f"\nGenerating testbench for: {scenario_file.stem}")

    # Parse scenario
    with open(scenario_file) as f:
        scenario = parse_yaml_scenario(f.read())

    # Generate testbench
    config = TestbenchConfig(
        module_name=scenario_file.stem,
        dump_waveform=True,
        timeout_cycles=10000
    )

    tb_gen = TestbenchGenerator(config)

    # Find DUT module (use FIFO as example)
    tb_code = tb_gen.generate_from_scenario(scenario, dut_module="dma_fifo")

    # Save testbench
    tb_file = output_dir / f"tb_{scenario_file.stem}.sv"
    tb_file.write_text(tb_code)

    print(f"  ✓ Testbench: {tb_file.name}")

    return tb_file, scenario

def run_simulation(tb_file, rtl_files, output_dir):
    """Run simulation."""
    print(f"\nRunning simulation: {tb_file.name}")

    runner = SimulationRunner(
        simulator="iverilog",
        output_dir=output_dir
    )

    result = runner.run(
        design_files=rtl_files,
        testbench_file=tb_file,
        top_module=f"tb_{tb_file.stem.replace('tb_', '')}"
    )

    if result.success:
        print(f"  ✓ Simulation passed")
        print(f"    Tests: {result.tests_passed}/{result.tests_total} passed")
        print(f"    Assertions: {result.assertions_passed}/{result.assertions_total} passed")
    else:
        print(f"  ✗ Simulation failed")
        if result.error:
            print(f"    Error: {result.error}")

    if result.waveform_file:
        print(f"    Waveform: {result.waveform_file}")

    return result

def compare_with_golden(sim_result, golden_trace_file, output_dir):
    """Compare simulation with golden trace."""
    print(f"\nComparing with golden trace...")

    if not sim_result.waveform_file or not golden_trace_file.exists():
        print("  ⚠ Skipping comparison (missing files)")
        return None

    from verilog_flow.stage2.golden_trace import GoldenTrace
    import json

    # Load golden trace
    with open(golden_trace_file) as f:
        trace_data = json.load(f)

    golden = GoldenTrace(
        scenario_id=trace_data.get('scenario_id', 'unknown'),
        scenario_name=trace_data.get('scenario_name', 'unknown'),
        clock_period_ps=trace_data.get('clock_period_ps', 10000),
    )

    # Compare
    analyzer = WaveformDiffAnalyzer()
    diff_result = analyzer.compare(golden, sim_result.waveform_file)

    if diff_result.matched:
        print(f"  ✓ Waveforms match!")
    else:
        print(f"  ⚠ Found {diff_result.difference_count} differences")
        for diff in diff_result.differences[:5]:
            print(f"    - {diff.signal} at {diff.time_ps}ps: "
                  f"expected={diff.expected_value}, actual={diff.actual_value}")

    return diff_result

def main():
    print("="*60)
    print("Stage 4: Simulation & Verification")
    print("="*60)

    rtl_dir = Path("03_rtl")
    scenario_dir = Path("02_test_scenarios")
    golden_dir = Path("02_golden_traces")
    output_dir = Path("04_simulation")
    output_dir.mkdir(exist_ok=True)

    # Get RTL files
    rtl_files = list(rtl_dir.glob("*.v"))
    print(f"\nRTL files: {len(rtl_files)}")
    for f in rtl_files:
        print(f"  - {f.name}")

    # Process each scenario
    for scenario_file in sorted(scenario_dir.glob("*.yaml")):
        print("\n" + "-"*60)
        print(f"Scenario: {scenario_file.stem}")
        print("-"*60)

        # Generate testbench
        tb_file, scenario = generate_testbench(scenario_file, rtl_dir, output_dir)

        # Run simulation
        sim_result = run_simulation(tb_file, rtl_files, output_dir)

        # Compare with golden trace
        golden_file = golden_dir / f"{scenario_file.stem}_golden.json"
        if golden_file.exists():
            compare_with_golden(sim_result, golden_file, output_dir)

    print("\n" + "="*60)
    print("Stage 4 Complete")
    print("="*60)

if __name__ == "__main__":
    main()
```

---

## 第五步：综合验证 (Stage 5)

### 5.1 运行综合和时序分析

创建 `05_run_synthesis.py`：

```python
#!/usr/bin/env python3
"""Step 5: Run synthesis and analyze timing/area."""

from pathlib import Path
from verilog_flow import SynthesisRunner, TimingAnalyzer, AreaEstimator

def synthesize_module(rtl_file, target_freq, target_device, output_dir):
    """Synthesize a single module."""
    print(f"\nSynthesizing: {rtl_file.name}")
    print(f"  Target: {target_freq} MHz on {target_device}")

    runner = SynthesisRunner(output_dir=output_dir)

    result = runner.run(
        verilog_files=[rtl_file],
        top_module=rtl_file.stem,
        target_frequency_mhz=target_freq,
        target_device=target_device
    )

    if result.success:
        print(f"  ✓ Synthesis successful")
        print(f"    Est. Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
        print(f"    Timing met: {result.timing_met}")
        print(f"    Cell count: {result.cell_count}")
        print(f"    LUTs: {result.lut_count}, FFs: {result.flip_flop_count}")
    else:
        print(f"  ✗ Synthesis failed")
        for error in result.errors:
            print(f"    Error: {error}")

    return result

def analyze_results(synth_results, target_freq):
    """Analyze synthesis results."""
    print("\n" + "="*60)
    print("Synthesis Analysis Summary")
    print("="*60)

    timing_analyzer = TimingAnalyzer(target_frequency_mhz=target_freq)

    all_passed = True
    for module_name, result in synth_results.items():
        status = "✓ PASS" if result.timing_met else "✗ FAIL"
        print(f"\n{module_name}: {status}")
        print(f"  Target: {target_freq} MHz")
        print(f"  Achieved: {result.estimated_max_frequency_mhz:.2f} MHz")

        if result.worst_negative_slack_ns < 0:
            print(f"  WNS: {result.worst_negative_slack_ns:.3f} ns (VIOLATION)")
            all_passed = False
        else:
            print(f"  WNS: +{result.worst_negative_slack_ns:.3f} ns")

        print(f"  Resources: {result.cell_count} cells "
              f"({result.lut_count} LUTs, {result.flip_flop_count} FFs)")

    print("\n" + "="*60)
    if all_passed:
        print("✓ All modules meet timing requirements")
    else:
        print("✗ Some modules failed timing - optimization needed")
    print("="*60)

def main():
    print("="*60)
    print("Stage 5: Synthesis & Analysis")
    print("="*60)

    rtl_dir = Path("03_rtl")
    output_dir = Path("05_synthesis")
    output_dir.mkdir(exist_ok=True)

    target_freq = 200  # MHz
    target_device = "generic"

    synth_results = {}

    # Synthesize each module
    for rtl_file in sorted(rtl_dir.glob("*.v")):
        module_output = output_dir / rtl_file.stem
        module_output.mkdir(exist_ok=True)

        result = synthesize_module(
            rtl_file,
            target_freq,
            target_device,
            module_output
        )

        synth_results[rtl_file.stem] = result

    # Analyze results
    analyze_results(synth_results, target_freq)

    print("\n" + "="*60)
    print("Stage 5 Complete")
    print("="*60)

if __name__ == "__main__":
    main()
```

---

## 完整运行流程

创建一个主脚本 `run_all.py`：

```python
#!/usr/bin/env python3
"""Complete workflow runner."""

import sys
import subprocess

def run_step(step_name, script):
    """Run a single step."""
    print("\n" + "="*70)
    print(f"  {step_name}")
    print("="*70)

    result = subprocess.run([sys.executable, script])

    if result.returncode != 0:
        print(f"\n✗ Step failed: {step_name}")
        return False

    return True

def main():
    steps = [
        ("Stage 1: Architecture Definition", "01_define_architecture.py"),
        ("Stage 2: Test Scenario Generation", "02_generate_traces.py"),
        ("Stage 3: RTL Code Generation", "03_generate_rtl.py"),
        ("Stage 4: Simulation & Verification", "04_run_simulation.py"),
        ("Stage 5: Synthesis & Analysis", "05_run_synthesis.py"),
    ]

    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  VeriFlow Complete Workflow".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    for step_name, script in steps:
        if not run_step(step_name, script):
            sys.exit(1)

    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  All Stages Completed Successfully!".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    print("\nOutput directories:")
    print("  - 01_architecture/       : Micro-architecture specification")
    print("  - 02_test_scenarios/     : YAML test scenarios")
    print("  - 02_golden_traces/      : Golden reference traces")
    print("  - 03_rtl/                : Generated RTL code")
    print("  - 04_simulation/         : Simulation results & waveforms")
    print("  - 05_synthesis/          : Synthesis reports")

if __name__ == "__main__":
    main()
```

---

## 项目文件结构

运行完整流程后，项目结构如下：

```
project/
├── 01_define_architecture.py      # 架构定义脚本
├── 02_generate_traces.py          # 场景生成脚本
├── 03_generate_rtl.py             # RTL 生成脚本
├── 04_run_simulation.py           # 仿真脚本
├── 05_run_synthesis.py            # 综合脚本
├── run_all.py                     # 主运行脚本
├── project_requirements.json      # 项目需求
│
├── 01_architecture/               # 架构规范输出
│   └── axi4_dma_controller_spec.json
│
├── 02_test_scenarios/             # 测试场景
│   ├── dma_single_transfer.yaml
│   └── dma_burst_transfer.yaml
│
├── 02_golden_traces/              # Golden Trace
│   ├── dma_single_transfer_golden.json
│   └── dma_burst_transfer_golden.json
│
├── 03_rtl/                        # RTL 代码
│   ├── axi4_adapter.v
│   ├── dma_fifo.v
│   └── dma_handshake_reg.v
│
├── 04_simulation/                 # 仿真结果
│   ├── tb_dma_single_transfer.sv
│   ├── tb_dma_burst_transfer.sv
│   ├── waveform.vcd
│   └── simulation.log
│
└── 05_synthesis/                  # 综合结果
    ├── dma_fifo/
    │   ├── synthesis_result.json
    │   └── synthesized.v
    └── ...
```

---

## 下一步

1. **查看结果**：检查各阶段输出目录
2. **迭代优化**：根据仿真和综合结果调整设计
3. **添加功能**：扩展模块功能（中断、错误处理等）
4. **FPGA 实现**：使用 Vivado/Quartus 进行实际实现

有任何问题请查看 `README.md` 或 `README_EN.md` 获取更详细的文档！