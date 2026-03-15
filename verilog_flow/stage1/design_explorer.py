"""Design space explorer — multi-alternative architecture generation.

Generates 2-3 architecture alternatives at the spec level with:
- Trade-off matrix (area / speed / power / complexity)
- Concrete option-based clarification (not open-ended questions)
- User preference tracking for future recommendations

v5.0: New module for design exploration at Stage 1.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DesignAlternative:
    """A single design alternative with trade-off metrics."""
    name: str
    description: str
    trade_offs: Dict[str, str]  # metric_name -> qualitative rating
    estimated_resources: Dict[str, int]  # lut/ff/bram/dsp counts
    latency_cycles: int = 0
    throughput: str = ""
    complexity: str = "medium"  # low | medium | high
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    spec_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignChoice:
    """A design decision point with concrete options."""
    question: str
    context: str
    options: List[DesignAlternative] = field(default_factory=list)
    recommendation_idx: int = 0  # index of recommended option
    impact_summary: str = ""


@dataclass
class TradeOffMatrix:
    """Comparison matrix for multiple design alternatives."""
    metrics: List[str]  # column headers
    alternatives: List[DesignAlternative]

    def to_markdown(self) -> str:
        """Render as a markdown table."""
        if not self.alternatives:
            return "No alternatives to compare."

        # Header
        header = "| Alternative | " + " | ".join(self.metrics) + " |"
        sep = "|" + "|".join(["---"] * (len(self.metrics) + 1)) + "|"

        rows = [header, sep]
        for alt in self.alternatives:
            values = [alt.trade_offs.get(m, "?") for m in self.metrics]
            row = f"| {alt.name} | " + " | ".join(values) + " |"
            rows.append(row)

        return "\n".join(rows)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics,
            "alternatives": [
                {
                    "name": a.name,
                    "description": a.description,
                    "trade_offs": a.trade_offs,
                    "estimated_resources": a.estimated_resources,
                    "latency_cycles": a.latency_cycles,
                    "throughput": a.throughput,
                    "pros": a.pros,
                    "cons": a.cons,
                }
                for a in self.alternatives
            ],
        }


class DesignSpaceExplorer:
    """Explore design alternatives and present trade-offs.

    Usage in SKILL.md Stage 1:
        explorer = DesignSpaceExplorer()
        choices = explorer.analyze_design_space(requirement, spec_data)
        # Present choices to user via AskUserQuestion
        # Apply selected alternative's spec_overrides
    """

    # Known design patterns with trade-off profiles
    SBOX_ALTERNATIVES = [
        DesignAlternative(
            name="Combinational LUT S-Box",
            description="Pure combinational logic lookup table, zero latency",
            trade_offs={
                "Area": "High (~1024 LUTs/16 instances)",
                "Speed": "Fast (0 extra cycles)",
                "Power": "High (large fanout)",
                "Flexibility": "Low (hardcoded)",
            },
            estimated_resources={"lut": 1024, "ff": 0, "bram": 0, "dsp": 0},
            latency_cycles=0,
            complexity="low",
            pros=["Zero additional latency", "Simple implementation"],
            cons=["Large area", "Not configurable at runtime"],
            spec_overrides={"sbox_type": "combinational"},
        ),
        DesignAlternative(
            name="Distributed RAM (LUTRAM) S-Box",
            description="FPGA LUTRAM-based, 1-cycle read latency, runtime configurable",
            trade_offs={
                "Area": "Medium (~256 LUTs/16 instances)",
                "Speed": "Good (+1 cycle latency)",
                "Power": "Medium",
                "Flexibility": "High (runtime configurable)",
            },
            estimated_resources={"lut": 256, "ff": 0, "bram": 0, "dsp": 0},
            latency_cycles=1,
            complexity="medium",
            pros=["Runtime configurable", "Moderate area", "Single-cycle read"],
            cons=["Adds 1 cycle to pipeline latency"],
            spec_overrides={"sbox_type": "lutram"},
        ),
        DesignAlternative(
            name="Block RAM S-Box",
            description="FPGA BRAM-based, 2-cycle read latency, most area efficient",
            trade_offs={
                "Area": "Low (16 BRAMs)",
                "Speed": "Slower (+2 cycles latency)",
                "Power": "Low",
                "Flexibility": "High (runtime configurable)",
            },
            estimated_resources={"lut": 0, "ff": 0, "bram": 16, "dsp": 0},
            latency_cycles=2,
            complexity="medium",
            pros=["Smallest LUT footprint", "Runtime configurable"],
            cons=["Adds 2 cycles to pipeline latency", "BRAM port contention possible"],
            spec_overrides={"sbox_type": "bram"},
        ),
    ]

    PIPELINE_ALTERNATIVES = [
        DesignAlternative(
            name="Full Unrolled Pipeline",
            description="All rounds physically instantiated, max throughput",
            trade_offs={
                "Area": "High (10x round logic)",
                "Throughput": "128 bits/cycle",
                "Latency": "10-13 cycles",
                "Complexity": "Medium",
            },
            estimated_resources={"lut": 15000, "ff": 5000, "bram": 0, "dsp": 0},
            latency_cycles=10,
            throughput="128 bits/cycle",
            complexity="medium",
            pros=["Maximum throughput", "Deterministic latency"],
            cons=["Large area", "High power"],
            spec_overrides={"pipeline_type": "full_unrolled"},
        ),
        DesignAlternative(
            name="Iterative (Single Round + FSM)",
            description="One round unit reused 10 times via FSM control",
            trade_offs={
                "Area": "Low (1x round logic)",
                "Throughput": "128 bits/10 cycles",
                "Latency": "10 cycles",
                "Complexity": "Low",
            },
            estimated_resources={"lut": 2000, "ff": 500, "bram": 0, "dsp": 0},
            latency_cycles=10,
            throughput="12.8 bits/cycle",
            complexity="low",
            pros=["Smallest area", "Simple design"],
            cons=["Low throughput", "Cannot pipeline multiple blocks"],
            spec_overrides={"pipeline_type": "iterative"},
        ),
        DesignAlternative(
            name="Partial Pipeline (2-stage)",
            description="5 rounds per stage, 2 physical stages",
            trade_offs={
                "Area": "Medium (2x round logic)",
                "Throughput": "128 bits/2 cycles",
                "Latency": "10 cycles",
                "Complexity": "Medium",
            },
            estimated_resources={"lut": 4000, "ff": 1500, "bram": 0, "dsp": 0},
            latency_cycles=10,
            throughput="64 bits/cycle",
            complexity="medium",
            pros=["Balanced area/throughput", "Moderate complexity"],
            cons=["Half throughput of full pipeline"],
            spec_overrides={"pipeline_type": "partial_2stage"},
        ),
    ]

    KEY_EXPANSION_ALTERNATIVES = [
        DesignAlternative(
            name="Pre-computed Key Schedule",
            description="All 11 round keys computed before encryption starts",
            trade_offs={
                "Area": "Medium (key storage registers)",
                "Latency": "Higher initial latency",
                "Key Agility": "Low (must wait for full expansion)",
            },
            estimated_resources={"lut": 500, "ff": 1408, "bram": 0, "dsp": 0},
            complexity="low",
            pros=["Simple control", "Keys available immediately during encryption"],
            cons=["Cannot start encryption until all keys ready"],
            spec_overrides={"key_expansion": "precomputed"},
        ),
        DesignAlternative(
            name="On-the-fly Key Expansion",
            description="Round keys generated in sync with data pipeline",
            trade_offs={
                "Area": "Low (no key storage)",
                "Latency": "Minimal initial latency",
                "Key Agility": "High (new key every cycle)",
            },
            estimated_resources={"lut": 800, "ff": 256, "bram": 0, "dsp": 0},
            complexity="medium",
            pros=["No key storage overhead", "Supports per-block key change"],
            cons=["More complex control logic", "Key must be available at each stage"],
            spec_overrides={"key_expansion": "on_the_fly"},
        ),
    ]

    def analyze_design_space(self, requirement: str,
                             spec_data: Dict[str, Any]) -> List[DesignChoice]:
        """Analyze requirements and generate relevant design choices.

        Returns a list of DesignChoice objects, each representing a decision
        point with concrete alternatives.
        """
        choices: List[DesignChoice] = []
        req_lower = requirement.lower()

        # Detect if this is a crypto/AES design
        is_crypto = any(kw in req_lower for kw in
                        ["aes", "des", "cipher", "encrypt", "decrypt", "crypto"])

        # S-Box implementation choice (for crypto designs)
        if is_crypto and any(kw in req_lower for kw in
                             ["sbox", "s-box", "configurable", "custom"]):
            choices.append(DesignChoice(
                question="Which S-Box implementation strategy?",
                context=(
                    "The design requires S-Box lookup tables. "
                    "This choice affects area, latency, and runtime configurability."
                ),
                options=self.SBOX_ALTERNATIVES,
                recommendation_idx=1,  # LUTRAM is usually the best balance
                impact_summary=(
                    "LUTRAM adds 1 cycle latency but enables runtime S-Box "
                    "reconfiguration with moderate area cost."
                ),
            ))

        # Pipeline architecture choice
        if any(kw in req_lower for kw in
               ["pipeline", "throughput", "high-speed", "high speed"]):
            choices.append(DesignChoice(
                question="Which pipeline architecture?",
                context=(
                    "Pipeline depth directly trades area for throughput. "
                    "Full unrolled gives max throughput but uses the most resources."
                ),
                options=self.PIPELINE_ALTERNATIVES,
                recommendation_idx=0,  # Full pipeline for high-throughput designs
                impact_summary=(
                    "Full unrolled pipeline achieves 128 bits/cycle throughput "
                    "at the cost of ~15K LUTs."
                ),
            ))

        # Key expansion choice (for AES)
        if is_crypto and "key" in req_lower:
            choices.append(DesignChoice(
                question="Which key expansion strategy?",
                context=(
                    "Key expansion can be pre-computed (all keys ready before "
                    "encryption) or on-the-fly (keys generated alongside data)."
                ),
                options=self.KEY_EXPANSION_ALTERNATIVES,
                recommendation_idx=1,  # On-the-fly for pipeline designs
                impact_summary=(
                    "On-the-fly expansion supports per-block key changes "
                    "and avoids key storage registers."
                ),
            ))

        return choices

    def generate_trade_off_matrix(self, choice: DesignChoice) -> TradeOffMatrix:
        """Generate a trade-off comparison matrix for a design choice."""
        if not choice.options:
            return TradeOffMatrix(metrics=[], alternatives=[])

        # Collect all metric names from alternatives
        all_metrics: List[str] = []
        for alt in choice.options:
            for m in alt.trade_offs:
                if m not in all_metrics:
                    all_metrics.append(m)

        return TradeOffMatrix(
            metrics=all_metrics,
            alternatives=choice.options,
        )

    def format_choice_for_user(self, choice: DesignChoice) -> str:
        """Format a design choice as readable text for AskUserQuestion.

        Returns markdown-formatted text describing the alternatives.
        """
        lines = [f"## {choice.question}", ""]
        if choice.context:
            lines.append(choice.context)
            lines.append("")

        matrix = self.generate_trade_off_matrix(choice)
        lines.append(matrix.to_markdown())
        lines.append("")

        for i, alt in enumerate(choice.options):
            rec = " (Recommended)" if i == choice.recommendation_idx else ""
            lines.append(f"### Option {i+1}: {alt.name}{rec}")
            lines.append(alt.description)
            if alt.pros:
                lines.append(f"  Pros: {', '.join(alt.pros)}")
            if alt.cons:
                lines.append(f"  Cons: {', '.join(alt.cons)}")
            lines.append("")

        if choice.impact_summary:
            lines.append(f"Recommendation rationale: {choice.impact_summary}")

        return "\n".join(lines)

    def apply_choice(self, spec_data: Dict[str, Any],
                     choice: DesignChoice,
                     selected_idx: int) -> Dict[str, Any]:
        """Apply a selected alternative's overrides to the spec.

        Returns modified spec_data (does not mutate the original).
        """
        import copy
        new_spec = copy.deepcopy(spec_data)

        if 0 <= selected_idx < len(choice.options):
            alt = choice.options[selected_idx]
            for key, value in alt.spec_overrides.items():
                new_spec[key] = value

            # Record the choice in metadata
            metadata = new_spec.setdefault("design_choices", [])
            metadata.append({
                "question": choice.question,
                "selected": alt.name,
                "alternatives_considered": len(choice.options),
            })

        return new_spec
