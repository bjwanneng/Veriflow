"""Stage 1 & 1.5: Micro-architecture specification and decision making."""

from .spec_generator import SpecGenerator
from .architect import MicroArchitect
from .arch_prompts import ARCH_PROMPTS, get_prompt_for_step
from .arch_decomposer import ArchDecomposer, ValidationResult

__all__ = [
    "SpecGenerator",
    "MicroArchitect",
    "ARCH_PROMPTS",
    "get_prompt_for_step",
    "ArchDecomposer",
    "ValidationResult"
]