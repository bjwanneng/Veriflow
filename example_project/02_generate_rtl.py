#!/usr/bin/env python3
"""Step 2: Generate RTL code."""

import sys
sys.path.insert(0, '../verilog_flow')

from verilog_flow import RTLCodeGenerator, LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth
from pathlib import Path

def main():
    print("="*60)
    print("Stage 2: Generate RTL")
    print("="*60)

    # Generate FIFO
    generator = RTLCodeGenerator()
    module = generator.generate_fifo(
        module_name="simple_fifo",
        depth=16,
        data_width=32
    )

    # Save RTL
    Path("02_rtl").mkdir(exist_ok=True)
    module.save("02_rtl")

    print(f"\n✓ Generated RTL:")
    print(f"  - File: 02_rtl/simple_fifo.v")
    print(f"  - Lines: {module.lines_of_code}")
    print(f"  - Ports: {len(module.ports)}")

    # Run lint
    print("\n" + "-"*60)
    print("Lint Check")
    print("-"*60)

    lint_checker = LintChecker()
    result = lint_checker.check(module.verilog_code, "simple_fifo.v")

    if result.error_count == 0:
        print("✓ No errors")
    else:
        print(f"✗ {result.error_count} errors")
        for issue in result.issues:
            if issue.severity == 'error':
                print(f"  Line {issue.line_number}: {issue.message}")

    if result.warning_count > 0:
        print(f"⚠ {result.warning_count} warnings")

    # Static analysis
    print("\n" + "-"*60)
    print("Static Analysis")
    print("-"*60)

    depth_result = analyze_logic_depth(module.verilog_code, target_depth=10)
    print(f"Logic depth violations: {depth_result['violation_count']}")

if __name__ == "__main__":
    main()
