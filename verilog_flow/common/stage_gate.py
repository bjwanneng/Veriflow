"""Stage gate checker — quality gates between VeriFlow pipeline stages."""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
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
class ApprovalRecord:
    """Record of a manual stage-transition approval."""
    from_stage: int
    to_stage: int
    approved_by: str
    approved_at: str
    gate_result_summary: str
    token: str = ""


@dataclass
class StageGateResult:
    """Result of a stage gate check."""
    stage: int
    passed: bool
    issues: List[GateIssue] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    approval: Optional[ApprovalRecord] = None

    @property
    def errors(self) -> List[GateIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[GateIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def fully_approved(self) -> bool:
        """True only if gate passed AND manual approval was given."""
        return self.passed and self.approval is not None


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

    def check_transition(self, from_stage: int, to_stage: int,
                         approve_token: Optional[str] = None,
                         approved_by: str = "unknown") -> StageGateResult:
        """Check whether it is safe to transition from one stage to the next.

        Requires BOTH:
          1. Automated gate checks pass (no errors)
          2. Explicit manual approval via approve_token or interactive prompt

        Without approval, result.fully_approved will be False even if
        automated checks pass.
        """
        # ── Input validation (guard against skipping stages) ─────────
        if from_stage not in self._checkers:
            raise ValueError(
                f"Invalid from_stage={from_stage}. Valid stages: {sorted(self._checkers.keys())}")
        if to_stage not in self._checkers:
            raise ValueError(
                f"Invalid to_stage={to_stage}. Valid stages: {sorted(self._checkers.keys())}")
        if to_stage != from_stage + 1:
            raise ValueError(
                f"Cannot skip stages: {from_stage}→{to_stage}. "
                f"You must transition one stage at a time ({from_stage}→{from_stage + 1}).")
        result = self.check_stage(from_stage)
        if result.errors:
            result.passed = False
            result.issues.append(GateIssue(
                "TRANSITION_BLOCKED", "error",
                f"Stage {from_stage} has errors — cannot proceed to stage {to_stage}"))
            return result

        # ── Manual approval gate ─────────────────────────────────────
        if approve_token:
            result.approval = self._create_approval(
                from_stage, to_stage, approved_by, approve_token, result)
            self._save_approval(result.approval)
        else:
            result.issues.append(GateIssue(
                "APPROVAL_REQUIRED", "error",
                f"Stage {from_stage}→{to_stage} requires manual approval. "
                f"Use --approve-token <token> or call require_manual_approval() interactively."))
            result.passed = False

        return result

    def require_manual_approval(self, from_stage: int, to_stage: int,
                                 approved_by: str = "interactive") -> ApprovalRecord:
        """Interactive manual approval — blocks until user confirms.

        Call this from CLI or script. Prints gate summary and asks for y/N.
        Returns ApprovalRecord on success, raises RuntimeError on rejection.
        """
        result = self.check_stage(from_stage)

        # Print summary for human review
        print(f"\n{'='*60}")
        print(f"  STAGE GATE: {from_stage} → {to_stage}")
        print(f"{'='*60}")
        print(f"  Errors:   {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}")
        print(f"  Metrics:  {result.metrics}")
        if result.issues:
            print(f"\n  Issues:")
            for issue in result.issues:
                print(f"    [{issue.severity.upper()}] {issue.check}: {issue.message}")
        print(f"{'='*60}")

        if result.errors:
            raise RuntimeError(
                f"Stage {from_stage} has {len(result.errors)} error(s). "
                f"Fix them before requesting approval.")

        # Ask for confirmation
        answer = input(f"\n  Approve transition Stage {from_stage} → {to_stage}? [y/N]: ").strip().lower()
        if answer != 'y':
            raise RuntimeError(f"Transition {from_stage}→{to_stage} rejected by user.")

        token = f"manual_{int(time.time())}"
        approval = self._create_approval(from_stage, to_stage, approved_by, token, result)
        self._save_approval(approval)
        print(f"  ✓ Approved. Token: {token}\n")
        return approval

    def _create_approval(self, from_stage: int, to_stage: int,
                         approved_by: str, token: str,
                         result: StageGateResult) -> ApprovalRecord:
        summary = (f"errors={len(result.errors)}, warnings={len(result.warnings)}, "
                   f"metrics={result.metrics}")
        return ApprovalRecord(
            from_stage=from_stage,
            to_stage=to_stage,
            approved_by=approved_by,
            approved_at=datetime.now().isoformat(),
            gate_result_summary=summary,
            token=token,
        )

    def _save_approval(self, approval: ApprovalRecord):
        """Persist approval record to .veriflow/approvals/."""
        approvals_dir = self.layout.root / ".veriflow" / "approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)
        filename = f"approval_{approval.from_stage}_to_{approval.to_stage}_{approval.token}.json"
        path = approvals_dir / filename
        data = {
            "from_stage": approval.from_stage,
            "to_stage": approval.to_stage,
            "approved_by": approval.approved_by,
            "approved_at": approval.approved_at,
            "gate_result_summary": approval.gate_result_summary,
            "token": approval.token,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_approval_history(self) -> List[ApprovalRecord]:
        """Load all approval records from disk."""
        approvals_dir = self.layout.root / ".veriflow" / "approvals"
        if not approvals_dir.exists():
            return []
        records = []
        for f in sorted(approvals_dir.glob("approval_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                records.append(ApprovalRecord(**data))
            except Exception:
                continue
        return records

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
