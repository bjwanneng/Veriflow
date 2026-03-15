"""Stage 3: RTL Code Generation and Static Analysis."""

from .code_generator import RTLCodeGenerator, GeneratedModule
from .lint_checker import LintChecker, LintResult
from .template_engine import TemplateEngine
from .skill_d import analyze_logic_depth, analyze_cdc
from .skill_d_enhanced import (
    SkillDEnhanced,
    ThreeParadigmChecker,
    LogicDepthEstimate,
    CDCCrossingEnhanced,
    ErrorModelPoint,
    CalibratedErrorModel,
    LogicDepthCategory,
)

__all__ = [
    "RTLCodeGenerator",
    "GeneratedModule",
    "LintChecker",
    "LintResult",
    "TemplateEngine",
    "analyze_logic_depth",
    "analyze_cdc",
    # Stage 3.5 Enhanced
    "SkillDEnhanced",
    "ThreeParadigmChecker",
    "LogicDepthEstimate",
    "CDCCrossingEnhanced",
    "ErrorModelPoint",
    "CalibratedErrorModel",
    "LogicDepthCategory",
]
