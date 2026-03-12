"""Coding style management for RTL generation."""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .project_layout import ProjectLayout

# Package-level defaults directory (shipped with the repo)
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULTS_DIR = _PACKAGE_ROOT / "defaults"


@dataclass
class CodingStyleRule:
    """A single coding-style rule."""
    rule_id: str
    category: str          # naming, reset, clock, coding, structure
    description: str
    example_good: str
    example_bad: str
    severity: str = "recommended"  # required | recommended | optional


@dataclass
class LintIssue:
    """A coding-style violation found during validation."""
    rule_id: str
    line: int
    message: str
    severity: str


@dataclass
class CodingStyle:
    """Complete coding-style definition for a vendor target."""
    vendor: str
    rules: List[CodingStyleRule] = field(default_factory=list)
    naming: Dict[str, str] = field(default_factory=dict)
    reset_style: str = "async_active_low"
    clock_edge: str = "posedge"
    indent: int = 4
    max_line_length: int = 120


# ── Built-in vendor presets ──────────────────────────────────────────

def _generic_style() -> CodingStyle:
    return CodingStyle(
        vendor="generic",
        rules=[
            CodingStyleRule("NAMING_MODULE", "naming",
                            "Module names use snake_case",
                            "aes_cipher_top", "AESCipherTop", "required"),
            CodingStyleRule("NAMING_SIGNAL", "naming",
                            "Signal names use snake_case",
                            "data_valid", "dataValid", "required"),
            CodingStyleRule("NAMING_PARAM", "naming",
                            "Parameters use UPPER_CASE",
                            "DATA_WIDTH", "dataWidth", "required"),
            CodingStyleRule("RESET_ASYNC_LOW", "reset",
                            "Use asynchronous active-low reset (rst_n)",
                            "always @(posedge clk or negedge rst_n)",
                            "always @(posedge clk or posedge rst)", "recommended"),
            CodingStyleRule("INDENT_4", "coding",
                            "Use 4-space indentation",
                            "    if (en)", "  if (en)", "recommended"),
        ],
        naming={"module": "snake_case", "signal": "snake_case",
                "parameter": "UPPER_CASE", "localparam": "UPPER_CASE"},
        reset_style="async_active_low",
        clock_edge="posedge",
        indent=4,
        max_line_length=120,
    )


def _xilinx_style() -> CodingStyle:
    return CodingStyle(
        vendor="xilinx",
        rules=[
            CodingStyleRule("NAMING_MODULE", "naming",
                            "Module names use snake_case (UG901)",
                            "axi_bram_ctrl", "AXI_BRAM_CTRL", "required"),
            CodingStyleRule("NAMING_SIGNAL", "naming",
                            "Signal names use snake_case",
                            "wr_data", "wrData", "required"),
            CodingStyleRule("NAMING_PARAM", "naming",
                            "Parameters use UPPER_CASE",
                            "C_DATA_WIDTH", "data_width", "required"),
            CodingStyleRule("RESET_SYNC_HIGH", "reset",
                            "Xilinx recommends synchronous active-high reset for better FPGA utilization",
                            "always @(posedge clk) if (rst)",
                            "always @(posedge clk or negedge rst_n)", "recommended"),
            CodingStyleRule("BRAM_INFER", "structure",
                            "Use recommended BRAM inference template (UG901)",
                            "reg [W-1:0] mem [0:D-1]; always @(posedge clk) ...",
                            "Unstructured memory access", "recommended"),
        ],
        naming={"module": "snake_case", "signal": "snake_case",
                "parameter": "C_UPPER_CASE", "localparam": "UPPER_CASE"},
        reset_style="sync_active_high",
        clock_edge="posedge",
        indent=4,
        max_line_length=120,
    )


