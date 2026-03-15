"""Stage 5: Synthesis-Level Verification."""

from .synthesis_runner import SynthesisRunner, SynthesisResult
from .timing_analyzer import TimingAnalyzer, TimingResult
from .area_estimator import AreaEstimator, AreaResult
from .yosys_interface import YosysInterface
from .precheck import check_synthesizability, PrecheckResult
from .kpi_comparator import (
    KPIComparator,
    KPIComparisonReport,
    KPIComparison,
    SynthesisKPIs,
    FailureReason,
    AutomaticFallbackExecutor,
    KPIStatus,
    FallbackTarget,
)

__all__ = [
    "SynthesisRunner",
    "SynthesisResult",
    "TimingAnalyzer",
    "TimingResult",
    "AreaEstimator",
    "AreaResult",
    "YosysInterface",
    "check_synthesizability",
    "PrecheckResult",
    # Stage 5 Enhanced
    "KPIComparator",
    "KPIComparisonReport",
    "KPIComparison",
    "SynthesisKPIs",
    "FailureReason",
    "AutomaticFallbackExecutor",
    "KPIStatus",
    "FallbackTarget",
]
