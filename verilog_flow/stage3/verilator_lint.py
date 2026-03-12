"""Verilator --lint-only wrapper for deep static analysis (Stage 3).

Provides a second lint layer that catches issues beyond regex-based checks:
- Precise bit-width mismatch warnings (-Wwidth)
- Unused signals/ports (-Wunused)
- Combinational loop detection (-Wcircular)
- Implicit type conversions
- Incomplete case coverage

Falls back gracefully if Verilator is not installed.
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..common.toolchain_detect import detect_toolchain

# Reuse LintIssue/LintResult from the main lint_checker
from .lint_checker import LintIssue, LintResult


# Map Verilator warning tags to severity
_VERILATOR_SEVERITY: Dict[str, str] = {
    "%Error": "error",
    "%Warning": "warning",
    "%Info": "info",
}


@dataclass
class VerilatorLintConfig:
    """Configuration for Verilator lint run."""
    # Warning flags to enable (empty = use Verilator defaults + -Wall)
    extra_flags: List[str] = field(default_factory=lambda: ["-Wall"])
    # Warning flags to suppress (e.g., ["-Wno-UNUSED", "-Wno-PINCONNECTEMPTY"])
    suppress_flags: List[str] = field(default_factory=list)
    # Top module name (required for multi-module designs)
    top_module: Optional[str] = None
    # Include directories
    include_dirs: List[Path] = field(default_factory=list)
    # Timeout in seconds
    timeout: int = 60
    # Language standard
    language: str = "1364-2005"  # Verilog-2005


class VerilatorLint:
    """Run Verilator in lint-only mode and parse results."""

    def __init__(self, config: Optional[VerilatorLintConfig] = None):
        self.config = config or VerilatorLintConfig()
        self._toolchain = detect_toolchain()
        self._env = self._toolchain.shell_env()
        verilator_info = self._toolchain.tools.get("verilator")
        self.available = verilator_info.available if verilator_info else False
        self.verilator_path = verilator_info.path if verilator_info else None
        self.version = verilator_info.version if verilator_info else None

    def check_files(self, verilog_files: List[Path],
                    top_module: Optional[str] = None) -> LintResult:
        """Run verilator --lint-only on a list of Verilog files.

        Returns a merged LintResult. If Verilator is not installed,
        returns an empty result with an info-level notice.
        """
        file_str = ", ".join(str(f) for f in verilog_files[:3])
        result = LintResult(file_path=file_str)

        if not self.available:
            result.issues.append(LintIssue(
                severity='info',
                rule_id='VERILATOR_NOT_FOUND',
                message='Verilator not installed — deep lint skipped. '
                        'Install: apt install verilator / brew install verilator / choco install verilator',
                line_number=0,
                suggestion='Install Verilator for deeper static analysis (bit-width, unused signals, loops)',
            ))
            return result

        # Build command
        cmd = [self.verilator_path, "--lint-only"]
        cmd.append(f"--language {self.config.language}")
        cmd.extend(self.config.extra_flags)
        cmd.extend(self.config.suppress_flags)

        top = top_module or self.config.top_module
        if top:
            cmd.extend(["--top-module", top])

        for inc_dir in self.config.include_dirs:
            cmd.extend(["-I", str(inc_dir)])

        for vf in verilog_files:
            cmd.append(str(vf))

        # Run
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=self._env,
            )
            # Verilator outputs warnings/errors to stderr
            output = proc.stderr + proc.stdout
            result.issues.extend(self._parse_output(output))

        except subprocess.TimeoutExpired:
            result.issues.append(LintIssue(
                severity='error',
                rule_id='VERILATOR_TIMEOUT',
                message=f'Verilator timed out after {self.config.timeout}s',
                line_number=0,
                suggestion='Increase timeout or simplify the design',
            ))
        except OSError as e:
            result.issues.append(LintIssue(
                severity='error',
                rule_id='VERILATOR_EXEC_ERROR',
                message=f'Failed to run Verilator: {e}',
                line_number=0,
            ))

        return result

    def check_file(self, file_path: Path,
                   top_module: Optional[str] = None) -> LintResult:
        """Convenience: lint a single file."""
        if not file_path.exists():
            result = LintResult(file_path=str(file_path))
            result.issues.append(LintIssue(
                severity='error',
                rule_id='FILE_NOT_FOUND',
                message=f'File does not exist: {file_path}',
                line_number=0,
            ))
            return result
        return self.check_files([file_path], top_module=top_module)

    def _parse_output(self, output: str) -> List[LintIssue]:
        """Parse Verilator stderr output into LintIssue list.

        Verilator output format:
            %Warning-UNUSED: file.v:10:5: Signal is not used: 'foo'
            %Error: file.v:20:3: Cannot find: 'bar'
            %Warning-WIDTH: file.v:30:10: Operator ASSIGN expects 8 bits ...
        """
        issues = []
        # Pattern: %Warning-TAG: file:line:col: message
        #      or: %Error: file:line:col: message
        pattern = re.compile(
            r'%(Error|Warning)(?:-(\w+))?:\s*'  # severity + optional tag
            r'([^:]+):(\d+):(?:(\d+):)?\s*'     # file:line:col (col optional)
            r'(.+)'                               # message
        )

        for line in output.split('\n'):
            m = pattern.match(line.strip())
            if not m:
                continue

            sev_str = m.group(1)  # "Error" or "Warning"
            tag = m.group(2) or ""  # e.g., "UNUSED", "WIDTH", ""
            file_name = m.group(3)
            line_num = int(m.group(4))
            col = int(m.group(5)) if m.group(5) else 0
            message = m.group(6).strip()

            severity = "error" if sev_str == "Error" else "warning"
            rule_id = f"VERILATOR_{tag}" if tag else "VERILATOR_ERROR"

            issues.append(LintIssue(
                severity=severity,
                rule_id=rule_id,
                message=message,
                line_number=line_num,
                column=col,
                suggestion=_suggest_fix(tag, message),
            ))

        return issues


def _suggest_fix(tag: str, message: str) -> str:
    """Provide fix suggestions for common Verilator warnings."""
    suggestions = {
        "UNUSED": "Remove the unused signal, or prefix with /* verilator lint_off UNUSED */",
        "UNDRIVEN": "Ensure the signal is driven, or tie it to a default value",
        "WIDTH": "Check bit-width on both sides of the assignment; use explicit slicing or zero-extension",
        "CASEINCOMPLETE": "Add a default branch to the case statement",
        "COMBDLY": "Do not use non-blocking (<=) in combinational always blocks; use blocking (=)",
        "BLKSEQ": "Do not use blocking (=) in sequential always blocks; use non-blocking (<=)",
        "PINCONNECTEMPTY": "Connect the port or explicitly leave unconnected with .port()",
        "CIRCULAR": "Break the combinational loop by inserting a register",
        "MULTIDRIVEN": "Ensure each signal has exactly one driver",
        "LATCH": "Add a default assignment at the top of the combinational block",
        "IMPLICIT": "Declare the signal explicitly as wire or reg",
    }
    return suggestions.get(tag, "")
