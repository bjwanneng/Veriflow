"""Experience database for storing and retrieving design patterns and failure cases."""

import json
import hashlib
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
from datetime import datetime


@dataclass
class DesignPattern:
    """A reusable design pattern from successful implementations."""
    pattern_id: str
    name: str
    description: str
    module_type: str  # e.g., "AXI Slave", "FIFO", "Arbiter"
    target_frequency_mhz: float

    # Design content
    micro_arch_spec: Dict[str, Any]
    yaml_template: str
    generated_verilog: Optional[str] = None

    # Metadata
    success_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)


@dataclass
class FailureCase:
    """A recorded failure case for learning."""
    case_id: str
    module_name: str
    target_frequency_mhz: float

    # Failure details
    stage: str  # Which stage failed (1.5, 2, 3, 4, 5)
    failure_type: str  # e.g., "timing_violation", "lint_error", "sim_mismatch"
    error_message: str

    # Context
    micro_arch_spec: Optional[Dict] = None
    generated_code: Optional[str] = None
    yosys_report: Optional[Dict] = None

    # Resolution
    resolved: bool = False
    resolution_notes: Optional[str] = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    run_id: Optional[str] = None


@dataclass
class Field:
    """Workaround for field default_factory in Python < 3.10"""
    pass




class ExperienceDB:
    """Experience database for design patterns and failure cases."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or Path(".veriflow/experience_db")
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.patterns_dir = self.db_path / "patterns"
        self.failures_dir = self.db_path / "failures"
        self.index_file = self.db_path / "index.json"

        self.patterns_dir.mkdir(exist_ok=True)
        self.failures_dir.mkdir(exist_ok=True)

        self._index = self._load_index()

    def _load_index(self) -> Dict:
        """Load the database index."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                return json.load(f)
        return {
            "patterns": {},
            "failures": {},
            "version": "1.0"
        }

    def _save_index(self):
        """Save the database index."""
        with open(self.index_file, 'w') as f:
            json.dump(self._index, f, indent=2)

    def _generate_id(self, content: str) -> str:
        """Generate a unique ID from content."""
        return hashlib.md5(content.encode()).hexdigest()[:12]

    # Pattern operations

    def save_pattern(self, pattern: DesignPattern) -> str:
        """Save a design pattern to the database."""
        pattern_file = self.patterns_dir / f"{pattern.pattern_id}.json"

        with open(pattern_file, 'w') as f:
            json.dump(asdict(pattern), f, indent=2)

        # Update index
        self._index["patterns"][pattern.pattern_id] = {
            "name": pattern.name,
            "module_type": pattern.module_type,
            "target_frequency_mhz": pattern.target_frequency_mhz,
            "tags": pattern.tags
        }
        self._save_index()

        return pattern.pattern_id

    def get_pattern(self, pattern_id: str) -> Optional[DesignPattern]:
        """Retrieve a design pattern by ID."""
        pattern_file = self.patterns_dir / f"{pattern_id}.json"

        if not pattern_file.exists():
            return None

        with open(pattern_file, 'r') as f:
            data = json.load(f)

        return DesignPattern(**data)

    def find_patterns(self, module_type: str = None,
                      min_frequency: float = None,
                      tags: List[str] = None) -> List[DesignPattern]:
        """Find patterns matching criteria."""
        results = []

        for pattern_id, meta in self._index["patterns"].items():
            # Apply filters
            if module_type and meta.get("module_type") != module_type:
                continue
            if min_frequency and meta.get("target_frequency_mhz", 0) < min_frequency:
                continue
            if tags and not any(t in meta.get("tags", []) for t in tags):
                continue

            pattern = self.get_pattern(pattern_id)
            if pattern:
                results.append(pattern)

        return results

    # Failure case operations

    def record_failure(self, case: FailureCase) -> str:
        """Record a failure case to the database."""
        # Generate ID if not provided
        if not case.case_id:
            content = f"{case.module_name}_{case.stage}_{case.failure_type}_{time.time()}"
            case.case_id = self._generate_id(content)

        case_file = self.failures_dir / f"{case.case_id}.json"

        with open(case_file, 'w') as f:
            json.dump(asdict(case), f, indent=2)

        # Update index
        self._index["failures"][case.case_id] = {
            "module_name": case.module_name,
            "stage": case.stage,
            "failure_type": case.failure_type,
            "resolved": case.resolved
        }
        self._save_index()

        return case.case_id

    def get_failure(self, case_id: str) -> Optional[FailureCase]:
        """Retrieve a failure case by ID."""
        case_file = self.failures_dir / f"{case_id}.json"

        if not case_file.exists():
            return None

        with open(case_file, 'r') as f:
            data = json.load(f)

        return FailureCase(**data)

    def find_similar_failures(self, module_name: str = None,
                              stage: str = None,
                              failure_type: str = None,
                              unresolved_only: bool = True) -> List[FailureCase]:
        """Find similar failure cases for learning."""
        results = []

        for case_id, meta in self._index["failures"].items():
            if unresolved_only and meta.get("resolved"):
                continue
            if module_name and meta.get("module_name") != module_name:
                continue
            if stage and meta.get("stage") != stage:
                continue
            if failure_type and meta.get("failure_type") != failure_type:
                continue

            case = self.get_failure(case_id)
            if case:
                results.append(case)

        return results

    def resolve_failure(self, case_id: str, resolution_notes: str):
        """Mark a failure case as resolved."""
        case = self.get_failure(case_id)
        if case:
            case.resolved = True
            case.resolution_notes = resolution_notes
            self.record_failure(case)

            # Update index
            if case_id in self._index["failures"]:
                self._index["failures"][case_id]["resolved"] = True
                self._save_index()