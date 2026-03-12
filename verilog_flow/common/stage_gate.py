"""Stage gate checker — quality gates between VeriFlow pipeline stages."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .project_layout import ProjectLayout, STAGE_DIRS


@dataclass
class GateIssue:
    """A single gate-check finding."""
    check: str
    severity: str   # "error" | "warning"
    message: str


@dataclass
class StageGateResult:
    """Result of a stage gate check."""
    stage: int
    passed: bool
    issues: List[GateIssue] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> List[GateIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[GateIssue]:
        return [i for i in self.issues if i.severity == "warning"]


class StageGateChecker:
    """Run quality-gate checks for each stage of the VeriFlow pipeline."""

    def __init__(self, layout: ProjectLayout):
        self.layout = layout
        self._checkers = {
            1: self._check_stage1,
            2: self._check_stage2,
            3: self._check_stage3,
            4: self._check_stage4,
            5: self._check_stage5,
        }

    def check_stage(self, stage: int) -> StageGateResult:
        """Run gate checks for a single stage."""
        checker = self._checkers.get(stage)
        if not checker:
            raise ValueError(f"Unknown stage {stage}")
        return checker()

    def check_all(self) -> List[StageGateResult]:
        """Run gate checks for all stages."""
        return [self.check_stage(s) for s in sorted(self._checkers)]

    def check_transition(self, from_stage: int, to_stage: int) -> StageGateResult:
        """Check whether it is safe to transition from one stage to the next."""
        result = self.check_stage(from_stage)
        if result.errors:
            result.passed = False
            result.issues.append(GateIssue(
                "TRANSITION_BLOCKED", "error",
                f"Stage {from_stage} has errors — cannot proceed to stage {to_stage}"))
        return result

    # ── Per-stage checkers ───────────────────────────────────────────

    def _check_stage1(self) -> StageGateResult:
        """Stage 1 gate: spec completeness."""
        issues: List[GateIssue] = []
        specs_dir = self.layout.get_dir(1, "specs")
        specs = list(specs_dir.glob("*_spec.json")) if specs_dir.exists() else []
        if not specs:
            issues.append(GateIssue("SPEC_MISSING", "error",
                                    "No *_spec.json files found in stage_1_spec/specs/"))
        return StageGateResult(
            stage=1, passed=len(issues) == 0, issues=issues,
            metrics={"spec_count": len(specs)})

    def _check_stage2(self) -> StageGateResult:
        """Stage 2 gate: scenarios and golden traces."""
        issues: List[GateIssue] = []
        scen_dir = self.layout.get_dir(2, "scenarios")
        trace_dir = self.layout.get_dir(2, "golden_traces")
        scenarios = list(scen_dir.glob("*.yaml")) if scen_dir.exists() else []
        traces = list(trace_dir.glob("*.json")) if trace_dir.exists() else []
        if not scenarios:
            issues.append(GateIssue("SCENARIO_MISSING", "error",
                                    "No YAML scenarios in stage_2_timing/scenarios/"))
        if scenarios and not traces:
            issues.append(GateIssue("TRACE_MISSING", "warning",
                                    "Scenarios exist but no golden traces generated"))
        return StageGateResult(
            stage=2, passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            metrics={"scenario_count": len(scenarios), "trace_count": len(traces)})

    def _check_stage3(self) -> StageGateResult:
        """Stage 3 gate: RTL file coverage."""
        issues: List[GateIssue] = []
        rtl_dir = self.layout.get_dir(3, "rtl")
        rtl_files = list(rtl_dir.rglob("*.v")) if rtl_dir.exists() else []
        if not rtl_files:
            issues.append(GateIssue("RTL_MISSING", "error",
                                    "No .v files found in stage_3_codegen/rtl/"))
        return StageGateResult(
            stage=3, passed=len(issues) == 0, issues=issues,
            metrics={"rtl_file_count": len(rtl_files)})

    def _check_stage4(self) -> StageGateResult:
        """Stage 4 gate: simulation pass rate."""
        issues: List[GateIssue] = []
        tb_dir = self.layout.get_dir(4, "tb")
        sim_dir = self.layout.get_dir(4, "sim")
        tbs = list(tb_dir.glob("*.v")) + list(tb_dir.glob("*.sv")) if tb_dir.exists() else []
        sim_logs = list(sim_dir.glob("*.log")) if sim_dir.exists() else []
        if not tbs:
            issues.append(GateIssue("TB_MISSING", "warning",
                                    "No testbench files in stage_4_sim/tb/"))
        # Check sim logs for failures
        fail_count = 0
        for log in sim_logs:
            content = log.read_text(encoding="utf-8", errors="ignore")
            if "FAIL" in content or "ERROR" in content:
                fail_count += 1
        if fail_count > 0:
            issues.append(GateIssue("SIM_FAILURES", "error",
                                    f"{fail_count} simulation log(s) contain failures"))
        total = len(sim_logs) if sim_logs else 0
        pass_rate = (total - fail_count) / total if total > 0 else 0.0
        return StageGateResult(
            stage=4, passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            metrics={"tb_count": len(tbs), "sim_pass_rate": pass_rate})

    def _check_stage5(self) -> StageGateResult:
        """Stage 5 gate: synthesis success rate."""
        issues: List[GateIssue] = []
        synth_dir = self.layout.get_dir(5, "synth")
        synth_reports = list(synth_dir.glob("*.json")) if synth_dir.exists() else []
        if not synth_reports:
            issues.append(GateIssue("SYNTH_MISSING", "warning",
                                    "No synthesis reports in stage_5_synth/synth/"))
        return StageGateResult(
            stage=5, passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            metrics={"synth_report_count": len(synth_reports)})
