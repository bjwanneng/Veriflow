"""
VeriFlow-Agent 5.0: Industrial-grade Verilog code generation system
with timing and micro-architecture awareness.

Enhancements from original design requirements:
- Stage 1.5: Power Guardband, Interface Timing Matrix, Fallback Thresholds
- Stage 2: Assertion physical meaning explanation, Stimulus export
- Stage 3.5: Three-paradigm enforcement, Skill D calibration mechanism
- Stage 4: Diagnostic enhancement, Assertion ID mapping, Progressive coverage
- Stage 5: KPI automatic comparison, Fallback to Stage 1.5, Experience DB recording
"""

__version__ = "5.0.0"
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
from .stage1 import (
    PowerGuardband,
    InterfaceTimingMatrix,
    InterfaceTiming,
    FallbackThresholds,
    FallbackThreshold,
    FallbackAction,
    Stage15Checklist,
    PreCheckReport,
    ArchitectureDecisionEngine,
    Stage15PreChecker,
    ResourceType,
    CriticalPathCutStrategy,
    create_default_fallback_thresholds,
    create_default_power_guardband,
    create_default_interface_timing_matrix,
    enhance_spec_with_stage15,
    load_stage15_enhancements,
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
from .stage2 import (
    AssertionExplainer,
    AssertionExplanation,
    ViolationScenario,
    ViolationSeverity,
    StimulusExporter,
    StimulusTransaction,
    StimulusConfig,
    Stage2SchemaValidator,
)

# Stage 3: Code generation
from .stage3 import (
    RTLCodeGenerator,
    GeneratedModule,
    LintChecker,
    LintResult,
)
from .stage3 import (
    analyze_logic_depth,
    analyze_cdc,
    SkillDEnhanced,
    ThreeParadigmChecker,
    LogicDepthEstimate,
    CDCCrossingEnhanced,
    ErrorModelPoint,
    CalibratedErrorModel,
    LogicDepthCategory,
)

# Stage 4: Simulation
from .stage4 import (
    TestbenchGenerator,
    TestbenchConfig,
    SimulationRunner,
    WaveformDiffAnalyzer,
    DiffResult,
    AssertionChecker,
    AssertionResult,
)
from .stage4 import (
    EnhancedWaveformDiffAnalyzer,
    EnhancedDiffResult,
    EnhancedDiffEvent,
    DiagnosticAnalyzer,
    ProgressiveCoverageManager,
    CoverageLayer,
    DiffSuggestion,
    DiffSeverity,
    ProbableCause,
)

# Stage 5: Synthesis
from .stage5 import (
    SynthesisRunner,
    TimingAnalyzer,
    AreaEstimator,
    YosysInterface,
    check_synthesizability,
    PrecheckResult,
)
from .stage5 import (
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
    # Stage 1 (Base)
    "MicroArchSpec",
    "SpecGenerator",
    "PipelineStage",
    "InterfaceSpec",
    "TimingBudget",
    # Stage 1.5 (Enhanced)
    "PowerGuardband",
    "InterfaceTimingMatrix",
    "InterfaceTiming",
    "FallbackThresholds",
    "FallbackThreshold",
    "FallbackAction",
    "Stage15Checklist",
    "PreCheckReport",
    "ArchitectureDecisionEngine",
    "Stage15PreChecker",
    "ResourceType",
    "CriticalPathCutStrategy",
    "create_default_fallback_thresholds",
    "create_default_power_guardband",
    "create_default_interface_timing_matrix",
    "enhance_spec_with_stage15",
    "load_stage15_enhancements",
    # Stage 2 (Base)
    "TimingScenario",
    "Phase",
    "SignalTransition",
    "Assertion",
    "parse_yaml_scenario",
    "generate_wavedrom",
    "generate_golden_trace",
    "validate_scenario",
    # Stage 2 (Enhanced)
    "AssertionExplainer",
    "AssertionExplanation",
    "ViolationScenario",
    "ViolationSeverity",
    "StimulusExporter",
    "StimulusTransaction",
    "StimulusConfig",
    "Stage2SchemaValidator",
    # Stage 3 (Base)
    "RTLCodeGenerator",
    "GeneratedModule",
    "LintChecker",
    "LintResult",
    "analyze_logic_depth",
    "analyze_cdc",
    # Stage 3.5 (Enhanced)
    "SkillDEnhanced",
    "ThreeParadigmChecker",
    "LogicDepthEstimate",
    "CDCCrossingEnhanced",
    "ErrorModelPoint",
    "CalibratedErrorModel",
    "LogicDepthCategory",
    # Stage 4 (Base)
    "TestbenchGenerator",
    "TestbenchConfig",
    "SimulationRunner",
    "WaveformDiffAnalyzer",
    "DiffResult",
    "AssertionChecker",
    "AssertionResult",
    # Stage 4 (Enhanced)
    "EnhancedWaveformDiffAnalyzer",
    "EnhancedDiffResult",
    "EnhancedDiffEvent",
    "DiagnosticAnalyzer",
    "ProgressiveCoverageManager",
    "CoverageLayer",
    "DiffSuggestion",
    "DiffSeverity",
    "ProbableCause",
    # Stage 5 (Base)
    "SynthesisRunner",
    "TimingAnalyzer",
    "AreaEstimator",
    "YosysInterface",
    "check_synthesizability",
    "PrecheckResult",
    # Stage 5 (Enhanced)
    "KPIComparator",
    "KPIComparisonReport",
    "KPIComparison",
    "SynthesisKPIs",
    "FailureReason",
    "AutomaticFallbackExecutor",
    "KPIStatus",
    "FallbackTarget",
]