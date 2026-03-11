#!/usr/bin/env python3
"""Step 4: Run synthesis."""

import sys
sys.path.insert(0, '../verilog_flow')

from verilog_flow import SynthesisRunner
from pathlib import Path

def main():
    print("="*60)
    print("Stage 4: Run Synthesis")
    print("="*60)

    # Check RTL exists
    rtl_file = "02_rtl/simple_fifo.v"
    if not Path(rtl_file).exists():
        print(f"✗ RTL file not found: {rtl_file}")
        print("  Run 02_generate_rtl.py first")
        return

    print(f"\nSynthesizing: {rtl_file}")
    print("Target: 200 MHz on generic device")

    # Run synthesis
    runner = SynthesisRunner(output_dir="04_synthesis")

    result = runner.run(
        verilog_files=[rtl_file],
        top_module="simple_fifo",
        target_frequency_mhz=200,
        target_device="generic"
    )

    if result.success:
        print(f"\n✓ Synthesis successful")
        print(f"  Estimated Fmax: {result.estimated_max_frequency_mhz:.2f} MHz")
        print(f"  Timing met: {result.timing_met}")
        print(f"  Cell count: {result.cell_count}")
        print(f"  LUTs: {result.lut_count}")
        print(f"  FFs: {result.flip_flop_count}")
    else:
        print(f"\n✗ Synthesis failed")
        for error in result.errors:
            print(f"  Error: {error}")

if __name__ == "__main__":
    main()
