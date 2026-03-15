"""Stage 4: Physical Simulation & Verification."""

from .testbench import TestbenchGenerator, TestbenchConfig
from .sim_runner import SimulationRunner, SimulationResult
from .waveform_diff import WaveformDiffAnalyzer, DiffResult
from .assertion_checker import AssertionChecker, AssertionResult
from .waveform_diff_enhanced import (
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

__all__ = [
    "TestbenchGenerator",
    "TestbenchConfig",
    "SimulationRunner",
    "SimulationResult",
    "WaveformDiffAnalyzer",
    "DiffResult",
    "AssertionChecker",
    "AssertionResult",
    # Stage 4 Enhanced
    "EnhancedWaveformDiffAnalyzer",
    "EnhancedDiffResult",
    "EnhancedDiffEvent",
    "DiagnosticAnalyzer",
    "ProgressiveCoverageManager",
    "CoverageLayer",
    "DiffSuggestion",
    "DiffSeverity",
    "ProbableCause",
]