def _intel_style() -> CodingStyle:
    return CodingStyle(
        vendor="intel",
        rules=[
            CodingStyleRule("NAMING_MODULE", "naming",
                            "Module names use snake_case",
                            "avalon_mm_slave", "AvalonMMSlave", "required"),
            CodingStyleRule("NAMING_SIGNAL", "naming",
                            "Signal names use snake_case",
                            "read_data", "readData", "required"),
            CodingStyleRule("NAMING_PARAM", "naming",
                            "Parameters use UPPER_CASE",
                            "DATA_WIDTH", "dataWidth", "required"),
            CodingStyleRule("RESET_ASYNC_LOW", "reset",
                            "Intel FPGAs: async active-low reset for dedicated reset routing",
                            "always @(posedge clk or negedge rst_n)",
                            "always @(posedge clk) if (rst)", "recommended"),
            CodingStyleRule("BRAM_INFER", "structure",
                            "Use Intel recommended BRAM inference style",
                            "reg [W-1:0] mem [0:D-1]; always @(posedge clk) ...",
                            "Unstructured memory access", "recommended"),
        ],
        naming={"module": "snake_case", "signal": "snake_case",
                "parameter": "UPPER_CASE", "localparam": "UPPER_CASE"},
        reset_style="async_active_low",
        clock_edge="posedge",
        indent=3,
        max_line_length=120,
    )


_VENDOR_PRESETS = {
    "generic": _generic_style,
    "xilinx": _xilinx_style,
    "intel": _intel_style,
}


