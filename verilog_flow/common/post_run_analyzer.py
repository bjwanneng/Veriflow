"""Post-run analysis for self-evolution — identifies patterns in failures and regressions."""

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_layout import ProjectLayout
from .execution_log import ExecutionLogger, RunLog
from .experience_db import ExperienceDB, FailureCase


@dataclass
class Insight:
    """A single analysis insight / recommendation."""
    category: str   # "repeated_failure" | "perf_regression" | "coverage_gap" | "suggestion"
    severity: str   # "high" | "medium" | "low"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    """Aggregated post-run analysis report."""
    run_count: int = 0
    insights: List[Insight] = field(default_factory=list)
    stage_stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def high_severity(self) -> List[Insight]:
        return [i for i in self.insights if i.severity == "high"]


class PostRunAnalyzer:
    """Analyze recent pipeline runs and produce actionable insights."""

    def __init__(self, layout: ProjectLayout,
                 experience_db: Optional[ExperienceDB] = None):
        self.layout = layout
        self._logger = ExecutionLogger(layout)
        self._exp_db = experience_db or ExperienceDB(
            db_path=layout.get_experience_dir())

    def analyze(self, n_recent: int = 10) -> AnalysisReport:
        """Analyze the most recent *n_recent* runs and return an AnalysisReport."""
        runs = self._logger.list_runs(n_recent=n_recent)
        report = AnalysisReport(run_count=len(runs))

        if not runs:
            report.insights.append(Insight(
                "suggestion", "low", "No run logs found — run the pipeline first."))
            return report

        self._analyze_repeated_failures(runs, report)
        self._analyze_performance(runs, report)
        self._analyze_coverage_gaps(runs, report)
        self._generate_suggestions(runs, report)

        # Persist report
        self._save_report(report)

        # Record unresolved failures into ExperienceDB
        self._record_failures(runs)

        return report

    # ── Analysis dimensions ──────────────────────────────────────────

    def _analyze_repeated_failures(self, runs: List[RunLog],
                                   report: AnalysisReport) -> None:
        """Detect stages that fail repeatedly across runs."""
        fail_counter: Counter = Counter()
        for run in runs:
            for slog in run.stages:
                if not slog.success:
                    fail_counter[slog.stage_name] += 1

        for stage_name, count in fail_counter.most_common():
            if count >= 2:
                report.insights.append(Insight(
                    "repeated_failure", "high",
                    f"Stage '{stage_name}' failed in {count}/{len(runs)} recent runs",
                    {"stage": stage_name, "fail_count": count}))

    def _analyze_performance(self, runs: List[RunLog],
                             report: AnalysisReport) -> None:
        """Detect performance regressions (duration trending up)."""
        durations = [r.duration for r in runs if r.duration > 0]
        if len(durations) < 3:
            return
        recent_avg = sum(durations[:3]) / 3
        older_avg = sum(durations[3:]) / max(len(durations) - 3, 1)
        if older_avg > 0 and recent_avg > older_avg * 1.5:
            report.insights.append(Insight(
                "perf_regression", "medium",
                f"Recent runs are ~{recent_avg/older_avg:.1f}x slower than earlier runs",
                {"recent_avg_s": round(recent_avg, 2),
                 "older_avg_s": round(older_avg, 2)}))

        # Per-stage stats
        stage_durations: Dict[str, List[float]] = {}
        for run in runs:
            for slog in run.stages:
                stage_durations.setdefault(slog.stage_name, []).append(slog.duration)
        report.stage_stats = {
            name: {"avg_s": round(sum(ds) / len(ds), 2), "runs": len(ds)}
            for name, ds in stage_durations.items()
        }

    def _analyze_coverage_gaps(self, runs: List[RunLog],
                               report: AnalysisReport) -> None:
        """Identify stages that were never executed."""
        executed_stages = set()
        for run in runs:
            for slog in run.stages:
                executed_stages.add(slog.stage_num)
        for s in range(1, 6):
            if s not in executed_stages:
                report.insights.append(Insight(
                    "coverage_gap", "medium",
                    f"Stage {s} was never executed in the last {len(runs)} runs"))

    def _generate_suggestions(self, runs: List[RunLog],
                              report: AnalysisReport) -> None:
        """Produce general improvement suggestions."""
        success_count = sum(1 for r in runs if r.success)
        total = len(runs)
        rate = success_count / total if total else 0
        if rate < 0.5:
            report.insights.append(Insight(
                "suggestion", "high",
                f"Overall success rate is {rate*100:.0f}% — consider reviewing failing stages"))
        elif rate < 0.8:
            report.insights.append(Insight(
                "suggestion", "medium",
                f"Success rate is {rate*100:.0f}% — room for improvement"))

    # ── Side-effects ─────────────────────────────────────────────────

    def _record_failures(self, runs: List[RunLog]) -> None:
        """Write failure cases from recent runs into ExperienceDB."""
        for run in runs:
            for slog in run.stages:
                if not slog.success and slog.error:
                    case = FailureCase(
                        case_id="",
                        module_name=run.project_name,
                        target_frequency_mhz=0.0,
                        stage=str(slog.stage_num),
                        failure_type="pipeline_failure",
                        error_message=slog.error,
                        run_id=run.run_id,
                    )
                    self._exp_db.record_failure(case)

    def _save_report(self, report: AnalysisReport) -> Path:
        reports_dir = self.layout.get_reports_dir()
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / "post_run_analysis.json"
        path.write_text(
            json.dumps(asdict(report), indent=2, default=str),
            encoding="utf-8")
        return path
