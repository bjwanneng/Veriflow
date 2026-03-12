"""
VeriFlow-Agent 3.0: Industrial-grade Verilog code generation system
with timing and micro-architecture awareness.
"""

__version__ = "3.0.0"
__author__ = "VeriFlow Team"

# Common utilities
from .common.kpi import KPITracker
from .common.experience_db import ExperienceDB
from .common.project_layout import ProjectLayout
from .common.coding_style import CodingStyle, CodingStyleManager
from .common.stage_gate import StageGateChecker
from .common.execution_log import ExecutionLogger
from .common.post_run_analyzer import PostRunAnalyzer

# Stage 1: Micro-architecture specification
from .stage1.spec_generator import (
    MicroArchSpec,
    SpecGenerator,
    PipelineStage,
    InterfaceSpec,
    TimingBudget,
)

# Stage 2: Virtual timing modeling
from .stage2 import (
    TimingScenario,
    Phase,
    SignalTransition,
    Assertion,
    parse_yaml_scenario,
    generate_wavedrom,
    generate_golden_trace,
    validate_scenario,
)

# Stage 3: Code generation
from .stage3 import (
    RTLCodeGenerator,
    GeneratedModule,
    LintChecker,
    LintResult,
)

# Stage 4: Simulation
from .stage4 import (
    TestbenchGenerator,
    TestbenchConfig,
    SimulationRunner,
    WaveformDiffAnalyzer,
)

# Stage 5: Synthesis
from .stage5 import (
    SynthesisRunner,
    TimingAnalyzer,
    AreaEstimator,
)

__all__ = [
    # Version
    "__version__",
    # Common
    "KPITracker",
    "ExperienceDB",
    "ProjectLayout",
    "CodingStyle",
    "CodingStyleManager",
    "StageGateChecker",
    "ExecutionLogger",
    "PostRunAnalyzer",
    # Stage 1
    "MicroArchSpec",
    "SpecGenerator",
    "PipelineStage",
    "InterfaceSpec",
    "TimingBudget",
    # Stage 2
    "TimingScenario",
    "Phase",
    "SignalTransition",
    "Assertion",
    "parse_yaml_scenario",
    "generate_wavedrom",
    "generate_golden_trace",
    "validate_scenario",
    # Stage 3
    "RTLCodeGenerator",
    "GeneratedModule",
    "LintChecker",
    "LintResult",
    # Stage 4
    "TestbenchGenerator",
    "TestbenchConfig",
    "SimulationRunner",
    "WaveformDiffAnalyzer",
    # Stage 5
    "SynthesisRunner",
    "TimingAnalyzer",
    "AreaEstimator",
]