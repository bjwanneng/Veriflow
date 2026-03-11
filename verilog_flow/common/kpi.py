"""KPI tracking and dashboard generation."""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class StageMetrics:
    """Metrics for a single stage."""
    stage_name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    token_count: int = 0
    success: bool = False
    error_message: Optional[str] = None

    # Stage-specific metrics
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time


@dataclass
class RunMetrics:
    """Metrics for a complete run."""
    run_id: str
    module_name: str
    target_frequency_mhz: float
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    stages: List[StageMetrics] = field(default_factory=list)

    # Overall results
    pass_at_1: bool = False
    timing_closure: bool = False
    area_utilization: Optional[float] = None

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_tokens(self) -> int:
        return sum(s.token_count for s in self.stages)


class KPITracker:
    """Track KPIs across runs and generate dashboards."""

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path(".veriflow/kpi.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.current_run: Optional[RunMetrics] = None
        self._history: List[Dict] = self._load_history()

    def _load_history(self) -> List[Dict]:
        """Load historical KPI data."""
        if self.storage_path.exists():
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        return []

    def _save_history(self):
        """Save KPI history."""
        with open(self.storage_path, 'w') as f:
            json.dump(self._history, f, indent=2, default=str)

    def start_run(self, run_id: str, module_name: str, target_frequency_mhz: float) -> RunMetrics:
        """Start tracking a new run."""
        self.current_run = RunMetrics(
            run_id=run_id,
            module_name=module_name,
            target_frequency_mhz=target_frequency_mhz
        )
        return self.current_run

    def start_stage(self, stage_name: str) -> StageMetrics:
        """Start a new stage in the current run."""
        if not self.current_run:
            raise RuntimeError("No active run. Call start_run() first.")

        stage = StageMetrics(stage_name=stage_name)
        self.current_run.stages.append(stage)
        return stage

    def end_stage(self, success: bool = True, error_message: Optional[str] = None, **custom_metrics):
        """End the current stage."""
        if not self.current_run or not self.current_run.stages:
            raise RuntimeError("No active stage.")

        stage = self.current_run.stages[-1]
        stage.end_time = time.time()
        stage.success = success
        stage.error_message = error_message
        stage.custom_metrics.update(custom_metrics)

    def end_run(self, pass_at_1: bool = False, timing_closure: bool = False, **kwargs):
        """End the current run and save metrics."""
        if not self.current_run:
            raise RuntimeError("No active run.")

        run = self.current_run
        run.end_time = time.time()
        run.pass_at_1 = pass_at_1
        run.timing_closure = timing_closure

        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)

        # Save to history
        self._history.append(asdict(run))
        self._save_history()

        return run

    def get_summary(self, n_runs: Optional[int] = None) -> Dict:
        """Get summary statistics."""
        runs = self._history[-n_runs:] if n_runs else self._history

        if not runs:
            return {"message": "No runs recorded yet."}

        total_runs = len(runs)
        passed_runs = sum(1 for r in runs if r.get('pass_at_1'))
        timing_closed = sum(1 for r in runs if r.get('timing_closure'))

        return {
            "total_runs": total_runs,
            "pass_at_1_rate": passed_runs / total_runs,
            "timing_closure_rate": timing_closed / total_runs,
            "avg_duration": sum(r.get('duration', 0) for r in runs) / total_runs,
            "avg_tokens": sum(r.get('total_tokens', 0) for r in runs) / total_runs,
        }