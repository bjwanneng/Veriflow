#!/usr/bin/env python3
"""Run all steps in the workflow."""

import sys
import subprocess

def run_step(name, script):
    """Run a single step."""
    print("\n" + "="*70)
    print(f"  {name}")
    print("="*70)

    result = subprocess.run([sys.executable, script])

    if result.returncode != 0:
        print(f"\n✗ Failed: {name}")
        return False
    return True

def main():
    steps = [
        ("Step 1: Define Architecture", "01_define_spec.py"),
        ("Step 2: Generate RTL", "02_generate_rtl.py"),
        ("Step 3: Run Simulation", "03_run_simulation.py"),
        ("Step 4: Run Synthesis", "04_run_synthesis.py"),
    ]

    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  VeriFlow Example Project".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    for name, script in steps:
        if not run_step(name, script):
            sys.exit(1)

    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  All Steps Completed!".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)

    print("\nOutput:")
    print("  - 01_spec/          : Architecture specification")
    print("  - 02_rtl/           : Generated RTL code")
    print("  - 03_simulation/    : Simulation results")
    print("  - 04_synthesis/     : Synthesis reports")

if __name__ == "__main__":
    main()
