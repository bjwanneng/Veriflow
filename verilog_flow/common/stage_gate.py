"""Stage gate checker — quality gates between VeriFlow pipeline stages.

v3.3 Enhancements:
- Stage Completion Marker (immutable, prevents skipping stages)
- Two-layer lint ENFORCED in Stage 3
- Experience DB integration for failure suggestions
"""

import json
import os
import re
import shutil
import subprocess
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
    severity: str   # "error" | "warning" | "info"
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
    """Run quality-gate checks for each stage of the VeriFlow pipeline.

    v3.3: Enhanced with Completion Markers and two-layer lint.
    """

    STAGE_NAMES = {
        1: "Micro-Architecture Spec",
        2: "Timing Scenarios & Golden Traces",
        3: "Verilog RTL Code Generation",
        4: "Simulation & Verification",
        5: "Synthesis Analysis",
    }

    def __init__(self, layout: ProjectLayout):
        self.layout = layout
        self._checkers = {
            1: self._check_stage1,
            2: self._check_stage2,
            3: self._check_stage3,
            4: self._check_stage4,
            5: self._check_stage5,
        }

    # =========================================================================
    # Completion Marker (v3.3)
    # =========================================================================

    def _get_marker_path(self, stage: int) -> Path:
        """Get path to completion marker file."""
        return self.layout.root / ".veriflow" / "stage_completed" / f"stage_{stage}_COMPLETE"

    def is_stage_complete(self, stage: int) -> bool:
        """Check if a stage has completion marker (immutable)."""
        return self._get_marker_path(stage).exists()

    def get_current_stage(self) -> int:
        """Get the latest completed stage number."""
        for s in range(5, 0, -1):
            if self.is_stage_complete(s):
                return s
        return 0

    def can_proceed_to(self, to_stage: int) -> tuple[bool, str]:
        """
        Check if transition to a stage is allowed.

        Returns: (allowed: bool, reason: str)
        """
        current = self.get_current_stage()
        expected_next = current + 1

        if to_stage != expected_next:
            return False, f"Must complete Stage {expected_next} first (current: {current})"

        return True, "OK"

    def mark_stage_complete(self, stage: int):
        """
        Mark a stage as COMPLETE (immutable action).

        Creates a marker file in .veriflow/stage_completed/.
        This action cannot be undone.
        """
        marker_dir = self._get_marker_path(stage).parent
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = {
            "stage": stage,
            "stage_name": self.STAGE_NAMES.get(stage, f"Stage {stage}"),
            "completed_at": datetime.now().isoformat(),
        }
        self._get_marker_path(stage).write_text(json.dumps(marker, indent=2))
        print(f"✓ Stage {stage} marked COMPLETE (immutable marker created)")

    # =========================================================================
    # Stage Check Methods
    # =========================================================================

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

        v3.3 ENHANCED:
        1. First checks ALL previous stages have completion markers
        2. Then runs automated gate checks
        3. Requires manual approval

        Requires BOTH:
          1. Automated gate checks pass (no errors)
          2. Explicit manual approval via approve_token or interactive prompt
        3. ALL previous stages marked COMPLETE

        Without approval, result.fully_approved will be False even if
        automated checks pass.
        """
        # ── v3.3: Check ALL previous stages have completion markers ────────
        for s in range(1, from_stage):
            if not self.is_stage_complete(s):
                result = StageGateResult(stage=from_stage, passed=False)
                result.issues.append(GateIssue(
                    "STAGE_NOT_COMPLETE", "error",
                    f"Stage {s} was never marked complete — cannot proceed from {from_stage}. "
                    f"All stages 1..{from_stage-1} must be marked COMPLETE first."))
                return result

        # ── Input validation (guard against skipping stages) ─────────────
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
        print(f"  ✓ Approved. Token: {token}")

        # v3.3: Auto-mark stage complete after approval
        self.mark_stage_complete(from_stage)

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

    # =========================================================================
    # Per-stage checkers
    # =========================================================================

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
        """Stage 3 gate: RTL file coverage, TWO-LAYER LINT, and compilation.

        v3.3 ENHANCED: Now runs two-layer lint BEFORE compile check.

        Checks:
          1. Every module in spec has a corresponding .v file
          2. No .v file is a stub (< 100 bytes)
          3. No .v file contains TODO/placeholder markers
          4. TWO-LAYER LINT (Python regex + Verilator)
          5. All .v files compile with iverilog (if available)
        """
        issues: List[GateIssue] = []
        rtl_dir = self.layout.get_dir(3, "rtl")
        rtl_files = list(rtl_dir.rglob("*.v")) if rtl_dir.exists() else []

        if not rtl_files:
            issues.append(GateIssue("RTL_MISSING", "error",
                                    "No .v files found in stage_3_codegen/rtl/"))
            return StageGateResult(
                stage=3, passed=False, issues=issues,
                metrics={"rtl_file_count": 0})

        # Build map of module_name -> file_path from RTL files
        rtl_map = {f.stem: f for f in rtl_files}

        # --- Check 1: spec-vs-RTL coverage ---
        spec_modules = self._load_spec_modules()
        missing_modules = []
        if spec_modules:
            for mod_name in spec_modules:
                if mod_name not in rtl_map:
                    missing_modules.append(mod_name)
                    issues.append(GateIssue(
                        "MODULE_MISSING", "error",
                        f"Module '{mod_name}' defined in spec but no "
                        f"'{mod_name}.v' found under {rtl_dir}"))

        # --- Check 2 & 3: file size and placeholder markers ---
        placeholder_re = re.compile(
            r'//\s*TODO|//\s*placeholder|//\s*\.\.\.|'
            r'//\s*continue\b|/\*\s*\.\.\.\s*\*/|/\*[^*]*port connections[^*]*\*/',
            re.IGNORECASE,
        )
        min_size = 100  # bytes

        for vfile in rtl_files:
            size = vfile.stat().st_size
            if size < min_size:
                issues.append(GateIssue(
                    "RTL_STUB", "error",
                    f"{vfile.name}: file too small ({size} bytes), likely a stub"))
                continue

            content = vfile.read_text(encoding="utf-8", errors="replace")
            matches = placeholder_re.findall(content)
            if matches:
                unique = list(set(matches))
                issues.append(GateIssue(
                    "RTL_PLACEHOLDER", "error",
                    f"{vfile.name}: contains placeholder markers: {unique}"))

        # --- v3.3 NEW: Check 4 — TWO-LAYER LINT ---
        lint_issues = self._run_two_layer_lint(rtl_files)
        issues.extend(lint_issues)

        # --- Check 5: iverilog compilation ---
        compile_issues = self._check_compilation(rtl_files)
        issues.extend(compile_issues)

        has_errors = any(i.severity == "error" for i in issues)
        return StageGateResult(
            stage=3, passed=not has_errors, issues=issues,
            metrics={
                "rtl_file_count": len(rtl_files),
                "spec_module_count": len(spec_modules),
                "missing_module_count": len(missing_modules),
            })

    def _run_two_layer_lint(self, rtl_files: List[Path]) -> List[GateIssue]:
        """v3.3: Run two-layer lint on all RTL files.

        Layer 1: Python regex rules (always runs)
        Layer 2: Verilator --lint-only (if installed)
        """
        issues: List[GateIssue] = []
        try:
            from verilog_flow.stage3.lint_checker import LintChecker
            linter = LintChecker()
            results = linter.check_files_deep(rtl_files)
            for result in results:
                for lint_issue in result.issues:
                    severity = lint_issue.severity
                    if severity == "error":
                        issues.append(GateIssue(
                            f"LINT_{lint_issue.rule_id}", "error",
                            f"{result.file_path}:{lint_issue.line_number}: {lint_issue.message}"))
                    elif severity == "warning":
                        issues.append(GateIssue(
                            f"LINT_{lint_issue.rule_id}", "warning",
                            f"{result.file_path}:{lint_issue.line_number}: {lint_issue.message}"))
                    else:
                        issues.append(GateIssue(
                            f"LINT_{lint_issue.rule_id}", "info",
                            f"{result.file_path}:{lint_issue.line_number}: {lint_issue.message}"))
        except ImportError:
            issues.append(GateIssue(
                "LINT_CHECKER_UNAVAILABLE", "warning",
                "LintChecker not imported — skipping two-layer lint"))
        return issues

    def _load_spec_modules(self) -> List[str]:
        """Load module names from all spec JSON files in stage_1_spec/specs/."""
        modules = []
        specs_dir = self.layout.get_dir(1, "specs")
        if not specs_dir.exists():
            return modules
        for spec_file in specs_dir.glob("*_spec.json"):
            try:
                data = json.loads(spec_file.read_text(encoding="utf-8"))
                for mod in data.get("modules", []):
                    name = mod.get("name", "")
                    if name:
                        modules.append(name)
            except (json.JSONDecodeError, KeyError):
                continue
        return modules

    def _detect_iverilog(self) -> Optional[str]:
        """Find iverilog executable via PATH or common oss-cad-suite locations."""
        iverilog = shutil.which("iverilog") or shutil.which("iverilog.exe")
        if iverilog:
            return iverilog
        # Check common Windows oss-cad-suite location
        oss_path = Path("C:/oss-cad-suite/bin/iverilog.exe")
        if oss_path.exists():
            return str(oss_path)
        return None

    def _check_compilation(self, verilog_files: List[Path]) -> List[GateIssue]:
        """Try to compile all .v files with iverilog. Returns issues."""
        issues: List[GateIssue] = []
        iverilog = self._detect_iverilog()
        if not iverilog:
            issues.append(GateIssue(
                "IVERILOG_NOT_FOUND", "warning",
                "iverilog not found — skipping compilation check. "
                "Install oss-cad-suite or add iverilog to PATH."))
            return issues

        rtl_dir = self.layout.get_dir(3, "rtl")
        cmd = [iverilog, "-g2005-sv", "-o", os.devnull]
        # Add all rtl subdirectories as include paths
        if rtl_dir.exists():
            for subdir in rtl_dir.iterdir():
                if subdir.is_dir():
                    cmd.extend(["-I", str(subdir)])
            cmd.extend(["-I", str(rtl_dir)])
        cmd.extend(str(f) for f in verilog_files)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                issues.append(GateIssue(
                    "COMPILE_FAIL", "error",
                    f"iverilog compilation failed:\n{stderr}"))

                # v3.3: Suggest from Experience DB if available
                exp_suggestions = self._get_experience_suggestions(stderr)
                for suggestion in exp_suggestions:
                    issues.append(GateIssue(
                        f"EXP_{suggestion['rule_id']}", "info",
                        f"Known pattern: {suggestion['description']} — {suggestion['fix']}"))

        except subprocess.TimeoutExpired:
            issues.append(GateIssue(
                "COMPILE_TIMEOUT", "error",
                "iverilog compilation timed out (>60s)"))
        except FileNotFoundError:
            issues.append(GateIssue(
                "IVERILOG_NOT_FOUND", "warning",
                f"iverilog not found at {iverilog}"))

        return issues

    def _get_experience_suggestions(self, error_message: str) -> List[Dict]:
        """v3.3: Get suggestions from experience DB for an error message."""
        suggestions = []
        # Hardcoded from AES-128 project lessons
        known_patterns = [
            {
                "rule_id": "BYTE_ORDER_MISMATCH",
                "description": "Byte order mismatch (MSB vs LSB)",
                "symptoms": ["NIST test vector fails", "byte order"],
                "fix": "Align byte mapping: s[0] = [127:120], s[15] = [7:0]"
            },
            {
                "rule_id": "REG_DRIVEN_BY_ASSIGN",
                "description": "reg signal driven by assign",
                "symptoms": ["cannot be driven by continuous assignment"],
                "fix": "Change reg to wire, or use always block instead of assign"
            },
            {
                "rule_id": "FORWARD_REFERENCE",
                "description": "Signal used before declaration",
                "symptoms": ["Unable to bind wire/reg/memory"],
                "fix": "Move signal declaration before usage"
            }
        ]
        for pattern in known_patterns:
            for symptom in pattern["symptoms"]:
                if symptom.lower() in error_message.lower():
                    suggestions.append(pattern)
                    break
        return suggestions

    def _check_stage4(self) -> StageGateResult:
        """Stage 4 gate: simulation pass rate."""
        issues: List[GateIssue] = []
        tb_dir = self.layout.get_dir(4, "tb")
        sim_dir = self.layout.get_dir(4, "sim")
        tbs = list(tb_dir.glob("*.v")) + list(tb_dir.glob("*.sv")) + list(tb_dir.glob("test_*.py")) if tb_dir.exists() else []
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