class CodingStyleManager:
    """Load, save, and apply coding styles.

    Coding style documentation is maintained as Markdown (.md) files in
    ``verilog_flow/defaults/coding_style/<vendor>/``.  These are the
    authoritative human-readable references.  Machine-readable parameters
    (reset style, indent, naming conventions) come from the built-in
    Python presets so that code generators can consume them directly.
    """

    def __init__(self, layout: ProjectLayout):
        self.layout = layout

    # ── Style loading ─────────────────────────────────────────────────

    def get_style(self, vendor: str = "generic") -> CodingStyle:
        """Return the machine-readable CodingStyle for *vendor*.

        Always resolved from the built-in Python presets.
        """
        factory = _VENDOR_PRESETS.get(vendor)
        if factory:
            return factory()
        raise ValueError(f"Unknown vendor '{vendor}'. Available: {self.list_vendors()}")

    def get_style_doc(self, vendor: str = "generic") -> Optional[str]:
        """Return the Markdown coding-style document for *vendor*.

        Resolution order:
        1. Project-local  ``.veriflow/coding_style/<vendor>/*.md``
        2. Package defaults  ``verilog_flow/defaults/coding_style/<vendor>/*.md``

        Returns the content of the first ``.md`` file found, or ``None``.
        """
        for base in (self.layout.get_coding_style_dir(vendor),
                     _DEFAULTS_DIR / "coding_style" / vendor):
            if base.is_dir():
                md_files = sorted(base.glob("*.md"))
                if md_files:
                    return md_files[0].read_text(encoding="utf-8")
        return None

    def get_template(self, name: str, vendor: str = "generic") -> Optional[str]:
        """Return the content of a ``.v`` template file.

        Resolution order:
        1. Project-local  ``.veriflow/templates/<vendor>/<name>.v``
        2. Package defaults  ``verilog_flow/defaults/templates/<vendor>/<name>.v``

        *name* should NOT include the ``.v`` extension.
        """
        filename = f"{name}.v"
        for base in (self.layout.get_templates_dir(vendor),
                     _DEFAULTS_DIR / "templates" / vendor):
            candidate = base / filename
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        return None

    def list_templates(self, vendor: str = "generic") -> List[str]:
        """Return available template names (without .v extension)."""
        names: set = set()
        for base in (self.layout.get_templates_dir(vendor),
                     _DEFAULTS_DIR / "templates" / vendor):
            if base.is_dir():
                for f in base.glob("*.v"):
                    names.add(f.stem)
        return sorted(names)

    def list_vendors(self) -> List[str]:
        """Return available vendor names (built-in + on-disk)."""
        vendors = set(_VENDOR_PRESETS.keys())
        for root in (self.layout.get_metadata_dir() / "coding_style",
                     _DEFAULTS_DIR / "coding_style"):
            if root.exists():
                for d in root.iterdir():
                    if d.is_dir():
                        vendors.add(d.name)
        return sorted(vendors)

    # ── Project initialisation ────────────────────────────────────────

    def initialize_defaults(self) -> None:
        """Copy default coding-style docs (.md) and templates (.v) into
        the project's ``.veriflow/`` directory.

        Source: ``verilog_flow/defaults/coding_style/`` and
        ``verilog_flow/defaults/templates/``.
        """
        # Copy coding_style .md files
        src_cs = _DEFAULTS_DIR / "coding_style"
        if src_cs.is_dir():
            for vendor_dir in src_cs.iterdir():
                if vendor_dir.is_dir():
                    dst = self.layout.get_coding_style_dir(vendor_dir.name)
                    dst.mkdir(parents=True, exist_ok=True)
                    for md_file in vendor_dir.glob("*.md"):
                        shutil.copy2(md_file, dst / md_file.name)

        # Copy template .v files
        src_tpl = _DEFAULTS_DIR / "templates"
        if src_tpl.is_dir():
            for vendor_dir in src_tpl.iterdir():
                if vendor_dir.is_dir():
                    dst = self.layout.get_templates_dir(vendor_dir.name)
                    dst.mkdir(parents=True, exist_ok=True)
                    for v_file in vendor_dir.glob("*.v"):
                        shutil.copy2(v_file, dst / v_file.name)

    # ── Validation ────────────────────────────────────────────────────

    def validate_code(self, code: str, style: CodingStyle) -> List[LintIssue]:
        """Run coding-style checks against generated RTL code."""
        issues: List[LintIssue] = []
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            # Line length
            if len(line) > style.max_line_length:
                issues.append(LintIssue(
                    "LINE_LENGTH", i,
                    f"Line exceeds {style.max_line_length} chars ({len(line)})",
                    "recommended"))
            # Indentation (skip blank / comment-only / preprocessor lines)
            stripped = line.lstrip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("`"):
                leading = len(line) - len(stripped)
                if leading > 0 and leading % style.indent != 0:
                    issues.append(LintIssue(
                        "INDENT", i,
                        f"Indentation ({leading}) not a multiple of {style.indent}",
                        "recommended"))

        # ── v3.2: Naming convention enforcement ──────────────────────
        naming = style.naming

        # Module name check
        if naming.get("module") == "snake_case":
            for i, line in enumerate(lines, 1):
                m = re.match(r'\s*module\s+(\w+)', line)
                if m:
                    name = m.group(1)
                    if name != name.lower() or re.search(r'[A-Z]', name):
                        issues.append(LintIssue(
                            "NAMING_MODULE", i,
                            f'Module name "{name}" is not snake_case',
                            "required"))

        # Signal name check (reg/wire declarations)
        if naming.get("signal") == "snake_case":
            sig_re = re.compile(
                r'\b(?:reg|wire|logic)\b\s+(?:signed\s+)?(?:\[[^\]]*\]\s+)?(\w+)')
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('//'):
                    continue
                for m in sig_re.finditer(stripped):
                    name = m.group(1)
                    if re.search(r'[A-Z]', name):
                        issues.append(LintIssue(
                            "NAMING_SIGNAL", i,
                            f'Signal "{name}" is not snake_case',
                            "required"))

        # Parameter name check
        param_style = naming.get("parameter", "UPPER_CASE")
        if "UPPER" in param_style:
            param_re = re.compile(r'\b(?:parameter|localparam)\b\s+(?:\[[^\]]*\]\s+)?(\w+)')
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('//'):
                    continue
                for m in param_re.finditer(stripped):
                    name = m.group(1)
                    if name != name.upper():
                        issues.append(LintIssue(
                            "NAMING_PARAM", i,
                            f'Parameter "{name}" is not UPPER_CASE',
                            "recommended"))

        return issues
