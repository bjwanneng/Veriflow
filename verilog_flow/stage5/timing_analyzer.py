"""Timing Analyzer for Stage 5."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TimingPath:
    """A single timing path."""
    path_name: str
    start_point: str
    end_point: str
    path_type: str  # setup, hold, recovery, removal

    # Timing values
    arrival_time_ns: float = 0.0
    required_time_ns: float = 0.0
    slack_ns: float = 0.0

    # Path details
    logic_levels: int = 0
    cells: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate slack."""
        self.slack_ns = self.required_time_ns - self.arrival_time_ns


@dataclass
class TimingResult:
    """Result of timing analysis."""

    target_frequency_mhz: float = 100.0
    estimated_max_frequency_mhz: float = 0.0

    # Slack summary
    worst_setup_slack_ns: float = 0.0
    worst_hold_slack_ns: float = 0.0
    total_negative_slack_ns: float = 0.0

    # Path counts
    violating_paths: int = 0
    total_paths: int = 0

    # Detailed paths
    critical_paths: List[TimingPath] = field(default_factory=list)

    @property
    def timing_met(self) -> bool:
        """Check if timing is met."""
        return self.worst_setup_slack_ns >= 0 and self.worst_hold_slack_ns >= 0

    @property
    def fmax_mhz(self) -> float:
        """Calculate maximum frequency."""
        if self.worst_setup_slack_ns >= 0:
            return self.target_frequency_mhz
        # Estimate based on negative slack
        period_ns = 1000.0 / self.target_frequency_mhz
        actual_period_ns = period_ns - self.worst_setup_slack_ns
        return 1000.0 / actual_period_ns

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_frequency_mhz": self.target_frequency_mhz,
            "estimated_max_frequency_mhz": self.estimated_max_frequency_mhz,
            "timing_met": self.timing_met,
            "worst_setup_slack_ns": self.worst_setup_slack_ns,
            "worst_hold_slack_ns": self.worst_hold_slack_ns,
            "total_negative_slack_ns": self.total_negative_slack_ns,
            "violating_paths": self.violating_paths,
            "total_paths": self.total_paths,
            "fmax_mhz": self.fmax_mhz,
            "critical_paths": [
                {
                    "name": p.path_name,
                    "start": p.start_point,
                    "end": p.end_point,
                    "slack_ns": p.slack_ns,
                    "logic_levels": p.logic_levels,
                }
                for p in self.critical_paths[:10]  # Top 10
            ],
        }


class TimingAnalyzer:
    """Analyze timing from synthesis results."""

    def __init__(self, target_frequency_mhz: float = 100.0):
        self.target_frequency_mhz = target_frequency_mhz
        self.clock_period_ns = 1000.0 / target_frequency_mhz

    def analyze_from_synthesis(
        self, synthesis_json: Path, synthesis_result: Dict[str, Any]
    ) -> TimingResult:
        """Analyze timing from synthesis output."""

        result = TimingResult(target_frequency_mhz=self.target_frequency_mhz)

        # Extract cell information
        cells = synthesis_result.get("cells", {})

        # Estimate timing based on cell types
        lut_count = cells.get("$lut", 0)
        dff_count = cells.get("$dff", 0) + cells.get("$dffe", 0)

        # Rough timing estimation
        # Assume 500ps per LUT, 100ps per flip-flop clock-to-Q
        estimated_delay_ns = (lut_count * 0.5) + (dff_count * 0.1)

        if estimated_delay_ns > 0:
            result.estimated_max_frequency_mhz = min(1000.0 / estimated_delay_ns, 1000.0)
        else:
            result.estimated_max_frequency_mhz = self.target_frequency_mhz

        # Calculate slacks
        achieved_period_ns = 1000.0 / result.estimated_max_frequency_mhz
        result.worst_setup_slack_ns = self.clock_period_ns - achieved_period_ns

        # Assume hold is met (typical for FPGA designs)
        result.worst_hold_slack_ns = 0.5  # Assume 500ps hold slack

        # Count paths
        result.total_paths = dff_count
        if result.worst_setup_slack_ns < 0:
            result.violating_paths = max(1, dff_count // 10)  # Estimate

        # Create critical path
        if result.violating_paths > 0:
            critical_path = TimingPath(
                path_name="critical_path_1",
                start_point="input_reg",
                end_point="output_reg",
                path_type="setup",
                arrival_time_ns=achieved_period_ns,
                required_time_ns=self.clock_period_ns,
                logic_levels=lut_count // 2 if lut_count > 0 else 1,
            )
            result.critical_paths.append(critical_path)

        return result

    def estimate_critical_path_delay(
        self, logic_depth: int, fanout: int = 1
    ) -> float:
        """Estimate critical path delay in nanoseconds.

        Args:
            logic_depth: Number of logic levels
            fanout: Average fanout

        Returns:
            Estimated delay in nanoseconds
        """
        # Simplified model: base delay + per-level delay + fanout penalty
        base_delay_ns = 0.5
        per_level_ns = 0.5
        fanout_penalty_ns = 0.1 * fanout

        return base_delay_ns + (logic_depth * per_level_ns) + fanout_penalty_ns

    def calculate_required_period(
        self, setup_slack_ns: float, hold_slack_ns: float
    ) -> float:
        """Calculate required clock period for timing closure."""
        # Required period = current period - WNS (worst negative slack)
        current_period_ns = self.clock_period_ns
        required_period_ns = current_period_ns - min(0, setup_slack_ns)
        return required_period_ns

    def generate_timing_report(self, result: TimingResult, output_path: Path) -> Path:
        """Generate a detailed timing report."""

        lines = []
        lines.append("=" * 80)
        lines.append("Timing Analysis Report")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Target Frequency: {result.target_frequency_mhz:.2f} MHz")
        lines.append(f"Target Period: {self.clock_period_ns:.3f} ns")
        lines.append("")

        lines.append(f"Estimated Max Frequency: {result.estimated_max_frequency_mhz:.2f} MHz")
        lines.append(f"Estimated Min Period: {1000.0/result.estimated_max_frequency_mhz:.3f} ns")
        lines.append("")

        lines.append("Slack Summary:")
        lines.append(f"  Worst Setup Slack: {result.worst_setup_slack_ns:.3f} ns")
        lines.append(f"  Worst Hold Slack:  {result.worst_hold_slack_ns:.3f} ns")
        lines.append(f"  Timing Met: {result.timing_met}")
        lines.append("")

        lines.append(f"Path Summary:")
        lines.append(f"  Total Paths: {result.total_paths}")
        lines.append(f"  Violating Paths: {result.violating_paths}")
        lines.append("")

        if result.critical_paths:
            lines.append("Critical Paths:")
            for i, path in enumerate(result.critical_paths[:5], 1):
                lines.append(f"  {i}. {path.path_name}")
                lines.append(f"     Start: {path.start_point}")
                lines.append(f"     End: {path.end_point}")
                lines.append(f"     Slack: {path.slack_ns:.3f} ns")
                lines.append(f"     Logic Levels: {path.logic_levels}")
                lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
