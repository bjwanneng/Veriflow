"""
Stage 5 Enhanced: KPI Comparator and Automatic Fallback.

Implements the full Stage 5 requirements from original design:
- KPI comparison (Stage 5 results vs Stage 1.5 budget)
- Automatic fallback to Stage 1.5 if KPI not met
- Failure reason recording to Experience DB
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime

from ..common.experience_db import ExperienceDB, FailureCase
from ..stage1.stage15_enhanced import FallbackThresholds, FallbackAction


class KPIStatus(Enum):
    """Status of a KPI check."""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class FallbackTarget(Enum):
    """Where to fall back to when KPI fails."""
    STAGE_1_5 = "stage_1_5"        # Re-do micro-architecture decisions
    STAGE_2 = "stage_2"              # Re-do timing modeling
    STAGE_3 = "stage_3"              # Re-do code generation with different options
    NO_FALLBACK = "no_fallback"      # Cannot fall back, require manual intervention


@dataclass
class KPIComparison:
    """Result of comparing a single KPI."""
    kpi_name: str
    stage1_budget: Optional[float] = None
    stage5_actual: Optional[float] = None
    status: KPIStatus = KPIStatus.PASS
    margin: Optional[float] = None
    description: str = ""

    @property
    def passed(self) -> bool:
        return self.status == KPIStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kpi_name": self.kpi_name,
            "stage1_budget": self.stage1_budget,
            "stage5_actual": self.stage5_actual,
            "status": self.status.value,
            "margin": self.margin,
            "description": self.description
        }


@dataclass
class SynthesisKPIs:
    """KPI results from synthesis."""
    # Timing
    max_frequency_mhz: Optional[float] = None
    critical_path_delay_ns: Optional[float] = None
    setup_slack_ns: Optional[float] = None
    hold_slack_ns: Optional[float] = None
    worst_neg_slack_ns: Optional[float] = None

    # Area
    total_luts: Optional[int] = None
    total_ffs: Optional[int] = None
    bram_count: Optional[int] = None
    dsp_count: Optional[int] = None
    total_cells: Optional[int] = None

    # Power (estimated)
    dynamic_power_mw: Optional[float] = None
    leakage_power_mw: Optional[float] = None
    total_power_mw: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_yosys_report(cls, report: Dict[str, Any]) -> 'SynthesisKPIs':
        """Extract KPIs from Yosys synthesis report."""
        kpis = cls()

        # Extract cell counts
        cells = report.get('cells', {})
        kpis.total_cells = report.get('cell_count_total', sum(cells.values()))

        # Count LUT-like cells
        lut_cells = 0
        ff_cells = 0
        for cell_name, count in cells.items():
            cn_lower = cell_name.lower()
            if 'lut' in cn_lower or cn_lower in ('$_and_', '$_or_', '$_xor_', '$_not_', '$_mux_',
                                                  '$_nand_', '$_nor_', '$_xnor_'):
                lut_cells += count
            elif 'dff' in cn_lower or 'sdff' in cn_lower:
                ff_cells += count

        kpis.total_luts = lut_cells
        kpis.total_ffs = ff_cells

        # Estimate max frequency from cell count
        if kpis.total_luts:
            # Heuristic: each LUT ~0.5ns, max freq ~ 1/(total_delay)
            estimated_depth = (kpis.total_luts ** 0.5)  # sqrt as rough estimate
            kpis.critical_path_delay_ns = estimated_depth * 0.5
            if kpis.critical_path_delay_ns > 0:
                kpis.max_frequency_mhz = 1000.0 / kpis.critical_path_delay_ns

        return kpis

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SynthesisKPIs':
        """Load from dictionary."""
        kpis = cls()
        for key, value in data.items():
            if hasattr(kpis, key):
                setattr(kpis, key, value)
        return kpis


@dataclass
class FailureReason:
    """Detailed reason for a failure."""
    category: str
    subcategory: str
    description: str
    affected_kpis: List[str] = field(default_factory=list)
    suggested_fix: str = ""
    related_failure_cases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KPIComparisonReport:
    """Complete KPI comparison report."""
    report_id: str
    design_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Comparisons
    comparisons: List[KPIComparison] = field(default_factory=list)

    # Overall status
    overall_status: KPIStatus = KPIStatus.PASS
    requires_fallback: bool = False
    fallback_target: FallbackTarget = FallbackTarget.NO_FALLBACK

    # Failure analysis
    failure_reasons: List[FailureReason] = field(default_factory=list)

    def add_comparison(self, comparison: KPIComparison):
        """Add a KPI comparison and update overall status."""
        self.comparisons.append(comparison)

        if comparison.status == KPIStatus.FAIL:
            self.overall_status = KPIStatus.FAIL
            self.requires_fallback = True
        elif comparison.status == KPIStatus.WARNING and self.overall_status == KPIStatus.PASS:
            self.overall_status = KPIStatus.WARNING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "design_name": self.design_name,
            "timestamp": self.timestamp,
            "overall_status": self.overall_status.value,
            "requires_fallback": self.requires_fallback,
            "fallback_target": self.fallback_target.value,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "failure_reasons": [r.to_dict() for r in self.failure_reasons]
        }

    def save(self, output_path: Path):
        """Save report to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_markdown(self) -> str:
        """Generate human-readable markdown report."""
        md = f"# KPI Comparison Report: {self.design_name}\n\n"
        md += f"Generated: {self.timestamp}\n\n"

        status_icon = {
            KPIStatus.PASS: "✅",
            KPIStatus.WARNING: "🟡",
            KPIStatus.FAIL: "❌"
        }

        md += f"## Overall Status: {status_icon[self.overall_status]} {self.overall_status.value.upper()}\n\n"

        if self.requires_fallback:
            md += f"### 🔴 REQUIRES FALLBACK to {self.fallback_target.value}\n\n"

        md += "## KPI Comparisons\n\n"
        md += "| KPI | Stage 1 Budget | Stage 5 Actual | Status | Margin |\n"
        md += "|-----|----------------|----------------|--------|--------|\n"

        for comp in self.comparisons:
            budget = comp.stage1_budget or "N/A"
            actual = comp.stage5_actual or "N/A"
            margin = comp.margin if comp.margin is not None else "N/A"
            md += f"| {comp.kpi_name} | {budget} | {actual} | {status_icon[comp.status]} {comp.status.value} | {margin} |\n"

        md += "\n"

        if self.failure_reasons:
            md += "## Failure Reasons\n\n"
            for reason in self.failure_reasons:
                md += f"### {reason.category}: {reason.subcategory}\n\n"
                md += f"{reason.description}\n\n"
                if reason.affected_kpis:
                    md += f"Affected KPIs: {', '.join(reason.affected_kpis)}\n\n"
                if reason.suggested_fix:
                    md += f"**Suggested Fix**: {reason.suggested_fix}\n\n"

        if self.requires_fallback:
            md += "## Fallback Plan\n\n"
            md += f"**Target**: {self.fallback_target.value}\n\n"
            md += "### Action Items:\n"
            if self.fallback_target == FallbackTarget.STAGE_1_5:
                md += "- [ ] Re-evaluate micro-architecture decisions\n"
                md += "- [ ] Consider additional pipeline stages\n"
                md += "- [ ] Adjust resource selection (DistRAM vs BlockRAM)\n"
            elif self.fallback_target == FallbackTarget.STAGE_2:
                md += "- [ ] Revise timing scenarios\n"
                md += "- [ ] Adjust latency budget\n"
            elif self.fallback_target == FallbackTarget.STAGE_3:
                md += "- [ ] Re-generate RTL with different options\n"
                md += "- [ ] Apply logic depth optimizations\n"

        return md


