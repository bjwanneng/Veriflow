"""
Stage 3.5 Enhanced: Skill D with Calibration Mechanism.

Implements the full Stage 3 & 3.5 requirements from original design:
- Three-paradigm enforcement (combinational/sequential separation)
- Skill D1: Logic depth estimation with budget comparison
- Skill D2: CDC analysis with naming/clock constraint awareness
- Calibration mechanism: Skill D results vs Stage 5 synthesis data
- Error model iterative updates
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum
from pathlib import Path
from datetime import datetime


class LogicDepthCategory(Enum):
    """Categories of logic depth for budgeting."""
    VERY_SHALLOW = "very_shallow"  # 1-3 levels
    SHALLOW = "shallow"            # 4-6 levels
    MEDIUM = "medium"              # 7-10 levels
    DEEP = "deep"                  # 11-15 levels
    VERY_DEEP = "very_deep"        # 16+ levels


@dataclass
class LogicDepthEstimate:
    """Result of logic depth estimation for a signal path."""
    signal_name: str
    start_point: str
    end_point: str
    estimated_depth: int
    budgeted_depth: int
    exceeds_budget: bool = False
    gate_count: int = 0
    gate_types: List[str] = field(default_factory=list)
    estimated_delay_ns: float = 0.0
    line_number: int = 0
    suggested_fix: str = ""

    @property
    def margin(self) -> int:
        return self.budgeted_depth - self.estimated_depth

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "start_point": self.start_point,
            "end_point": self.end_point,
            "estimated_depth": self.estimated_depth,
            "budgeted_depth": self.budgeted_depth,
            "exceeds_budget": self.exceeds_budget,
            "margin": self.margin,
            "gate_count": self.gate_count,
            "gate_types": self.gate_types,
            "estimated_delay_ns": self.estimated_delay_ns,
            "line_number": self.line_number,
            "suggested_fix": self.suggested_fix
        }


@dataclass
class CDCCrossingEnhanced:
    """Enhanced CDC crossing with naming convention awareness."""
    source_clock: str
    dest_clock: str
    signal_name: str
    has_synchronizer: bool = False
    synchronizer_stages: int = 0
    follows_naming_convention: bool = False
    has_clock_constraint: bool = False
    line_number: int = 0
    crossing_type: str = "unknown"  # "data", "control", "status"
    severity: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_clock": self.source_clock,
            "dest_clock": self.dest_clock,
            "signal_name": self.signal_name,
            "has_synchronizer": self.has_synchronizer,
            "synchronizer_stages": self.synchronizer_stages,
            "follows_naming_convention": self.follows_naming_convention,
            "has_clock_constraint": self.has_clock_constraint,
            "line_number": self.line_number,
            "crossing_type": self.crossing_type,
            "severity": self.severity
        }


@dataclass
class ErrorModelPoint:
    """A single calibration point for the error model."""
    run_id: str
    estimated_depth: int
    actual_depth: int  # From Stage 5 synthesis
    estimated_delay_ns: float
    actual_delay_ns: float  # From Stage 5 timing report
    module_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def depth_error(self) -> int:
        return self.actual_depth - self.estimated_depth

    @property
    def delay_error_ns(self) -> float:
        return self.actual_delay_ns - self.estimated_delay_ns

    @property
    def depth_error_ratio(self) -> float:
        if self.estimated_depth > 0:
            return self.depth_error / self.estimated_depth
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "estimated_depth": self.estimated_depth,
            "actual_depth": self.actual_depth,
            "estimated_delay_ns": self.estimated_delay_ns,
            "actual_delay_ns": self.actual_delay_ns,
            "depth_error": self.depth_error,
            "delay_error_ns": self.delay_error_ns,
            "depth_error_ratio": self.depth_error_ratio,
            "module_name": self.module_name,
            "timestamp": self.timestamp
        }


@dataclass
class CalibratedErrorModel:
    """Iteratively updated error model for Skill D calibration."""
    model_id: str = "default"
    points: List[ErrorModelPoint] = field(default_factory=list)
    average_depth_error: float = 0.0
    average_delay_error_ns: float = 0.0
    depth_correction_factor: float = 1.0
    delay_correction_factor: float = 1.0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_point(self, point: ErrorModelPoint):
        """Add a calibration point and update model."""
        self.points.append(point)
        self._update_model()
        self.last_updated = datetime.now().isoformat()

    def _update_model(self):
        """Update the error model based on collected points."""
        if not self.points:
            return

        n = len(self.points)
        self.average_depth_error = sum(p.depth_error for p in self.points) / n
        self.average_delay_error_ns = sum(p.delay_error_ns for p in self.points) / n

        # Calculate correction factors (using average error ratio)
        depth_ratios = [p.depth_error_ratio for p in self.points if p.estimated_depth > 0]
        if depth_ratios:
            avg_ratio = sum(depth_ratios) / len(depth_ratios)
            self.depth_correction_factor = 1.0 + avg_ratio

        # Simple linear correction for delay
        if self.average_delay_error_ns != 0:
            self.delay_correction_factor = 1.0 + (self.average_delay_error_ns / 10.0)  # Normalize

    def apply_depth_correction(self, estimated_depth: int) -> int:
        """Apply correction to estimated depth."""
        corrected = int(estimated_depth * self.depth_correction_factor)
        return max(1, corrected)

    def apply_delay_correction(self, estimated_delay_ns: float) -> float:
        """Apply correction to estimated delay."""
        return estimated_delay_ns * self.delay_correction_factor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "point_count": len(self.points),
            "average_depth_error": self.average_depth_error,
            "average_delay_error_ns": self.average_delay_error_ns,
            "depth_correction_factor": self.depth_correction_factor,
            "delay_correction_factor": self.delay_correction_factor,
            "last_updated": self.last_updated,
            "recent_points": [p.to_dict() for p in self.points[-10:]]  # Last 10
        }

    def save(self, output_path: Path):
        """Save model to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, input_path: Path) -> 'CalibratedErrorModel':
        """Load model from JSON file."""
        with open(input_path, 'r') as f:
            data = json.load(f)
        model = cls(model_id=data.get("model_id", "default"))
        model.average_depth_error = data.get("average_depth_error", 0.0)
        model.average_delay_error_ns = data.get("average_delay_error_ns", 0.0)
        model.depth_correction_factor = data.get("depth_correction_factor", 1.0)
        model.delay_correction_factor = data.get("delay_correction_factor", 1.0)
        model.last_updated = data.get("last_updated", "")
        return model


