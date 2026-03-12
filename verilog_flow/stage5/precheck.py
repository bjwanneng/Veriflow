"""Synthesizability pre-check using Yosys (Stage 5).

Runs a lightweight read_verilog + hierarchy + proc pass to catch
syntax errors and multi-driver issues without a full synthesis.
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .yosys_interface import YosysInterface


@dataclass
class PrecheckResult:
    """Result of synthesizability pre-check."""

    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def check_synthesizability(
    verilog_files: List[Path],
    top_module: str,
    yosys: Optional[YosysInterface] = None,
) -> PrecheckResult:
    """Quick synthesizability check via Yosys (read + hierarchy + proc).

    This does NOT run full synthesis — it only checks that the design
    can be parsed, elaborated, and converted from processes to netlists
    without errors.
    """
    if yosys is None:
        yosys = YosysInterface()

    if not yosys.available:
        return PrecheckResult(
            success=False,
            errors=[yosys.install_hint()],
        )

    # Build a minimal Yosys script
    lines = [
        "# Synthesizability pre-check",
    ]
    for vf in verilog_files:
        lines.append(f"read_verilog {vf}")
    lines += [
        f"hierarchy -top {top_module}",
        "proc",
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ys", delete=False, encoding="utf-8"
    ) as f:
        f.write("\n".join(lines))
        script_path = f.name

    try:
        result = subprocess.run(
            ["yosys", script_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return PrecheckResult(success=False, errors=["Pre-check timed out (60s)"])
    except Exception as e:
        return PrecheckResult(success=False, errors=[str(e)])
    finally:
        Path(script_path).unlink(missing_ok=True)

    combined = result.stdout + result.stderr
    errors: List[str] = []
    warnings: List[str] = []

    for line in combined.split("\n"):
        stripped = line.strip()
        if "ERROR" in stripped or "error:" in stripped.lower():
            errors.append(stripped)
        elif "Warning" in stripped or "warning:" in stripped.lower():
            warnings.append(stripped)

    if result.returncode != 0 and not errors:
        errors.append(f"Yosys exited with code {result.returncode}")

    return PrecheckResult(
        success=(result.returncode == 0 and len(errors) == 0),
        errors=errors,
        warnings=warnings,
    )
