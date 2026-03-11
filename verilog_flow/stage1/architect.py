"""Micro-Architect for automated architecture decisions (Stage 1.5)."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .spec_generator import MicroArchSpec, SpecGenerator, TimingBudget, PipelineStage


@dataclass
class ArchitectureDecision:
    """A single architecture decision."""
    decision_type: str
    description: str
    rationale: str
    impact: str  # performance, area, power
    confidence: float = 1.0  # 0.0 to 1.0


class MicroArchitect:
    """Automated micro-architecture decision making."""

    def __init__(self):
        self.decisions: List[ArchitectureDecision] = []

    def design_from_requirements(
        self,
        module_name: str,
        requirements: Dict[str, Any]
    ) -> MicroArchSpec:
        """Generate complete micro-architecture from requirements."""

        generator = SpecGenerator()
        spec = generator.create_from_requirements(module_name, requirements)

        # Analyze requirements and make decisions
        self._decide_pipeline_structure(spec, requirements)
        self._decide_interfaces(spec, requirements)
        self._decide_timing_budget(spec, requirements)
        self._decide_resource_allocation(spec, requirements)

        return spec

    def _decide_pipeline_structure(
        self,
        spec: MicroArchSpec,
        requirements: Dict[str, Any]
    ):
        """Decide on pipeline structure."""

        target_freq = requirements.get("target_frequency_mhz", 100.0)
        latency_requirement = requirements.get("max_latency_cycles")
        throughput_requirement = requirements.get("throughput", "medium")

        # Simple heuristic: higher frequency = more pipeline stages
        if target_freq >= 500:
            suggested_stages = 5
        elif target_freq >= 300:
            suggested_stages = 4
        elif target_freq >= 200:
            suggested_stages = 3
        elif target_freq >= 100:
            suggested_stages = 2
        else:
            suggested_stages = 1

        # Adjust for latency constraint
        if latency_requirement and suggested_stages > latency_requirement:
            suggested_stages = max(1, latency_requirement)

        # Create pipeline stages
        for i in range(suggested_stages):
            stage = PipelineStage(
                name=f"stage_{i}",
                stage_number=i,
                logic_depth_estimate=5,  # Estimate 5 logic levels per stage
                latency_cycles=1,
                registers=[]
            )
            spec.pipeline_stages.append(stage)

        self.decisions.append(ArchitectureDecision(
            decision_type="pipeline_structure",
            description=f"{suggested_stages}-stage pipeline",
            rationale=f"Based on target frequency of {target_freq} MHz",
            impact="performance",
            confidence=0.8
        ))

    def _decide_interfaces(
        self,
        spec: MicroArchSpec,
        requirements: Dict[str, Any]
    ):
        """Decide on interface specifications."""

        interface_type = requirements.get("interface_type", "custom")
        data_width = requirements.get("data_width", 32)

        if interface_type == "axi4-lite":
            from .spec_generator import InterfaceSpec
            # Add AXI4-Lite interface
            spec.interfaces.append(InterfaceSpec(
                name="s_axi",
                protocol="AXI4-Lite",
                direction="slave",
                data_width=data_width,
                addr_width=requirements.get("addr_width", 32)
            ))

            self.decisions.append(ArchitectureDecision(
                decision_type="interface",
                description="AXI4-Lite slave interface",
                rationale="Standard protocol for register access",
                impact="area",
                confidence=0.9
            ))

    def _decide_timing_budget(
        self,
        spec: MicroArchSpec,
        requirements: Dict[str, Any]
    ):
        """Decide on timing budget allocation."""

        target_freq = requirements.get("target_frequency_mhz", 100.0)

        if spec.timing_budget:
            # Add margin for PVT variations
            spec.timing_budget.setup_slack_ns = 0.5  # 500ps setup margin
            spec.timing_budget.hold_slack_ns = 0.1   # 100ps hold margin

            self.decisions.append(ArchitectureDecision(
                decision_type="timing_budget",
                description=f"Clock period: {spec.timing_budget.clock_period_ns:.2f}ns",
                rationale=f"Target: {target_freq} MHz with 10% margin",
                impact="performance",
                confidence=0.85
            ))

    def _decide_resource_allocation(
        self,
        spec: MicroArchSpec,
        requirements: Dict[str, Any]
    ):
        """Decide on resource allocation."""

        # Estimate resources based on features
        from .spec_generator import ResourceMapping

        mapping = ResourceMapping()

        # Estimate LUTs based on pipeline stages and data width
        data_width = requirements.get("data_width", 32)
        num_stages = len(spec.pipeline_stages)

        mapping.lut_estimate = data_width * num_stages * 2  # Rough estimate
        mapping.ff_estimate = data_width * num_stages  # One register per bit per stage

        # Check for memory requirements
        if "fifo_depth" in requirements:
            mapping.bram_count = 1  # Assume one BRAM for FIFO

        spec.resource_mapping = mapping

        self.decisions.append(ArchitectureDecision(
            decision_type="resources",
            description=f"~{mapping.lut_estimate} LUTs, ~{mapping.ff_estimate} FFs",
            rationale="Estimated from pipeline structure",
            impact="area",
            confidence=0.6
        ))

    def get_decisions(self) -> List[ArchitectureDecision]:
        """Get all architecture decisions made."""
        return self.decisions

    def explain_design(self, spec: MicroArchSpec) -> str:
        """Generate a human-readable explanation of the design."""

        lines = []
        lines.append(f"Micro-Architecture Design: {spec.module_name}")
        lines.append("=" * 60)
        lines.append("")

        lines.append(f"Pipeline: {len(spec.pipeline_stages)} stages")
        for stage in spec.pipeline_stages:
            lines.append(f"  - {stage.name}: {stage.logic_depth_estimate} logic levels")
        lines.append("")

        if spec.timing_budget:
            lines.append(f"Timing Budget:")
            lines.append(f"  - Target: {spec.timing_budget.target_frequency_mhz:.2f} MHz")
            lines.append(f"  - Period: {spec.timing_budget.clock_period_ns:.2f} ns")
            lines.append("")

        lines.append(f"Resource Estimate:")
        lines.append(f"  - LUTs: ~{spec.resource_mapping.lut_estimate}")
        lines.append(f"  - FFs: ~{spec.resource_mapping.ff_estimate}")
        lines.append(f"  - BRAMs: {spec.resource_mapping.bram_count}")
        lines.append("")

        lines.append("Architecture Decisions:")
        for i, decision in enumerate(self.decisions, 1):
            lines.append(f"  {i}. {decision.decision_type}: {decision.description}")
            lines.append(f"     Rationale: {decision.rationale}")

        return "\n".join(lines)
