"""Stage 2: Virtual timing modeling with YAML DSL."""

from .yaml_dsl import (
    TimingScenario,
    Phase,
    SignalTransition,
    Assertion,
    TransitionType,
    AssertionType,
    parse_yaml_scenario,
)
from .wavedrom_gen import generate_wavedrom, generate_wavedrom_json, generate_wavedrom_svg
from .golden_trace import (
    GoldenTrace,
    TraceEvent,
    TraceValueType,
    generate_golden_trace,
)
from .validator import validate_scenario, ValidationResult, load_schema

__all__ = [
    # YAML DSL
    "TimingScenario",
    "Phase",
    "SignalTransition",
    "Assertion",
    "TransitionType",
    "AssertionType",
    "parse_yaml_scenario",
    # WaveDrom
    "generate_wavedrom",
    "generate_wavedrom_json",
    "generate_wavedrom_svg",
    # Golden Trace
    "GoldenTrace",
    "TraceEvent",
    "TraceValueType",
    "generate_golden_trace",
    # Validator
    "validate_scenario",
    "ValidationResult",
    "load_schema",
]