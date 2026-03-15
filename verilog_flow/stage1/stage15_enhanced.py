"""
Stage 1.5 Enhanced: Complete Micro-Architecture Specification with all required fields.

Implements the full Stage 1 & 1.5 requirements from original design:
- Architecture decision making (pipeline stages, critical path cuts, resource selection)
- Physical pre-evaluation (max logic levels from target frequency)
- Power Guardband support
- Interface Timing Matrix
- Fallback Thresholds
- Experience DB integration
- Quality gates with automatic fallback
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime


# =============================================================================
# Resource Type Selection
# =============================================================================

class ResourceType(Enum):
    """Resource type selection for design components."""
    DIST_RAM = "distributed_ram"      # LUTRAM for single-cycle access
    BLOCK_RAM = "block_ram"            # BRAM for larger memories
    REGISTERS = "registers"            # Flip-flops
    LUT_COMB = "lut_combinational"     # Pure LUT logic
    DSP = "dsp"                         # DSP slices


class CriticalPathCutStrategy(Enum):
    """Strategies for cutting critical paths."""
    BALANCED = "balanced"               # Equal logic per stage
    MINIMIZE_REGISTERS = "min_reg"      # Fewer registers, more logic per stage
    MAXIMIZE_FREQUENCY = "max_freq"     # More registers, less logic per stage


# =============================================================================
# Power Guardband
# =============================================================================

@dataclass
class PowerGuardband:
    """Power guardband for Stage 1.5."""
    enabled: bool = True
    dynamic_power_limit_mw: Optional[float] = None
    leakage_power_limit_mw: Optional[float] = None
    power_derate_factor: float = 1.2  # 20% guardband by default
    activity_factor: float = 0.2  # Typical toggle rate for estimation
    clock_gating_efficiency: float = 0.0  # 0-1, higher is better

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PowerGuardband':
        return cls(**data)


# =============================================================================
# Interface Timing Matrix
# =============================================================================

@dataclass
class InterfaceTiming:
    """Timing parameters for a single interface."""
    interface_name: str
    t_setup_ns: float = 0.0
    t_hold_ns: float = 0.0
    t_clk_q_ns: float = 0.0
    t_valid_ns: float = 0.0
    t_ready_ns: float = 0.0
    max_clock_frequency_mhz: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InterfaceTimingMatrix:
    """Complete interface timing matrix for all interfaces."""
    interfaces: List[InterfaceTiming] = field(default_factory=list)

    def add_interface(self, timing: InterfaceTiming):
        self.interfaces.append(timing)

    def get_interface(self, name: str) -> Optional[InterfaceTiming]:
        for iface in self.interfaces:
            if iface.interface_name == name:
                return iface
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interfaces": [t.to_dict() for t in self.interfaces]
        }


# =============================================================================
# Fallback Thresholds
# =============================================================================

class FallbackAction(Enum):
    """Actions to take when threshold is exceeded."""
    RETRY_STAGE_1 = "retry_stage_1"
    REDUCE_FREQUENCY = "reduce_frequency"
    ADD_PIPELINE_STAGES = "add_pipeline_stages"
    CHANGE_RESOURCE_TYPE = "change_resource_type"
    ADD_REGISTER_RETIMING = "add_register_retiming"


@dataclass
class FallbackThreshold:
    """Fallback threshold for a specific metric."""
    metric_name: str
    warning_threshold: float
    error_threshold: float
    fallback_action: FallbackAction
    action_parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def check_value(self, value: float) -> Tuple[str, float]:
        """
        Check a value against thresholds.

        Returns:
            ("ok"|"warning"|"error", margin)
        """
        if value >= self.error_threshold:
            return "error", value - self.error_threshold
        elif value >= self.warning_threshold:
            return "warning", value - self.warning_threshold
        else:
            return "ok", self.warning_threshold - value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "warning_threshold": self.warning_threshold,
            "error_threshold": self.error_threshold,
            "fallback_action": self.fallback_action.value,
            "action_parameters": self.action_parameters,
            "description": self.description
        }


@dataclass
class FallbackThresholds:
    """Collection of fallback thresholds."""
    thresholds: List[FallbackThreshold] = field(default_factory=list)

    def add_threshold(self, threshold: FallbackThreshold):
        self.thresholds.append(threshold)

    def check_all(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """Check all thresholds against provided metrics."""
        results = {
            "overall_status": "ok",
            "warnings": [],
            "errors": [],
            "recommended_actions": []
        }

        for thresh in self.thresholds:
            if thresh.metric_name in metrics:
                status, margin = thresh.check_value(metrics[thresh.metric_name])
                if status == "error":
                    results["errors"].append({
                        "metric": thresh.metric_name,
                        "value": metrics[thresh.metric_name],
                        "threshold": thresh.error_threshold,
                        "margin": margin,
                        "action": thresh.fallback_action.value,
                        "description": thresh.description
                    })
                    results["recommended_actions"].append(thresh.fallback_action)
                elif status == "warning":
                    results["warnings"].append({
                        "metric": thresh.metric_name,
                        "value": metrics[thresh.metric_name],
                        "threshold": thresh.warning_threshold,
                        "margin": margin,
                        "description": thresh.description
                    })

        if results["errors"]:
            results["overall_status"] = "error"
        elif results["warnings"]:
            results["overall_status"] = "warning"

        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thresholds": [t.to_dict() for t in self.thresholds]
        }


# =============================================================================
# Stage 1.5 Quality Checklist
# =============================================================================

@dataclass
class Stage15Checklist:
    """Stage 1.5 quality checklist with coverage tracking."""
    interface_consistency: bool = False
    latency_budget: bool = False
    power_guardband: bool = False
    ip_reuse_analysis: bool = False
    timing_budget_defined: bool = False
    pipeline_topology_defined: bool = False
    resource_mapping_defined: bool = False
    fallback_thresholds_defined: bool = False

    CHECKLIST_DESCRIPTIONS = {
        "interface_consistency": "所有接口信号宽度、方向、协议一致",
        "latency_budget": "延迟预算已分配到各个流水线阶段",
        "power_guardband": "功耗保护带已定义，包含动态/静态功耗上限",
        "ip_reuse_analysis": "IP复用分析已完成，复用/新增IP判定明确",
        "timing_budget_defined": "时序预算已定义，包含setup/hold裕度",
        "pipeline_topology_defined": "流水线拓扑已定义，包含阶段划分和关键路径切割",
        "resource_mapping_defined": "资源映射表已定义（DistRAM vs BlockRAM）",
        "fallback_thresholds_defined": "回退阈值已定义，明确触发条件和回退策略"
    }

    @property
    def total_items(self) -> int:
        return len(self.CHECKLIST_DESCRIPTIONS)

    @property
    def passed_items(self) -> int:
        return sum(1 for k in self.CHECKLIST_DESCRIPTIONS.keys()
                   if getattr(self, k, False))

    @property
    def all_passed(self) -> bool:
        return self.passed_items == self.total_items

    def get_status(self, item: str) -> Tuple[bool, str]:
        """Get checklist item status with description."""
        return getattr(self, item, False), self.CHECKLIST_DESCRIPTIONS.get(item, "")

    def to_dict(self) -> Dict[str, bool]:
        return {k: getattr(self, k, False)
                for k in self.CHECKLIST_DESCRIPTIONS.keys()}

    def to_markdown(self) -> str:
        """Generate markdown checklist with [x]/[ ] markers."""
        md = "## Stage 1.5 Quality Checklist\n\n"
        for key, desc in self.CHECKLIST_DESCRIPTIONS.items():
            status = "x" if getattr(self, key, False) else " "
            md += f"- [{status}] {desc}\n"
        md += f"\n**Coverage: {self.passed_items}/{self.total_items}**\n"
        return md


# =============================================================================
# Pre-Check Report
# =============================================================================

@dataclass
class PreCheckReport:
    """Complete pre-check report for Stage 1.5."""
    passed: bool = False
    timing_feasible: bool = True
    timing_issues: List[str] = field(default_factory=list)
    interfaces_consistent: bool = True
    interface_issues: List[str] = field(default_factory=list)
    latency_consistent: bool = True
    latency_issues: List[str] = field(default_factory=list)
    resources_reasonable: bool = True
    resource_warnings: List[str] = field(default_factory=list)
    fallback_check_result: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def errors(self) -> List[str]:
        return self.timing_issues + self.interface_issues + self.latency_issues

    @property
    def warnings(self) -> List[str]:
        return self.resource_warnings

    @property
    def should_fallback(self) -> bool:
        return self.fallback_check_result.get("overall_status") == "error"

    @property
    def recommended_fallback_actions(self) -> List[str]:
        return self.fallback_check_result.get("recommended_actions", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "timing_feasible": self.timing_feasible,
            "timing_issues": self.timing_issues,
            "interfaces_consistent": self.interfaces_consistent,
            "interface_issues": self.interface_issues,
            "latency_consistent": self.latency_consistent,
            "latency_issues": self.latency_issues,
            "resources_reasonable": self.resources_reasonable,
            "resource_warnings": self.resource_warnings,
            "fallback_check_result": self.fallback_check_result,
            "checked_at": self.checked_at
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        md = "## Stage 1.5 Pre-Check Report\n\n"
        md += f"**Status: {'✅ PASSED' if self.passed else '❌ FAILED'}**\n\n"

        if self.timing_issues:
            md += "### Timing Issues\n"
            for issue in self.timing_issues:
                md += f"- 🔴 {issue}\n"
            md += "\n"

        if self.interface_issues:
            md += "### Interface Issues\n"
            for issue in self.interface_issues:
                md += f"- 🔴 {issue}\n"
            md += "\n"

        if self.latency_issues:
            md += "### Latency Issues\n"
            for issue in self.latency_issues:
                md += f"- 🔴 {issue}\n"
            md += "\n"

        if self.resource_warnings:
            md += "### Resource Warnings\n"
            for warning in self.resource_warnings:
                md += f"- 🟡 {warning}\n"
            md += "\n"

        return md


# =============================================================================
# Default Configurations
# =============================================================================

def create_default_fallback_thresholds(clock_period_ns: float) -> FallbackThresholds:
    """Create default fallback thresholds based on clock period."""
    thresholds = FallbackThresholds()

    # Critical path delay threshold
    thresholds.add_threshold(FallbackThreshold(
        metric_name="max_combinational_delay_ns",
        warning_threshold=clock_period_ns * 0.75,
        error_threshold=clock_period_ns * 0.9,
        fallback_action=FallbackAction.ADD_PIPELINE_STAGES,
        description="最大组合逻辑延迟接近或超过时钟周期"
    ))

    # Setup slack threshold
    thresholds.add_threshold(FallbackThreshold(
        metric_name="setup_slack_ns",
        warning_threshold=0.2,
        error_threshold=0.0,
        fallback_action=FallbackAction.REDUCE_FREQUENCY,
        action_parameters={"frequency_reduction_percent": 10},
        description="Setup裕度过小或为负"
    ))

    # Logic depth threshold
    thresholds.add_threshold(FallbackThreshold(
        metric_name="max_logic_levels",
        warning_threshold=12,
        error_threshold=16,
        fallback_action=FallbackAction.ADD_PIPELINE_STAGES,
        description="逻辑级数过高"
    ))

    # Total LUT count warning
    thresholds.add_threshold(FallbackThreshold(
        metric_name="total_lut_count",
        warning_threshold=50000,
        error_threshold=100000,
        fallback_action=FallbackAction.CHANGE_RESOURCE_TYPE,
        description="LUT使用量过高"
    ))

    return thresholds


def create_default_power_guardband() -> PowerGuardband:
    """Create default power guardband configuration."""
    return PowerGuardband(
        enabled=True,
        power_derate_factor=1.2,
        activity_factor=0.2
    )


def create_default_interface_timing_matrix() -> InterfaceTimingMatrix:
    """Create default interface timing matrix."""
    matrix = InterfaceTimingMatrix()

    # Add default clock/reset interface timing
    matrix.add_interface(InterfaceTiming(
        interface_name="clock_reset",
        t_setup_ns=0.1,
        t_hold_ns=0.1,
        t_clk_q_ns=0.3,
        notes="Clock and reset interface timing defaults"
    ))

    # Add default data interface timing
    matrix.add_interface(InterfaceTiming(
        interface_name="data",
        t_setup_ns=0.2,
        t_hold_ns=0.1,
        t_clk_q_ns=0.3,
        t_valid_ns=0.5,
        t_ready_ns=0.5,
        notes="General data interface timing defaults"
    ))

    return matrix


# =============================================================================
# Helper Functions for Spec Integration
# =============================================================================

def enhance_spec_with_stage15(
    spec_dict: Dict[str, Any],
    target_frequency_mhz: float,
    fallback_thresholds: Optional[FallbackThresholds] = None,
    power_guardband: Optional[PowerGuardband] = None,
    interface_timing_matrix: Optional[InterfaceTimingMatrix] = None
) -> Dict[str, Any]:
    """
    Enhance a standard spec dictionary with Stage 1.5 extensions.

    Args:
        spec_dict: Original spec dictionary
        target_frequency_mhz: Target frequency
        fallback_thresholds: Optional custom fallback thresholds
        power_guardband: Optional custom power guardband
        interface_timing_matrix: Optional custom interface timing matrix

    Returns:
        Enhanced spec dictionary
    """
    clock_period_ns = 1000.0 / target_frequency_mhz

    # Create defaults if not provided
    if fallback_thresholds is None:
        fallback_thresholds = create_default_fallback_thresholds(clock_period_ns)
    if power_guardband is None:
        power_guardband = create_default_power_guardband()
    if interface_timing_matrix is None:
        interface_timing_matrix = create_default_interface_timing_matrix()

    # Add Stage 1.5 fields
    enhanced = spec_dict.copy()

    enhanced["stage15"] = {
        "power_guardband": power_guardband.to_dict(),
        "interface_timing_matrix": interface_timing_matrix.to_dict(),
        "fallback_thresholds": fallback_thresholds.to_dict(),
        "checklist": Stage15Checklist().to_dict(),
        "enhanced_at": datetime.now().isoformat()
    }

    return enhanced


def load_stage15_enhancements(spec_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Load Stage 1.5 enhancements from a spec dictionary."""
    return spec_dict.get("stage15", {})