class ThreeParadigmChecker:
    """
    Enforces the three-paradigm coding style:
    - Combinational logic and sequential logic completely separated
    """

    def __init__(self):
        self.issues: List[Dict[str, Any]] = []

    def check_file(self, verilog_code: str, file_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Check a Verilog file for three-paradigm compliance."""
        self.issues = []
        lines = verilog_code.split('\n')

        # Find always blocks
        always_blocks = self._extract_always_blocks(verilog_code)

        for block in always_blocks:
            self._check_always_block(block, lines)

        # Check for mixed blocking/non-blocking in same block
        self._check_mixed_assignments(verilog_code)

        return self.issues

    def _extract_always_blocks(self, code: str) -> List[Dict[str, Any]]:
        """Extract always blocks from code."""
        blocks = []
        pattern = r'always\s*(?:@\s*\([^)]*\))?\s*(.*?)(?=always\s|endmodule\b|$)'
        for match in re.finditer(pattern, code, re.DOTALL):
            start_line = code[:match.start()].count('\n') + 1
            blocks.append({
                "content": match.group(0),
                "start_line": start_line,
                "body": match.group(1)
            })
        return blocks

    def _check_always_block(self, block: Dict[str, Any], lines: List[str]):
        """Check an always block for paradigm compliance."""
        content = block["content"]
        line_num = block["start_line"]

        # Determine if it's sequential (posedge/negedge) or combinational (*)
        is_sequential = 'posedge' in content or 'negedge' in content
        is_combinational = '@(*)' in content or '@*' in content

        # Check blocking assignments in sequential blocks
        if is_sequential:
            # Should use non-blocking assignments (<=)
            blocking_matches = re.finditer(r'(\w+)\s*=\s*[^;]+;', block["body"])
            for m in blocking_matches:
                # Skip if it's inside a function/task or initial block
                self.issues.append({
                    "type": "blocking_in_sequential",
                    "line": line_num + block["body"][:m.start()].count('\n'),
                    "message": "Blocking assignment (=) in sequential always block - should use non-blocking (<=)",
                    "severity": "error"
                })

        # Check non-blocking assignments in combinational blocks
        if is_combinational:
            # Should use blocking assignments (=)
            non_blocking_matches = re.finditer(r'(\w+)\s*<=\s*[^;]+;', block["body"])
            for m in non_blocking_matches:
                self.issues.append({
                    "type": "non_blocking_in_combinational",
                    "line": line_num + block["body"][:m.start()].count('\n'),
                    "message": "Non-blocking assignment (<=) in combinational always block - should use blocking (=)",
                    "severity": "error"
                })

    def _check_mixed_assignments(self, code: str):
        """Check for signals driven by both always blocks and continuous assignments."""
        # Find all signals assigned in always blocks
        always_assigned = set()
        for match in re.finditer(r'(\w+)\s*[=<>]=\s*[^;]+;', code):
            always_assigned.add(match.group(1))

        # Find all signals in continuous assignments
        continuous_assigned = set()
        for match in re.finditer(r'assign\s+(\w+)', code):
            continuous_assigned.add(match.group(1))

        # Check for overlap
        overlap = always_assigned & continuous_assigned
        for signal in overlap:
            # Find line numbers
            line_num = code[:code.find(f"assign {signal}")].count('\n') + 1
            self.issues.append({
                "type": "mixed_drivers",
                "line": line_num,
                "message": f"Signal '{signal}' driven by both always block and continuous assignment",
                "severity": "error"
            })


class SkillDEnhanced:
    """
    Enhanced Skill D analyzer with calibration support.

    Features:
    - Logic depth estimation with budget comparison
    - CDC analysis with naming convention awareness
    - Calibration mechanism using Stage 5 synthesis data
    - Iterative error model updates
    """

    # CDC naming conventions
    CDC_SIGNAL_PATTERNS = [
        r'^sync_\w+',      # sync_* prefix
        r'\w+_sync$',      # *_sync suffix
        r'^cdc_\w+',       # cdc_* prefix
        r'\w+_cdc$',       # *_cdc suffix
        r'^meta_\w+',      # meta_* prefix (metastability)
        r'\w+_meta$',      # *_meta suffix
    ]

    def __init__(self, error_model: Optional[CalibratedErrorModel] = None):
        self.error_model = error_model or CalibratedErrorModel()
        self.depth_estimates: List[LogicDepthEstimate] = []
        self.cdc_crossings: List[CDCCrossingEnhanced] = []
        self.three_paradigm_issues: List[Dict[str, Any]] = []

    def analyze_logic_depth_with_budget(
        self,
        verilog_code: str,
        budgeted_depth: int = 12,
        target_frequency_mhz: float = 200.0
    ) -> List[LogicDepthEstimate]:
        """
        Analyze logic depth and compare against budget.

        Args:
            verilog_code: Verilog source code
            budgeted_depth: Maximum allowed logic levels
            target_frequency_mhz: Target frequency for delay estimation

        Returns:
            List of depth estimates with budget comparison
        """
        self.depth_estimates = []
        clock_period_ns = 1000.0 / target_frequency_mhz
        gate_delay_ns = clock_period_ns / budgeted_depth if budgeted_depth > 0 else 0.5

        # Analyze continuous assignments
        assign_pattern = r'assign\s+(\w+)\s*=\s*([^;]+);'
        for match in re.finditer(assign_pattern, verilog_code):
            signal = match.group(1)
            expression = match.group(2)
            line_num = verilog_code[:match.start()].count('\n') + 1

            depth = self._estimate_expression_depth(expression)

            # Apply error model correction if available
            corrected_depth = self.error_model.apply_depth_correction(depth)

            estimated_delay = corrected_depth * gate_delay_ns
            corrected_delay = self.error_model.apply_delay_correction(estimated_delay)

            estimate = LogicDepthEstimate(
                signal_name=signal,
                start_point=signal,
                end_point=signal,
                estimated_depth=corrected_depth,
                budgeted_depth=budgeted_depth,
                exceeds_budget=corrected_depth > budgeted_depth,
                estimated_delay_ns=corrected_delay,
                line_number=line_num
            )

            if estimate.exceeds_budget:
                estimate.suggested_fix = self._suggest_depth_fix(
                    corrected_depth, budgeted_depth, signal
                )

            self.depth_estimates.append(estimate)

        return self.depth_estimates

    def _estimate_expression_depth(self, expression: str) -> int:
        """Estimate logic depth from expression (enhanced)."""
        expression = expression.strip()
        if not expression:
            return 0

        # Count operators
        operators = len(re.findall(r'[&|^~+\-*/%]|==|!=|<|>|<=|>=|&&|\|\|', expression))

        # Count nested parentheses
        max_paren_depth = 0
        current_depth = 0
        for char in expression:
            if char == '(':
                current_depth += 1
                max_paren_depth = max(max_paren_depth, current_depth)
            elif char == ')':
                current_depth -= 1

        # Count conditionals (?:)
        conditionals = expression.count('?')

        # Enhanced heuristic
        estimated_depth = max(operators, max_paren_depth) + conditionals * 2

        # Add penalty for mux structures
        if '?' in expression or 'case' in expression.lower():
            estimated_depth += 1

        return max(1, estimated_depth)

    def _suggest_depth_fix(self, depth: int, budget: int, signal: str) -> str:
        """Suggest a fix for exceeding depth budget."""
        excess = depth - budget
        if excess <= 2:
            return f"考虑重新排列操作数顺序，或添加一级流水线寄存器"
        elif excess <= 5:
            return f"建议插入流水线寄存器分割该路径，或使用carry chain优化"
        else:
            return f"需要多级流水线分割，或重新考虑微架构"

    def analyze_cdc_enhanced(
        self,
        verilog_code: str,
        clock_constraints: Optional[Dict[str, Any]] = None
    ) -> List[CDCCrossingEnhanced]:
        """
        Enhanced CDC analysis with naming convention awareness.

        Args:
            verilog_code: Verilog source code
            clock_constraints: Optional clock domain constraints

        Returns:
            List of enhanced CDC crossings
        """
        self.cdc_crossings = []

        # Find all clock signals
        clocks = self._find_clocks(verilog_code)

        if len(clocks) < 2:
            return self.cdc_crossings  # No CDC possible

        # Find always blocks and their clock domains
        always_blocks = self._find_always_blocks(verilog_code)

        # Track which signals are in which domain
        signal_domains: Dict[str, Set[str]] = {}
        for block in always_blocks:
            clock = block.get('clock', 'unknown')
            for sig in block.get('assigned_signals', set()):
                if sig not in signal_domains:
                    signal_domains[sig] = set()
                signal_domains[sig].add(clock)

        # Identify cross-domain signals
        for signal, domains in signal_domains.items():
            if len(domains) > 1:
                domain_list = sorted(domains)
                for i in range(len(domain_list) - 1):
                    crossing = CDCCrossingEnhanced(
                        source_clock=domain_list[i],
                        dest_clock=domain_list[i + 1],
                        signal_name=signal,
                        line_number=self._find_signal_line(verilog_code, signal)
                    )

                    # Check naming conventions
                    crossing.follows_naming_convention = any(
                        re.search(pat, signal, re.IGNORECASE)
                        for pat in self.CDC_SIGNAL_PATTERNS
                    )

                    # Check for synchronizer
                    crossing.has_synchronizer = self._check_synchronizer(verilog_code, signal)
                    if crossing.has_synchronizer:
                        crossing.synchronizer_stages = self._count_sync_stages(verilog_code, signal)

                    # Check clock constraints
                    if clock_constraints:
                        key = (crossing.source_clock, crossing.dest_clock)
                        crossing.has_clock_constraint = key in clock_constraints

                    # Determine severity
                    if not crossing.has_synchronizer and not crossing.follows_naming_convention:
                        crossing.severity = "error"
                    elif not crossing.has_synchronizer:
                        crossing.severity = "warning"
                    else:
                        crossing.severity = "info"

                    self.cdc_crossings.append(crossing)

        # Also look for sync-named signals (may be safe CDC)
        for pattern in self.CDC_SIGNAL_PATTERNS:
            for match in re.finditer(pattern, verilog_code, re.IGNORECASE):
                signal = match.group(0)
                if not any(c.signal_name == signal for c in self.cdc_crossings):
                    # Add as informational
                    crossing = CDCCrossingEnhanced(
                        source_clock="unknown",
                        dest_clock="unknown",
                        signal_name=signal,
                        has_synchronizer=True,
                        follows_naming_convention=True,
                        severity="info",
                        line_number=verilog_code[:match.start()].count('\n') + 1
                    )
                    self.cdc_crossings.append(crossing)

        return self.cdc_crossings

    def _find_clocks(self, code: str) -> List[str]:
        """Find clock signals in code."""
        clocks = []
        patterns = [
            r'input\s+(?:wire\s+)?(?:clk|clock)\w*',
            r'input\s+(?:wire\s+)?\w+_clk\w*',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                parts = match.group(0).split()
                for part in parts:
                    if 'clk' in part.lower() or 'clock' in part.lower():
                        clk_name = re.sub(r'[^\w]', '', part)
                        if clk_name and clk_name not in clocks:
                            clocks.append(clk_name)
        return clocks

    def _find_always_blocks(self, code: str) -> List[Dict[str, Any]]:
        """Find always blocks and their clock domains."""
        blocks = []
        pattern = r'always\s*@\s*\(([^)]+)\)(.*?)(?=always\s|endmodule\b|$)'
        for match in re.finditer(pattern, code, re.DOTALL):
            sensitivity = match.group(1)
            body = match.group(2)

            clock = "unknown"
            clk_match = re.search(r'(posedge|negedge)\s+(\w+)', sensitivity, re.IGNORECASE)
            if clk_match:
                clock = clk_match.group(2)

            assigned_signals = set()
            for assign_match in re.finditer(r'(\w+)\s*<[=]=', body):
                assigned_signals.add(assign_match.group(1))

            blocks.append({
                "clock": clock,
                "assigned_signals": assigned_signals
            })
        return blocks

    def _check_synchronizer(self, code: str, signal: str) -> bool:
        """Check if a signal has a synchronizer."""
        patterns = [
            rf'{signal}\s*_sync',
            rf'sync_\w*_{signal}',
            rf'{signal}\s*_meta',
        ]
        for pattern in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return self._count_sync_stages(code, signal) >= 2

    def _count_sync_stages(self, code: str, signal: str) -> int:
        """Count synchronizer stages."""
        pattern = rf'\b{signal}_sync\w*\b'
        return len(list(re.finditer(pattern, code, re.IGNORECASE)))

    def _find_signal_line(self, code: str, signal: str) -> int:
        """Find line number of signal declaration."""
        pattern = rf'(?:reg|wire|logic|input|output)\s+(?:\[\d+:\d+\]\s+)?{signal}\b'
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return code[:match.start()].count('\n') + 1
        return 0

    def calibrate_with_synthesis(
        self,
        skill_d_estimates: List[LogicDepthEstimate],
        synthesis_report: Dict[str, Any],
        run_id: str,
        module_name: str
    ) -> CalibratedErrorModel:
        """
        Calibrate Skill D estimates with Stage 5 synthesis results.

        Args:
            skill_d_estimates: Estimates from Skill D
            synthesis_report: Report from Stage 5 Yosys synthesis
            run_id: Unique run identifier
            module_name: Name of the module

        Returns:
            Updated error model
        """
        # Extract actual depth from synthesis
        actual_depth = self._extract_actual_depth_from_synthesis(synthesis_report)
        actual_delay = self._extract_actual_delay_from_synthesis(synthesis_report)

        # For each estimate, add a calibration point
        for estimate in skill_d_estimates:
            point = ErrorModelPoint(
                run_id=run_id,
                estimated_depth=estimate.estimated_depth,
                actual_depth=actual_depth,  # Simplified - should map per-path
                estimated_delay_ns=estimate.estimated_delay_ns,
                actual_delay_ns=actual_delay,
                module_name=module_name
            )
            self.error_model.add_point(point)

        return self.error_model

    def _extract_actual_depth_from_synthesis(self, report: Dict[str, Any]) -> int:
        """Extract actual logic depth from synthesis report."""
        # This is a simplified implementation
        # In real implementation, parse detailed timing path reports
        cells = report.get('cells', {})
        total_cells = sum(cells.values())
        # Heuristic: average fanout of 2, so depth ~ sqrt(total_cells)
        return max(1, int(total_cells ** 0.5))

    def _extract_actual_delay_from_synthesis(self, report: Dict[str, Any]) -> float:
        """Extract actual delay from synthesis report."""
        # Simplified implementation
        cells = report.get('cells', {})
        lut_count = sum(v for k, v in cells.items() if 'lut' in k.lower())
        return lut_count * 0.5  # 0.5ns per LUT

    def check_three_paradigm(self, verilog_code: str) -> List[Dict[str, Any]]:
        """Check three-paradigm compliance."""
        checker = ThreeParadigmChecker()
        self.three_paradigm_issues = checker.check_file(verilog_code)
        return self.three_paradigm_issues

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate a summary report of all Skill D analyses."""
        return {
            "logic_depth": {
                "total_paths": len(self.depth_estimates),
                "exceeding_budget": sum(1 for e in self.depth_estimates if e.exceeds_budget),
                "max_depth": max((e.estimated_depth for e in self.depth_estimates), default=0),
                "avg_depth": sum(e.estimated_depth for e in self.depth_estimates) / len(self.depth_estimates) if self.depth_estimates else 0,
                "details": [e.to_dict() for e in self.depth_estimates]
            },
            "cdc": {
                "total_crossings": len(self.cdc_crossings),
                "unsafe_crossings": sum(1 for c in self.cdc_crossings if c.severity == "error"),
                "warning_crossings": sum(1 for c in self.cdc_crossings if c.severity == "warning"),
                "details": [c.to_dict() for c in self.cdc_crossings]
            },
            "three_paradigm": {
                "total_issues": len(self.three_paradigm_issues),
                "error_count": sum(1 for i in self.three_paradigm_issues if i.get("severity") == "error"),
                "details": self.three_paradigm_issues
            },
            "error_model": self.error_model.to_dict()
        }
