"""Stage 1 & 1.5: Micro-architecture specification and decision making."""

from .spec_generator import SpecGenerator, MicroArchSpec, PipelineStage, InterfaceSpec, TimingBudget
from .architect import MicroArchitect
from .arch_prompts import ARCH_PROMPTS, get_prompt_for_step
from .arch_decomposer import ArchDecomposer, ValidationResult
from .stage15_enhanced import (
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

__all__ = [
    # Original
    "SpecGenerator",
    "MicroArchSpec",
    "PipelineStage",
    "InterfaceSpec",
    "TimingBudget",
    "MicroArchitect",
    "ARCH_PROMPTS",
    "get_prompt_for_step",
    "ArchDecomposer",
    "ValidationResult",
    # Stage 1.5 Enhanced
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
]