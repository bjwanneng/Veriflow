"""
Per-Stage Deliverable Checklists for VeriFlow.

This module defines structured checklists for every stage, ensuring
all required deliverables are created before marking a stage complete.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Deliverable:
    """Single deliverable item in a stage checklist."""
    name: str
    description: str
    filename_patterns: List[str] = field(default_factory=list)  # Glob patterns
    required: bool = True
    content_checks: List[str] = field(default_factory=list)  # Strings that must be present


@dataclass
class StageChecklist:
    """Complete checklist for a single stage."""
    stage_number: int
    stage_name: str
    deliverables: List[Deliverable] = field(default_factory=list)

    def verify(self, stage_dir: Path) -> Tuple[bool, List[str], List[str]]:
        """
        Verify all deliverables are present in the given directory.

        Returns:
            (all_passed, missing_deliverables, warnings)
        """
        missing: List[str] = []
        warnings: List[str] = []

        for deliv in self.deliverables:
            found = False
            for pattern in deliv.filename_patterns:
                if any(stage_dir.glob(pattern)):
                    found = True
                    break
            if deliv.required and not found:
                missing.append(
                    f"[MISSING] {deliv.name}: {deliv.description} "
                    f"(expected one of: {', '.join(deliv.filename_patterns)})"
                )
            elif not deliv.required and not found:
                warnings.append(
                    f"[OPTIONAL] {deliv.name}: {deliv.description} not found"
                )

        return (len(missing) == 0, missing, warnings)


# ===========================================================================
# Stage Checklist Definitions
# ===========================================================================

STAGE_CHECKLISTS: Dict[int, StageChecklist] = {
    0: StageChecklist(
        stage_number=0,
        stage_name="Project Initialization",
        deliverables=[
            Deliverable(
                name="Directory Structure",
                description="All stage directories created",
                filename_patterns=["stage_1_spec", "stage_2_timing", "stage_3_codegen",
                                   "stage_4_sim", "stage_5_synth", ".veriflow"]
            ),
            Deliverable(
                name="Workflow Mode",
                description="Workflow mode selected (supervised/autonomous)",
                filename_patterns=[".veriflow/workflow_mode.txt"]
            ),
        ]
    ),

    1: StageChecklist(
        stage_number=1,
        stage_name="Micro-Architecture Specification",
        deliverables=[
            Deliverable(
                name="Arch Spec JSON",
                description="Micro-architecture specification conforming to arch_spec_v2.json schema",
                filename_patterns=["*_spec.json", "arch_spec.json"]
            ),
            Deliverable(
                name="Pre-Generation Validation Report",
                description="Requirement consistency, timing feasibility, resource estimation",
                filename_patterns=["*validation*.txt", "*precheck*.txt", "*report*.txt"]
            ),
        ]
    ),

    2: StageChecklist(
        stage_number=2,
        stage_name="Virtual Timing Modeling",
        deliverables=[
            Deliverable(
                name="Timing Scenarios YAML",
                description="Parameterized timing scenarios (reset, normal, edge, config)",
                filename_patterns=["*scenario*.yml", "*scenario*.yaml", "timing*.yml", "timing*.yaml"]
            ),
            Deliverable(
                name="Golden Trace",
                description="Golden reference trace (JSON or VCD)",
                filename_patterns=["*golden*.json", "*golden*.vcd", "golden_trace.*"]
            ),
            Deliverable(
                name="WaveDrom Waveform",
                description="WaveDrom JSON/HTML visualization",
                filename_patterns=["*wavedrom*.json", "*wavedrom*.html", "waveform*.json"]
            ),
            Deliverable(
                name="Assertions Explanation",
                description="SVA-like assertion properties with physical meaning and violation scenarios",
                filename_patterns=["*assertion*.md", "*assertion*.txt"]
            ),
            Deliverable(
                name="Stimulus Template",
                description="Testbench stimulus template for Stage 4",
                filename_patterns=["*stimulus*.v", "stimulus*.v"]
            ),
        ]
    ),

    3: StageChecklist(
        stage_number=3,
        stage_name="RTL Code Generation + Lint",
        deliverables=[
            Deliverable(
                name="RTL Files",
                description="All modules from arch spec have corresponding .v files",
                filename_patterns=["rtl/*.v"]
            ),
            Deliverable(
                name="Lint Report",
                description="Two-layer lint results (regex rules + iverilog/Verilator)",
                filename_patterns=["*lint*.txt", "lint_report.*"]
            ),
            Deliverable(
                name="Compilation Log",
                description="iverilog compilation with 0 errors",
                filename_patterns=["*compile*.log", "compile*.txt"]
            ),
        ]
    ),

    4: StageChecklist(
        stage_number=4,
        stage_name="Simulation & Verification",
        deliverables=[
            Deliverable(
                name="Unit Testbenches",
                description="tb_unit_*.v for all non-top modules",
                filename_patterns=["tb/tb_unit_*.v"]
            ),
            Deliverable(
                name="Integration Testbench",
                description="Self-checking top-level testbench",
                filename_patterns=["tb/tb_*.v", "tb/*top*.v"]
            ),
            Deliverable(
                name="Simulation Log",
                description="Simulation results (all PASS, no FAIL)",
                filename_patterns=["*sim*.log", "sim_output/*.txt"]
            ),
        ]
    ),

    5: StageChecklist(
        stage_number=5,
        stage_name="Synthesis Analysis",
        deliverables=[
            Deliverable(
                name="Yosys Script",
                description="Synthesis script for yosys",
                filename_patterns=["*.ys", "synth*.ys"]
            ),
            Deliverable(
                name="Synthesis Report",
                description="Resource utilization and timing analysis",
                filename_patterns=["*synth*.rpt", "*synth*.txt", "stat*.txt"]
            ),
        ]
    ),
}


def get_checklist(stage: int) -> Optional[StageChecklist]:
    """Get the checklist for a given stage number."""
    return STAGE_CHECKLISTS.get(stage)


def verify_stage(stage: int, project_root: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Verify the given stage is complete by checking its deliverables.

    Args:
        stage: Stage number (0-5)
        project_root: Root directory of the project

    Returns:
        (success, missing, warnings)
    """
    checklist = get_checklist(stage)
    if not checklist:
        return (False, [f"No checklist defined for stage {stage}"], [])

    # Determine stage directory
    stage_dir_names = {
        0: ".",
        1: "stage_1_spec",
        2: "stage_2_timing",
        3: "stage_3_codegen",
        4: "stage_4_sim",
        5: "stage_5_synth",
    }
    stage_dir = project_root / stage_dir_names.get(stage, f"stage_{stage}_*")

    if not stage_dir.exists():
        return (False, [f"Stage directory not found: {stage_dir}"], [])

    return checklist.verify(stage_dir)
