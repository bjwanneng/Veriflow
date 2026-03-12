"""Project directory layout management for VeriFlow."""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class StageDir:
    """Descriptor for a stage subdirectory."""
    name: str
    stage: int
    description: str
    subdirs: List[str] = field(default_factory=list)


# Canonical stage directory definitions
STAGE_DIRS: Dict[int, dict] = {
    1: {
        "dir_name": "stage_1_spec",
        "children": {
            "specs": StageDir("specs", 1, "Micro-architecture spec JSON files"),
        },
    },
    2: {
        "dir_name": "stage_2_timing",
        "children": {
            "scenarios": StageDir("scenarios", 2, "YAML timing scenarios"),
            "golden_traces": StageDir("golden_traces", 2, "Golden reference traces"),
            "waveforms": StageDir("waveforms", 2, "WaveDrom HTML waveforms"),
        },
    },
    3: {
        "dir_name": "stage_3_codegen",
        "children": {
            "rtl": StageDir("rtl", 3, "Generated RTL code",
                            subdirs=["common", "crypto", "tx", "rx"]),
        },
    },
    4: {
        "dir_name": "stage_4_sim",
        "children": {
            "tb": StageDir("tb", 4, "Testbench files"),
            "sim": StageDir("sim", 4, "Simulation outputs"),
        },
    },
    5: {
        "dir_name": "stage_5_synth",
        "children": {
            "synth": StageDir("synth", 5, "Per-module synthesis results"),
        },
    },
}

# Legacy directory names that may exist in older projects
_LEGACY_MAP = {
    "specs": (1, "specs"),
    "scenarios": (2, "scenarios"),
    "golden_traces": (2, "golden_traces"),
    "waveforms": (2, "waveforms"),
    "rtl": (3, "rtl"),
    "tb": (4, "tb"),
    "sim": (4, "sim"),
    "synth": (5, "synth"),
}


class ProjectLayout:
    """Manage the standard VeriFlow project directory layout."""

    METADATA_DIR = ".veriflow"
    REPORTS_DIR = "reports"

    def __init__(self, project_root: Path):
        self.root = Path(project_root).resolve()

    # ── Path accessors ──────────────────────────────────────────────

    def get_stage_root(self, stage: int) -> Path:
        """Return the root directory for a given stage, e.g. project/stage_3_codegen/."""
        if stage not in STAGE_DIRS:
            raise ValueError(f"Unknown stage {stage}. Valid: 1-5")
        return self.root / STAGE_DIRS[stage]["dir_name"]

    def get_dir(self, stage: int, key: str) -> Path:
        """Return a specific subdirectory, e.g. project/stage_3_codegen/rtl/."""
        stage_info = STAGE_DIRS.get(stage)
        if not stage_info:
            raise ValueError(f"Unknown stage {stage}")
        child = stage_info["children"].get(key)
        if not child:
            raise ValueError(f"Unknown key '{key}' for stage {stage}")
        return self.get_stage_root(stage) / child.name

    def get_metadata_dir(self) -> Path:
        return self.root / self.METADATA_DIR

    def get_logs_dir(self) -> Path:
        return self.get_metadata_dir() / "logs"

    def get_experience_dir(self) -> Path:
        return self.get_metadata_dir() / "experience_db"

    def get_reports_dir(self) -> Path:
        return self.root / self.REPORTS_DIR

    def get_coding_style_dir(self, vendor: str = "generic") -> Path:
        return self.get_metadata_dir() / "coding_style" / vendor

    def get_templates_dir(self, vendor: str = "generic") -> Path:
        return self.get_metadata_dir() / "templates" / vendor

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self, stages: Optional[List[int]] = None) -> None:
        """Create the full standard directory tree (or a subset of stages)."""
        target_stages = stages or list(STAGE_DIRS.keys())

        for stage_num in target_stages:
            stage_info = STAGE_DIRS[stage_num]
            for child in stage_info["children"].values():
                child_path = self.get_stage_root(stage_num) / child.name
                child_path.mkdir(parents=True, exist_ok=True)
                for sub in child.subdirs:
                    (child_path / sub).mkdir(parents=True, exist_ok=True)

        # Metadata directories
        self.get_logs_dir().mkdir(parents=True, exist_ok=True)
        self.get_experience_dir().mkdir(parents=True, exist_ok=True)
        self.get_reports_dir().mkdir(parents=True, exist_ok=True)

        # Coding style & template dirs for all vendors
        for vendor in ("generic", "xilinx", "intel"):
            self.get_coding_style_dir(vendor).mkdir(parents=True, exist_ok=True)
            self.get_templates_dir(vendor).mkdir(parents=True, exist_ok=True)

    def clean_stage(self, stage: int) -> None:
        """Remove all generated files for a given stage."""
        stage_root = self.get_stage_root(stage)
        if stage_root.exists():
            shutil.rmtree(stage_root)

    def migrate_legacy(self) -> List[str]:
        """Move files from legacy flat directories into the new layout.

        Returns a list of migration actions performed.
        """
        actions: List[str] = []
        for legacy_name, (stage, key) in _LEGACY_MAP.items():
            legacy_path = self.root / legacy_name
            if not legacy_path.exists() or not legacy_path.is_dir():
                continue
            target = self.get_dir(stage, key)
            target.mkdir(parents=True, exist_ok=True)
            for item in legacy_path.iterdir():
                dest = target / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
                    actions.append(f"Moved {legacy_path.name}/{item.name} -> {target.relative_to(self.root)}/{item.name}")
            # Remove empty legacy dir
            if not any(legacy_path.iterdir()):
                legacy_path.rmdir()
                actions.append(f"Removed empty legacy dir: {legacy_name}/")
        return actions