class KPIComparator:
    """
    Compares Stage 5 synthesis results against Stage 1.5 budgets.

    Determines if fallback is needed and where to fall back to.
    """

    # KPI definitions with thresholds
    KPI_DEFINITIONS = [
        ("max_frequency_mhz", "Target Frequency (MHz)", "min", KPIStatus.FAIL),
        ("critical_path_delay_ns", "Critical Path (ns)", "max", KPIStatus.FAIL),
        ("setup_slack_ns", "Setup Slack (ns)", "min", KPIStatus.WARNING),
        ("total_luts", "Total LUTs", "max", KPIStatus.WARNING),
        ("total_ffs", "Total FFs", "max", KPIStatus.WARNING),
        ("total_power_mw", "Total Power (mW)", "max", KPIStatus.WARNING),
    ]

    def __init__(
        self,
        experience_db: Optional[ExperienceDB] = None,
        fallback_thresholds: Optional[FallbackThresholds] = None
    ):
        self.experience_db = experience_db or ExperienceDB()
        self.fallback_thresholds = fallback_thresholds or FallbackThresholds()

    def compare_kpis(
        self,
        design_name: str,
        stage1_budget: Dict[str, Any],
        stage5_results: SynthesisKPIs
    ) -> KPIComparisonReport:
        """
        Compare Stage 5 results against Stage 1 budget.

        Args:
            design_name: Name of the design
            stage1_budget: Budget from Stage 1 spec
            stage5_results: Actual results from Stage 5 synthesis

        Returns:
            Complete comparison report with fallback decision
        """
        report = KPIComparisonReport(
            report_id=f"kpi_comp_{int(datetime.now().timestamp())}",
            design_name=design_name
        )

        # Compare each KPI
        for kpi_name, desc, direction, fail_severity in self.KPI_DEFINITIONS:
            budget = self._extract_budget(stage1_budget, kpi_name)
            actual = getattr(stage5_results, kpi_name, None)

            if budget is not None and actual is not None:
                comparison = self._compare_single_kpi(
                    kpi_name, budget, actual, direction, fail_severity
                )
                comparison.description = desc
                report.add_comparison(comparison)

        # Determine fallback target
        report.fallback_target = self._determine_fallback_target(report)
        report.requires_fallback = report.overall_status == KPIStatus.FAIL

        # Analyze failure reasons
        if report.requires_fallback:
            report.failure_reasons = self._analyze_failure_reasons(report, stage5_results)

        # Record failures to Experience DB
        if report.failure_reasons:
            self._record_failures_to_experience_db(report, design_name, stage5_results)

        return report

    def _extract_budget(self, budget: Dict[str, Any], kpi_name: str) -> Optional[float]:
        """Extract a budget value from Stage 1 spec."""
        # Try direct key
        if kpi_name in budget:
            return float(budget[kpi_name])

        # Try nested in timing_constraints
        if "timing_constraints" in budget:
            tc = budget["timing_constraints"]
            if kpi_name in tc:
                return float(tc[kpi_name])

        # Try derived values
        if kpi_name == "max_frequency_mhz" and "target_frequency_mhz" in budget:
            return float(budget["target_frequency_mhz"])
        if kpi_name == "critical_path_delay_ns" and "clock_period_ns" in budget:
            return float(budget["clock_period_ns"]) * 0.9  # 90% of period

        # Try resource_mapping
        if "resource_mapping" in budget:
            rm = budget["resource_mapping"]
            if kpi_name == "total_luts" and "lut_estimate" in rm:
                return float(rm["lut_estimate"])
            if kpi_name == "total_ffs" and "ff_estimate" in rm:
                return float(rm["ff_estimate"])

        return None

    def _compare_single_kpi(
        self,
        kpi_name: str,
        budget: float,
        actual: float,
        direction: str,  # "min" or "max"
        fail_severity: KPIStatus
    ) -> KPIComparison:
        """Compare a single KPI."""
        comparison = KPIComparison(kpi_name=kpi_name, stage1_budget=budget, stage5_actual=actual)

        if direction == "min":
            # Actual should be >= budget
            comparison.margin = actual - budget
            if actual >= budget:
                comparison.status = KPIStatus.PASS
            elif actual >= budget * 0.9:  # Within 10%
                comparison.status = KPIStatus.WARNING
            else:
                comparison.status = fail_severity
        else:  # "max"
            # Actual should be <= budget
            comparison.margin = budget - actual
            if actual <= budget:
                comparison.status = KPIStatus.PASS
            elif actual <= budget * 1.1:  # Within 10%
                comparison.status = KPIStatus.WARNING
            else:
                comparison.status = fail_severity

        return comparison

    def _determine_fallback_target(self, report: KPIComparisonReport) -> FallbackTarget:
        """Determine where to fall back to based on failures."""
        if not report.requires_fallback:
            return FallbackTarget.NO_FALLBACK

        # Classify failures
        timing_failures = [c for c in report.comparisons
                          if c.status == KPIStatus.FAIL
                          and "frequency" in c.kpi_name or "delay" in c.kpi_name or "slack" in c.kpi_name]

        area_failures = [c for c in report.comparisons
                        if c.status == KPIStatus.FAIL
                        and "lut" in c.kpi_name or "ff" in c.kpi_name or "cell" in c.kpi_name]

        power_failures = [c for c in report.comparisons
                         if c.status == KPIStatus.FAIL
                         and "power" in c.kpi_name]

        # Decision tree
        if timing_failures and area_failures:
            # Both timing and area - need architecture changes
            return FallbackTarget.STAGE_1_5
        elif timing_failures:
            # Timing issues - can try re-timing first, else architecture
            # Check if it's a small margin
            small_margin = all(abs(c.margin or 0) < c.stage1_budget * 0.2
                              for c in timing_failures if c.stage1_budget)
            if small_margin:
                return FallbackTarget.STAGE_3  # Try code optimization first
            else:
                return FallbackTarget.STAGE_1_5
        elif area_failures:
            # Area issues - architecture or resource changes
            return FallbackTarget.STAGE_1_5
        elif power_failures:
            # Power issues - architecture changes
            return FallbackTarget.STAGE_1_5
        else:
            # Other failures - try code gen first
            return FallbackTarget.STAGE_3

    def _analyze_failure_reasons(
        self,
        report: KPIComparisonReport,
        stage5_results: SynthesisKPIs
    ) -> List[FailureReason]:
        """Analyze and categorize failure reasons."""
        reasons = []

        # Timing failures
        freq_comp = next((c for c in report.comparisons if c.kpi_name == "max_frequency_mhz"), None)
        if freq_comp and freq_comp.status == KPIStatus.FAIL:
            reason = FailureReason(
                category="Timing",
                subcategory="Frequency Target Miss",
                description=f"Failed to meet frequency target: {freq_comp.stage5_actual:.1f} MHz actual vs {freq_comp.stage1_budget:.1f} MHz budget",
                affected_kpis=["max_frequency_mhz", "critical_path_delay_ns"],
                suggested_fix="Consider adding pipeline stages or reducing combinational logic depth"
            )
            reasons.append(reason)

        # Area failures
        lut_comp = next((c for c in report.comparisons if c.kpi_name == "total_luts"), None)
        if lut_comp and lut_comp.status == KPIStatus.FAIL:
            reason = FailureReason(
                category="Area",
                subcategory="LUT Overutilization",
                description=f"Exceeded LUT budget: {lut_comp.stage5_actual} actual vs {lut_comp.stage1_budget} budget",
                affected_kpis=["total_luts"],
                suggested_fix="Consider resource sharing, BlockRAM instead of LUTRAM, or algorithmic optimizations"
            )
            reasons.append(reason)

        return reasons

    def _record_failures_to_experience_db(
        self,
        report: KPIComparisonReport,
        design_name: str,
        stage5_results: SynthesisKPIs
    ):
        """Record failures to Experience DB for future reference."""
        for reason in report.failure_reasons:
            failure = FailureCase(
                case_id=f"fail_{int(datetime.now().timestamp())}",
                module_name=design_name,
                target_frequency_mhz=stage5_results.max_frequency_mhz or 0.0,
                stage="5",
                failure_type=f"{reason.category}_{reason.subcategory}",
                error_message=reason.description,
                yosys_report=stage5_results.to_dict(),
                resolved=False,
                resolution_notes=reason.suggested_fix
            )
            self.experience_db.record_failure(failure)


