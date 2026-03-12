"""Synthesis Runner for Stage 5."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .yosys_interface import YosysInterface


@dataclass
class SynthesisResult:
    """Result of synthesis run."""

    success: bool
    module_name: str

    # Timing
    target_frequency_mhz: float = 100.0
    estimated_max_frequency_mhz: float = 0.0
    timing_met: bool = False
    worst_negative_slack_ns: float = 0.0

    # Area
    cell_count: int = 0
    lut_count: int = 0
    flip_flop_count: int = 0
    bram_count: int = 0
    dsp_count: int = 0

    # Metrics
    synthesis_time_seconds: float = 0.0
    memory_usage_mb: float = 0.0

    # Files
    synthesized_netlist: Optional[Path] = None
    json_output: Optional[Path] = None
    log_file: Optional[Path] = None

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def utilization_score(self) -> float:
        """Calculate utilization score (0-1)."""
        # Simplified scoring based on cell count
        # Lower is better for area
        if self.cell_count == 0:
            return 0.0
        # Normalize: assume 10000 cells is "full"
        return min(1.0, self.cell_count / 10000.0)

    @property
    def timing_score(self) -> float:
        """Calculate timing score (0-1)."""
        if self.target_frequency_mhz == 0:
            return 0.0
        ratio = self.estimated_max_frequency_mhz / self.target_frequency_mhz
        # Ratio > 1 means timing met, < 1 means timing failed
        return min(1.0, max(0.0, ratio))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "module_name": self.module_name,
            "target_frequency_mhz": self.target_frequency_mhz,
            "estimated_max_frequency_mhz": self.estimated_max_frequency_mhz,
            "timing_met": self.timing_met,
            "worst_negative_slack_ns": self.worst_negative_slack_ns,
            "cell_count": self.cell_count,
            "lut_count": self.lut_count,
            "flip_flop_count": self.flip_flop_count,
            "bram_count": self.bram_count,
            "dsp_count": self.dsp_count,
            "synthesis_time_seconds": self.synthesis_time_seconds,
            "memory_usage_mb": self.memory_usage_mb,
            "utilization_score": self.utilization_score,
            "timing_score": self.timing_score,
            "synthesized_netlist": str(self.synthesized_netlist) if self.synthesized_netlist else None,
            "json_output": str(self.json_output) if self.json_output else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def save(self, output_path: Path) -> Path:
        """Save result to JSON file."""
        output_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return output_path


class SynthesisRunner:
    """Run synthesis and collect results."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("synthesis_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.yosys = YosysInterface()

    def run(
        self,
        verilog_files: List[Path],
        top_module: str,
        target_frequency_mhz: float = 100.0,
        target_device: str = "generic",
        flatten: bool = False,
    ) -> SynthesisResult:
        """Run synthesis on Verilog files."""

        start_time = time.time()

        result = SynthesisResult(
            success=False,
            module_name=top_module,
            target_frequency_mhz=target_frequency_mhz,
        )

        # Check Yosys availability
        if not self.yosys.available:
            result.errors.append(self.yosys.install_hint())
            return result

        # Run synthesis
        try:
            synth_output = self.yosys.synthesize(
                verilog_files=verilog_files,
                top_module=top_module,
                target=target_device,
                output_dir=self.output_dir,
                flatten=flatten,
            )

            # Populate result
            result.success = synth_output.get("success", False)
            result.synthesis_time_seconds = time.time() - start_time

            # Extract cell counts
            cells = synth_output.get("cells", {})

            # Use stat summary line for total cell count (more reliable than sum)
            result.cell_count = synth_output.get("cell_count_total", 0)
            if result.cell_count == 0:
                result.cell_count = sum(cells.values())

            # FF: match all cell types containing DFF/dff (covers $_DFF_P_, $_DFFE_PP_, $dff, etc.)
            result.flip_flop_count = sum(
                cnt for name, cnt in cells.items()
                if 'dff' in name.lower() or 'sdff' in name.lower()
            )

            # LUT: match $lut and gate-level primitives
            result.lut_count = sum(
                cnt for name, cnt in cells.items()
                if 'lut' in name.lower() or name.lower() in (
                    '$_and_', '$_or_', '$_xor_', '$_not_', '$_mux_',
                    '$_nand_', '$_nor_', '$_xnor_', '$_aoi3_', '$_oai3_',
                )
            )

            result.bram_count = sum(
                cnt for name, cnt in cells.items()
                if 'mem' in name.lower()
            )
            result.dsp_count = sum(
                cnt for name, cnt in cells.items()
                if name.lower() in ('$mul', '$div', '$_mul_', '$_div_')
            )

            # Estimate timing
            result.estimated_max_frequency_mhz = self.yosys.estimate_max_frequency(
                synth_output
            )
            result.timing_met = result.estimated_max_frequency_mhz >= target_frequency_mhz

            if result.timing_met:
                # Positive slack
                period_ns = 1000.0 / target_frequency_mhz
                achieved_period_ns = 1000.0 / result.estimated_max_frequency_mhz
                result.worst_negative_slack_ns = period_ns - achieved_period_ns
            else:
                # Negative slack
                period_ns = 1000.0 / target_frequency_mhz
                achieved_period_ns = 1000.0 / result.estimated_max_frequency_mhz
                result.worst_negative_slack_ns = period_ns - achieved_period_ns

            # Set output files
            result.synthesized_netlist = self.output_dir / "synthesized.v"
            result.json_output = self.output_dir / "synthesis.json"

            # Save log
            log_path = self.output_dir / "synthesis.log"
            log_content = synth_output.get("raw_output", "")
            log_path.write_text(log_content, encoding="utf-8")
            result.log_file = log_path

            # Collect warnings
            if "warnings" in synth_output:
                result.warnings.extend(synth_output["warnings"])
            if "errors" in synth_output:
                result.errors.extend(synth_output["errors"])

        except Exception as e:
            result.errors.append(f"Synthesis failed: {e}")
            result.synthesis_time_seconds = time.time() - start_time

        return result

    def check_timing_closure(
        self, result: SynthesisResult, slack_threshold_ns: float = 0.0
    ) -> bool:
        """Check if design meets timing closure."""
        if not result.success:
            return False

        return result.worst_negative_slack_ns >= slack_threshold_ns
