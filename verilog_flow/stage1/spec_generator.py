"""Stage 1 & 1.5: Generate Micro-Architecture Specification."""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class PipelineStage:
    """Definition of a pipeline stage."""
    name: str
    stage_number: int
    logic_depth_estimate: int  # Estimated logic levels
    latency_cycles: int = 1
    registers: List[str] = field(default_factory=list)


@dataclass
class ResourceMapping:
    """Resource allocation for the design."""
    bram_count: int = 0
    dsp_count: int = 0
    lut_estimate: int = 0
    ff_estimate: int = 0
    io_count: int = 0


@dataclass
class InterfaceSpec:
    """Interface specification for the module."""
    name: str
    protocol: str  # e.g., "AXI4-Lite", "AXI4", "Custom"
    direction: str  # "master", "slave", "bidirectional"
    data_width: int
    addr_width: int
    timing: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimingBudget:
    """Timing constraints and budgets."""
    target_frequency_mhz: float
    clock_period_ns: float = field(init=False)
    max_logic_levels: int = 0
    setup_slack_ns: float = 0.0
    hold_slack_ns: float = 0.0

    def __post_init__(self):
        self.clock_period_ns = 1000.0 / self.target_frequency_mhz


@dataclass
class MicroArchSpec:
    """Complete Micro-Architecture Specification (Stage 1.5 output)."""
    # Identification
    module_name: str
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())

    # Requirements
    requirements: Dict[str, Any] = field(default_factory=dict)

    # Architecture decisions
    pipeline_stages: List[PipelineStage] = field(default_factory=list)
    resource_mapping: ResourceMapping = field(default_factory=ResourceMapping)
    interfaces: List[InterfaceSpec] = field(default_factory=list)

    # Timing
    timing_budget: Optional[TimingBudget] = None

    # Control/Data paths
    control_path_description: str = ""
    data_path_description: str = ""

    # Pipeline topology (for visualization)
    pipeline_topology: Dict[str, Any] = field(default_factory=dict)

    # Quality gates
    quality_checklist: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, output_dir: Path) -> Path:
        """Save specification to file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{self.module_name}_spec.json"
        with open(output_file, 'w') as f:
            f.write(self.to_json())

        return output_file

    @classmethod
    def from_dict(cls, data: Dict) -> "MicroArchSpec":
        """Create from dictionary."""
        # Handle nested dataclasses
        if "pipeline_stages" in data:
            data["pipeline_stages"] = [PipelineStage(**s) for s in data["pipeline_stages"]]
        if "resource_mapping" in data:
            data["resource_mapping"] = ResourceMapping(**data["resource_mapping"])
        if "interfaces" in data:
            data["interfaces"] = [InterfaceSpec(**i) for i in data["interfaces"]]
        if "timing_budget" in data and data["timing_budget"]:
            data["timing_budget"] = TimingBudget(**data["timing_budget"])

        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "MicroArchSpec":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, file_path: Path) -> "MicroArchSpec":
        """Load from file."""
        with open(file_path, 'r') as f:
            return cls.from_json(f.read())


class SpecGenerator:
    """Generate Micro-Architecture Specifications."""

    def __init__(self):
        self.spec: Optional[MicroArchSpec] = None

    def create_from_requirements(self,
                                  module_name: str,
                                  requirements: Dict[str, Any]) -> MicroArchSpec:
        """Create a new spec from requirements."""
        self.spec = MicroArchSpec(
            module_name=module_name,
            requirements=requirements
        )

        # Extract key requirements
        target_freq = requirements.get("target_frequency_mhz", 100.0)
        self.spec.timing_budget = TimingBudget(
            target_frequency_mhz=target_freq,
            max_logic_levels=requirements.get("max_logic_levels", 10)
        )

        # Initialize quality checklist
        self.spec.quality_checklist = {
            "interface_consistency": False,
            "latency_budget": False,
            "power_guardband": False,
            "ip_reuse_analysis": False,
            "timing_budget_defined": False,
            "pipeline_topology_defined": False
        }

        return self.spec

    def add_pipeline_stage(self,
                           name: str,
                           stage_number: int,
                           logic_depth_estimate: int,
                           latency_cycles: int = 1):
        """Add a pipeline stage to the spec."""
        if not self.spec:
            raise RuntimeError("No spec created. Call create_from_requirements() first.")

        stage = PipelineStage(
            name=name,
            stage_number=stage_number,
            logic_depth_estimate=logic_depth_estimate,
            latency_cycles=latency_cycles
        )
        self.spec.pipeline_stages.append(stage)

    def add_interface(self,
                      name: str,
                      protocol: str,
                      direction: str,
                      data_width: int,
                      addr_width: int = 0):
        """Add an interface specification."""
        if not self.spec:
            raise RuntimeError("No spec created. Call create_from_requirements() first.")

        interface = InterfaceSpec(
            name=name,
            protocol=protocol,
            direction=direction,
            data_width=data_width,
            addr_width=addr_width
        )
        self.spec.interfaces.append(interface)

    def update_quality_checklist(self, item: str, passed: bool = True):
        """Update a quality checklist item."""
        if not self.spec:
            raise RuntimeError("No spec created.")

        if item in self.spec.quality_checklist:
            self.spec.quality_checklist[item] = passed

    def check_quality_gates(self) -> Dict[str, Any]:
        """Check if all quality gates pass."""
        if not self.spec:
            raise RuntimeError("No spec created.")

        passed = all(self.spec.quality_checklist.values())
        failed_items = [k for k, v in self.spec.quality_checklist.items() if not v]

        return {
            "passed": passed,
            "failed_items": failed_items,
            "total_checks": len(self.spec.quality_checklist),
            "passed_checks": len(self.spec.quality_checklist) - len(failed_items)
        }