class AutomaticFallbackExecutor:
    """
    Executes automatic fallback when KPI comparison fails.

    Records the fallback action and updates project state.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.veriflow_dir = project_root / ".veriflow"

    def execute_fallback(
        self,
        report: KPIComparisonReport,
        current_stage: int = 5
    ) -> bool:
        """
        Execute fallback to the determined target stage.

        Returns:
            True if fallback executed successfully
        """
        if not report.requires_fallback:
            return False

        target_stage_num = self._target_to_stage_number(report.fallback_target)

        # Record fallback action
        self._record_fallback_action(report, current_stage, target_stage_num)

        # Clear completion markers for stages after target
        self._clear_completion_markers(target_stage_num)

        return True

    def _target_to_stage_number(self, target: FallbackTarget) -> int:
        """Convert fallback target to stage number."""
        mapping = {
            FallbackTarget.STAGE_1_5: 1,
            FallbackTarget.STAGE_2: 2,
            FallbackTarget.STAGE_3: 3,
            FallbackTarget.NO_FALLBACK: 5,
        }
        return mapping.get(target, 1)

    def _record_fallback_action(
        self,
        report: KPIComparisonReport,
        from_stage: int,
        to_stage: int
    ):
        """Record the fallback action for audit."""
        fallback_dir = self.veriflow_dir / "fallbacks"
        fallback_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "report_id": report.report_id,
            "design_name": report.design_name,
            "timestamp": datetime.now().isoformat(),
            "from_stage": from_stage,
            "to_stage": to_stage,
            "fallback_target": report.fallback_target.value,
            "failure_reasons": [r.to_dict() for r in report.failure_reasons],
            "kpi_comparisons": [c.to_dict() for c in report.comparisons]
        }

        filename = f"fallback_{report.report_id}.json"
        with open(fallback_dir / filename, 'w') as f:
            json.dump(record, f, indent=2)

        # Also save the markdown report
        report.save(fallback_dir / f"{report.report_id}_kpi_report.json")
        (fallback_dir / f"{report.report_id}_kpi_report.md").write_text(report.to_markdown())

    def _clear_completion_markers(self, keep_up_to_stage: int):
        """Clear completion markers for stages after the target."""
        completed_dir = self.veriflow_dir / "stage_completed"
        if not completed_dir.exists():
            return

        for marker_file in completed_dir.glob("stage_*.complete"):
            try:
                # Extract stage number from filename
                match = re.search(r'stage_(\d+)', marker_file.name)
                if match:
                    stage_num = int(match.group(1))
                    if stage_num > keep_up_to_stage:
                        marker_file.unlink()
            except Exception:
                pass


import re  # for the fallback executor
