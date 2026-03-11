#!/usr/bin/env python3
"""Step 1: Define architecture specification."""

import sys
sys.path.insert(0, '../verilog_flow')

from verilog_flow import MicroArchitect
import json

def main():
    print("="*60)
    print("Stage 1: Define Architecture")
    print("="*60)

    requirements = {
        "module_name": "simple_fifo",
        "target_frequency_mhz": 200,
        "data_width": 32,
        "fifo_depth": 16,
        "description": "Simple synchronous FIFO for data buffering"
    }

    # Save requirements
    with open("requirements.json", "w") as f:
        json.dump(requirements, f, indent=2)
    print("\n✓ Requirements saved to requirements.json")

    # Generate architecture
    architect = MicroArchitect()
    spec = architect.design_from_requirements(
        module_name=requirements["module_name"],
        requirements=requirements
    )

    # Save specification
    import os
    os.makedirs("01_spec", exist_ok=True)
    spec.save("01_spec")

    print(f"\n✓ Architecture specification:")
    print(f"  - Module: {spec.module_name}")
    print(f"  - Target: {spec.timing_budget.target_frequency_mhz} MHz")
    print(f"  - Pipeline: {len(spec.pipeline_stages)} stages")
    print(f"  - Est. LUTs: {spec.resource_mapping.lut_estimate}")
    print(f"  - Est. FFs: {spec.resource_mapping.ff_estimate}")

    print("\n" + architect.explain_design(spec))

if __name__ == "__main__":
    main()
