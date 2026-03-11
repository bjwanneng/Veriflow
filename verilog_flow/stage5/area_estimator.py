"""Area Estimator for Stage 5."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AreaBreakdown:
    """Area breakdown by resource type."""

    # Logic
    lut_count: int = 0
    flip_flop_count: int = 0
    carry_chain_count: int = 0

    # Memory
    bram_count: int = 0
    bram_bits: int = 0
    distributed_ram_bits: int = 0

    # DSP
    dsp_count: int = 0
    multiplier_count: int = 0

    # I/O
    input_count: int = 0
    output_count: int = 0
    inout_count: int = 0

    # Routing (estimated)
    estimated_routing_overhead: float = 1.0  # Multiplier

    def total_logic_cells(self) -> int:
        """Calculate total logic cells."""
        return self.lut_count + self.flip_flop_count + self.carry_chain_count


@dataclass
class DeviceUtilization:
    """Utilization relative to device capacity."""

    device_name: str = "generic"

    # Capacity
    total_luts: int = 10000
    total_ffs: int = 20000
    total_brams: int = 50
    total_dsps: int = 50

    # Utilization
    lut_utilization: float = 0.0
    ff_utilization: float = 0.0
    bram_utilization: float = 0.0
    dsp_utilization: float = 0.0

    def calculate(self, area: AreaBreakdown):
        """Calculate utilization percentages."""
        if self.total_luts > 0:
            self.lut_utilization = area.lut_count / self.total_luts
        if self.total_ffs > 0:
            self.ff_utilization = area.flip_flop_count / self.total_ffs
        if self.total_brams > 0:
            self.bram_utilization = area.bram_count / self.total_brams
        if self.total_dsps > 0:
            self.dsp_utilization = area.dsp_count / self.total_dsps

    @property
    def total_utilization(self) -> float:
        """Calculate overall utilization."""
        return max(self.lut_utilization, self.ff_utilization,
                   self.bram_utilization, self.dsp_utilization)


@dataclass
class AreaResult:
    """Result of area estimation."""

    # Cell counts
    cell_count: int = 0

    # Detailed breakdown
    breakdown: AreaBreakdown = field(default_factory=AreaBreakdown)

    # Device utilization
    utilization: DeviceUtilization = field(default_factory=DeviceUtilization)

    # Estimates
    estimated_silicon_area_um2: float = 0.0
    estimated_power_mw: float = 0.0

    @property
    def gate_count_estimate(self) -> int:
        """Estimate equivalent gate count."""
        # Rough estimate: 6 gates per LUT, 8 gates per FF
        lut_gates = self.breakdown.lut_count * 6
        ff_gates = self.breakdown.flip_flop_count * 8
        return lut_gates + ff_gates

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cell_count": self.cell_count,
            "gate_count_estimate": self.gate_count_estimate,
            "breakdown": {
                "lut_count": self.breakdown.lut_count,
                "flip_flop_count": self.breakdown.flip_flop_count,
                "carry_chain_count": self.breakdown.carry_chain_count,
                "bram_count": self.breakdown.bram_count,
                "bram_bits": self.breakdown.bram_bits,
                "dsp_count": self.breakdown.dsp_count,
                "total_logic_cells": self.breakdown.total_logic_cells(),
            },
            "utilization": {
                "device": self.utilization.device_name,
                "lut_utilization": f"{self.utilization.lut_utilization*100:.1f}%",
                "ff_utilization": f"{self.utilization.ff_utilization*100:.1f}%",
                "bram_utilization": f"{self.utilization.bram_utilization*100:.1f}%",
                "dsp_utilization": f"{self.utilization.dsp_utilization*100:.1f}%",
                "total_utilization": f"{self.utilization.total_utilization*100:.1f}%",
            },
            "estimates": {
                "silicon_area_um2": self.estimated_silicon_area_um2,
                "power_mw": self.estimated_power_mw,
            },
        }


class AreaEstimator:
    """Estimate area utilization from synthesis results."""

    # Device definitions (simplified)
    DEVICE_DEFINITIONS = {
        "generic": {
            "luts": 100000,
            "ffs": 200000,
            "brams": 1000,
            "dsps": 1000,
        },
        "ice40": {
            "luts": 7680,
            "ffs": 7680,
            "brams": 32,
            "dsps": 0,
        },
        "ecp5": {
            "luts": 84000,
            "ffs": 84000,
            "brams": 756,
            "dsps": 312,
        },
        "xc7a100t": {
            "luts": 63400,
            "ffs": 126800,
            "brams": 135,
            "dsps": 240,
        },
    }

    def __init__(self, target_device: str = "generic"):
        self.target_device = target_device
        self.device_specs = self.DEVICE_DEFINITIONS.get(target_device, self.DEVICE_DEFINITIONS["generic"])

    def estimate_from_synthesis(self, synthesis_result: Dict[str, Any]) -> AreaResult:
        """Estimate area from synthesis results."""

        result = AreaResult()

        # Extract cell counts
        cells = synthesis_result.get("cells", {})

        # Count resources
        result.breakdown.lut_count = cells.get("$lut", 0)
        result.breakdown.flip_flop_count = (
            cells.get("$dff", 0) +
            cells.get("$dffe", 0) +
            cells.get("$adff", 0) +
            cells.get("$adffe", 0)
        )
        result.breakdown.carry_chain_count = cells.get("$alu", 0)
        result.breakdown.bram_count = cells.get("$mem", 0)
        result.breakdown.multiplier_count = cells.get("$mul", 0)
        result.breakdown.dsp_count = (
            cells.get("$mul", 0) +
            cells.get("$div", 0) +
            cells.get("$divfloor", 0)
        )

        # Total cells
        result.cell_count = sum(cells.values())

        # Calculate utilization
        result.utilization = DeviceUtilization(
            device_name=self.target_device,
            total_luts=self.device_specs["luts"],
            total_ffs=self.device_specs["ffs"],
            total_brams=self.device_specs["brams"],
            total_dsps=self.device_specs["dsps"],
        )
        result.utilization.calculate(result.breakdown)

        # Estimate silicon area (very rough approximation)
        # Assume: 100 um^2 per LUT, 80 um^2 per FF, etc.
        lut_area = result.breakdown.lut_count * 100
        ff_area = result.breakdown.flip_flop_count * 80
        bram_area = result.breakdown.bram_count * 10000  # BRAMs are large
        dsp_area = result.breakdown.dsp_count * 5000

        result.estimated_silicon_area_um2 = lut_area + ff_area + bram_area + dsp_area

        # Estimate power (very rough)
        # Assume: 10 uW per LUT, 5 uW per FF at 100MHz
        result.estimated_power_mw = (
            result.breakdown.lut_count * 0.01 +
            result.breakdown.flip_flop_count * 0.005
        )

        return result

    def estimate_from_cells(self, cells: Dict[str, int]) -> AreaResult:
        """Estimate area from cell dictionary."""
        return self.estimate_from_synthesis({"cells": cells})

    def compare_utilization(
        self, result: AreaResult, reference: Optional[AreaResult] = None
    ) -> Dict[str, Any]:
        """Compare utilization against reference or target."""

        comparison = {
            "target_device": self.target_device,
            "current_utilization": result.utilization.total_utilization,
            "status": "OK",
        }

        if reference:
            # Compare against reference design
            comparison["reference_cell_count"] = reference.cell_count
            comparison["ratio"] = (
                result.cell_count / reference.cell_count
                if reference.cell_count > 0 else 0
            )

        # Check if approaching device limits
        util = result.utilization.total_utilization
        if util > 0.9:
            comparison["status"] = "CRITICAL"
            comparison["warning"] = "Approaching device capacity limits!"
        elif util > 0.7:
            comparison["status"] = "WARNING"
            comparison["warning"] = "High utilization, consider optimization"

        return comparison

    def generate_area_report(self, result: AreaResult, output_path: Path) -> Path:
        """Generate a detailed area report."""

        lines = []
        lines.append("=" * 80)
        lines.append("Area Analysis Report")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Target Device: {self.target_device}")
        lines.append("")

        lines.append("Resource Usage:")
        lines.append(f"  LUTs:        {result.breakdown.lut_count:,}")
        lines.append(f"  Flip-Flops:  {result.breakdown.flip_flop_count:,}")
        lines.append(f"  Carry Chain: {result.breakdown.carry_chain_count:,}")
        lines.append(f"  BRAMs:       {result.breakdown.bram_count:,}")
        lines.append(f"  DSPs:        {result.breakdown.dsp_count:,}")
        lines.append(f"  Total Cells: {result.cell_count:,}")
        lines.append("")

        lines.append("Gate Count Estimate:")
        lines.append(f"  Equivalent Gates: ~{result.gate_count_estimate:,}")
        lines.append("")

        lines.append("Device Utilization:")
        lines.append(f"  LUTs:  {result.utilization.lut_utilization*100:.1f}%")
        lines.append(f"  FFs:   {result.utilization.ff_utilization*100:.1f}%")
        lines.append(f"  BRAMs: {result.utilization.bram_utilization*100:.1f}%")
        lines.append(f"  DSPs:  {result.utilization.dsp_utilization*100:.1f}%")
        lines.append(f"  Total: {result.utilization.total_utilization*100:.1f}%")
        lines.append("")

        lines.append("Estimates:")
        lines.append(f"  Silicon Area: ~{result.estimated_silicon_area_um2/1000000:.2f} mm^2")
        lines.append(f"  Power (est.): ~{result.estimated_power_mw:.2f} mW @ 100MHz")
        lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
