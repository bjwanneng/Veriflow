#!/usr/bin/env python3
"""Step 3: Run simulation."""

import sys
sys.path.insert(0, '../verilog_flow')

from verilog_flow import SimulationRunner, TestbenchConfig
from verilog_flow import TestbenchGenerator

def main():
    print("="*60)
    print("Stage 3: Run Simulation")
    print("="*60)

    # Check RTL exists
    rtl_file = "02_rtl/simple_fifo.v"
    if not Path(rtl_file).exists():
        print(f"✗ RTL file not found: {rtl_file}")
        print("  Run 02_generate_rtl.py first")
        return

    # Generate testbench
    print("\nGenerating testbench...")
    config = TestbenchConfig(
        module_name="simple_fifo",
        dump_waveform=True,
        timeout_cycles=1000
    )

    # Create simple scenario
    scenario = parse_yaml_scenario("""
scenario: "FIFO_Test"
clocks:
  clk:
    period: "10ns"
phases:
  - name: "Reset"
    duration_ns: 50
    signals:
      rst_n: 0
      wr_en: 0
      rd_en: 0
  - name: "Write"
    duration_ns: 100
    signals:
      rst_n: 1
      wr_en: 1
      rd_en: 0
  - name: "Read"
    duration_ns: 100
    signals:
      rst_n: 1
      wr_en: 0
      rd_en: 1
""")

    tb_gen = TestbenchGenerator(config)
    tb_code = tb_gen.generate_from_scenario(scenario)

    Path("03_simulation").mkdir(exist_ok=True)
    tb_file = "03_simulation/tb_simple_fifo.sv"
    Path(tb_file).write_text(tb_code)
    print(f"  ✓ Testbench: {tb_file}")

    # Run simulation
    print("\nRunning simulation with Icarus Verilog...")
    runner = SimulationRunner(
        simulator="iverilog",
        output_dir="03_simulation"
    )

    result = runner.run(
        design_files=[rtl_file],
        testbench_file=Path(tb_file),
        top_module="tb_simple_fifo"
    )

    if result.success:
        print(f"  ✓ Simulation passed")
        print(f"    Tests: {result.tests_passed}/{result.tests_total}")
    else:
        print(f"  ✗ Simulation failed")
        if result.error:
            print(f"    Error: {result.error}")

    if result.waveform_file:
        print(f"    Waveform: {result.waveform_file}")

if __name__ == "__main__":
    main()
