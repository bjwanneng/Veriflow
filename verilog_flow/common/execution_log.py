"""Structured execution logging for VeriFlow pipeline runs."""

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project_layout import ProjectLayout


@dataclass
class StageLog:
    """Log entry for a single stage execution."""
    stage_num: int
    stage_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0


@dataclass
class RunLog:
    """Complete log for a pipeline run."""
    run_id: str
    project_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    stages: List[StageLog] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0


class ExecutionLogger:
    """Write structured JSON logs for each pipeline run."""

    def __init__(self, layout: ProjectLayout):
        self.layout = layout
        self._current_run: Optional[RunLog] = None
        self._current_stage: Optional[StageLog] = None

    def start_run(self, project_name: str) -> RunLog:
        """Begin a new pipeline run."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{ts}"
        self._current_run = RunLog(
            run_id=run_id,
            project_name=project_name,
            start_time=time.time(),
        )
        return self._current_run

    @contextmanager
    def stage(self, stage_num: int, stage_name: str):
        """Context manager that logs a stage execution.

        Usage::

            with logger.stage(3, "codegen") as slog:
                # ... do work ...
                slog.metrics["files_generated"] = 5
        """
        if not self._current_run:
            raise RuntimeError("No active run. Call start_run() first.")
        slog = StageLog(stage_num=stage_num, stage_name=stage_name,
                        start_time=time.time())
        self._current_stage = slog
        try:
            yield slog
            slog.success = True
        except Exception as exc:
            slog.success = False
            slog.error = str(exc)
            raise
        finally:
            slog.end_time = time.time()
            self._current_run.stages.append(slog)
            self._current_stage = None

    def end_run(self, success: bool) -> RunLog:
        """Finalize the current run and persist the log to disk."""
        if not self._current_run:
            raise RuntimeError("No active run.")
        run = self._current_run
        run.end_time = time.time()
        run.success = success
        self._save(run)
        self._current_run = None
        return run

    @property
    def current_run(self) -> Optional[RunLog]:
        return self._current_run

    # ── Retrieval ────────────────────────────────────────────────────

    def list_runs(self, n_recent: int = 0) -> List[RunLog]:
        """Load recent run logs from disk (newest first)."""
        logs_dir = self.layout.get_logs_dir()
        if not logs_dir.exists():
            return []
        files = sorted(logs_dir.glob("run_*.json"), reverse=True)
        if n_recent > 0:
            files = files[:n_recent]
        runs: List[RunLog] = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                stages = [StageLog(**s) for s in data.pop("stages", [])]
                runs.append(RunLog(**data, stages=stages))
            except Exception:
                continue
        return runs

    # ── Persistence ──────────────────────────────────────────────────

    def _save(self, run: RunLog) -> Path:
        logs_dir = self.layout.get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        path = logs_dir / f"{run.run_id}.json"
        path.write_text(json.dumps(asdict(run), indent=2, default=str),
                        encoding="utf-8")
        return path
