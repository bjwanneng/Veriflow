"""Skill D: Logic Depth and CDC Analysis (Stage 3)."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple


@dataclass
class LogicDepthResult:
    """Result of logic depth analysis."""
    signal_path: str
    start_signal: str
    end_signal: str
    depth: int
    gates: List[str] = field(default_factory=list)
    estimated_delay_ps: float = 0.0


@dataclass
class CDCCrossing:
    """A single CDC crossing."""
    source_clock: str
    dest_clock: str
    signal: str
    has_synchronizer: bool = False
    synchronizer_stages: int = 0
    line_number: int = 0


@dataclass
class CDCAnalysisResult:
    """Result of CDC analysis."""
    crossings: List[CDCCrossing] = field(default_factory=list)

    @property
    def unsafe_crossings(self) -> List[CDCCrossing]:
        """Crossings without proper synchronizers."""
        return [c for c in self.crossings if not c.has_synchronizer]

    @property
    def safe_crossings(self) -> List[CDCCrossing]:
        """Crossings with proper synchronizers."""
        return [c for c in self.crossings if c.has_synchronizer]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_crossings": len(self.crossings),
            "safe_crossings": len(self.safe_crossings),
            "unsafe_crossings": len(self.unsafe_crossings),
            "crossings": [
                {
                    "signal": c.signal,
                    "source_clock": c.source_clock,
                    "dest_clock": c.dest_clock,
                    "has_synchronizer": c.has_synchronizer,
                    "synchronizer_stages": c.synchronizer_stages,
                    "line_number": c.line_number
                }
                for c in self.crossings
            ]
        }


def analyze_logic_depth(verilog_code: str, target_depth: int = 10) -> Dict[str, Any]:
    """Analyze combinational logic depth.

    This is a simplified analysis that estimates logic depth based on:
    - Number of operators in continuous assignments
    - Nested if/case statements
    """
    results = []

    # Analyze continuous assignments
    assign_pattern = r'assign\s+(\w+)\s*=\s*([^;]+);'

    for match in re.finditer(assign_pattern, verilog_code):
        signal = match.group(1)
        expression = match.group(2)
        line_number = verilog_code[:match.start()].count('\n') + 1

        # Count logic levels in expression
        depth = _estimate_expression_depth(expression)

        if depth > target_depth:
            results.append({
                "signal": signal,
                "depth": depth,
                "line_number": line_number,
                "warning": f"Logic depth {depth} exceeds target {target_depth}"
            })

    # Analyze always blocks
    always_pattern = r'always\s*@\s*\([^)]*\*[^)]*\)(.*?)(?=always|endmodule|$)'

    for match in re.finditer(always_pattern, verilog_code, re.DOTALL | re.IGNORECASE):
        block = match.group(1)

        # Find assignments within the block
        for assign_match in re.finditer(r'(\w+)\s*[=<>]=\s*([^;]+);', block):
            signal = assign_match.group(1)
            expression = assign_match.group(2)

            depth = _estimate_expression_depth(expression)

            if depth > target_depth:
                # Calculate absolute line number
                block_start = match.start(1)
                relative_pos = assign_match.start()
                abs_pos = block_start + relative_pos
                line_number = verilog_code[:abs_pos].count('\n') + 1

                results.append({
                    "signal": signal,
                    "depth": depth,
                    "line_number": line_number,
                    "warning": f"Logic depth {depth} exceeds target {target_depth}"
                })

    return {
        "target_depth": target_depth,
        "violations": results,
        "violation_count": len(results)
    }


def _estimate_expression_depth(expression: str) -> int:
    """Estimate logic depth of an expression.

    This is a heuristic that counts:
    - Operators as potential logic levels
    - Nested parentheses as depth
    - Function calls as additional depth
    """
    expression = expression.strip()

    if not expression:
        return 0

    # Count operators
    operators = len(re.findall(r'[&|^~+\-*/%]|==|!=|<|>|<=|>=|&&|\|\|', expression))

    # Count nested levels (parentheses depth)
    max_paren_depth = 0
    current_depth = 0
    for char in expression:
        if char == '(':
            current_depth += 1
            max_paren_depth = max(max_paren_depth, current_depth)
        elif char == ')':
            current_depth -= 1

    # Count conditional operators
    conditionals = expression.count('?')

    # Estimate: each operator ~1 level, conditionals ~2 levels
    estimated_depth = max(operators, max_paren_depth) + conditionals * 2

    return max(1, estimated_depth)


def analyze_cdc(verilog_code: str) -> CDCAnalysisResult:
    """Analyze clock domain crossings in the design.

    This is a simplified CDC analysis that looks for:
    - Multiple clock signals
    - Signals crossing between clock domains
    - Presence of synchronizers
    """
    result = CDCAnalysisResult()

    # Find all clock signals
    clocks = _find_clocks(verilog_code)

    if len(clocks) < 2:
        # No CDC possible with single clock
        return result

    # Find all always blocks and their clock domains
    always_blocks = _find_always_blocks(verilog_code)

    # Identify signals assigned in different clock domains
    signal_domains: Dict[str, Set[str]] = {}

    for block in always_blocks:
        clock = block.get('clock', 'unknown')
        assigned_signals = block.get('assigned_signals', set())

        for sig in assigned_signals:
            if sig not in signal_domains:
                signal_domains[sig] = set()
            signal_domains[sig].add(clock)

    # Find signals that exist in multiple domains (potential CDC)
    for signal, domains in signal_domains.items():
        if len(domains) > 1:
            # This signal is assigned in multiple clock domains
            domain_list = sorted(domains)
            for i in range(len(domain_list) - 1):
                crossing = CDCCrossing(
                    source_clock=domain_list[i],
                    dest_clock=domain_list[i + 1],
                    signal=signal,
                    has_synchronizer=_check_synchronizer(verilog_code, signal),
                    line_number=_find_signal_line(verilog_code, signal)
                )
                result.crossings.append(crossing)

    # Also check for synchronizer patterns (signals named like sync_* or *_sync)
    sync_pattern = r'(?:reg|logic)\s+(?:\[\d+:\d+\]\s+)?(sync_\w+|\w+_sync)\s*(?:\[|$|;)'
    for match in re.finditer(sync_pattern, verilog_code, re.IGNORECASE):
        signal = match.group(1)
        if not any(c.signal == signal for c in result.crossings):
            # This is a synchronizer signal, check if it's properly used
            line_number = verilog_code[:match.start()].count('\n') + 1

            # Try to determine source/dest clocks
            source_clock = "unknown"
            dest_clock = "clk"  # Assume main clock

            crossing = CDCCrossing(
                source_clock=source_clock,
                dest_clock=dest_clock,
                signal=signal,
                has_synchronizer=True,
                synchronizer_stages=_count_sync_stages(verilog_code, signal),
                line_number=line_number
            )
            result.crossings.append(crossing)

    return result


def _find_clocks(verilog_code: str) -> List[str]:
    """Find all clock signals in the code."""
    clocks = []

    # Common clock names
    clock_patterns = [
        r'input\s+(?:wire\s+)?(?:clk|clock)\w*',
        r'input\s+(?:wire\s+)?\w+_clk\w*',
        r'input\s+(?:wire\s+)?\w+_clock\w*',
    ]

    for pattern in clock_patterns:
        for match in re.finditer(pattern, verilog_code, re.IGNORECASE):
            # Extract signal name
            parts = match.group(0).split()
            for part in parts:
                if 'clk' in part.lower():
                    clocks.append(part.strip())

    return list(set(clocks))


def _find_always_blocks(verilog_code: str) -> List[Dict[str, Any]]:
    """Find all always blocks and extract their properties."""
    blocks = []

    # Match always blocks
    always_pattern = r'always\s*@\s*\(([^)]+)\)(.*?)(?=always|endmodule|$)'

    for match in re.finditer(always_pattern, verilog_code, re.DOTALL | re.IGNORECASE):
        sensitivity = match.group(1).strip()
        block_content = match.group(2)

        # Determine clock
        clock = "unknown"
        if 'posedge' in sensitivity or 'negedge' in sensitivity:
            clk_match = re.search(r'(posedge|negedge)\s+(\w+)', sensitivity, re.IGNORECASE)
            if clk_match:
                clock = clk_match.group(2)

        # Find assigned signals
        assigned_signals = set()
        for assign_match in re.finditer(r'(\w+)\s*<[=]=', block_content):
            assigned_signals.add(assign_match.group(1))

        blocks.append({
            'clock': clock,
            'sensitivity': sensitivity,
            'assigned_signals': assigned_signals,
            'content': block_content
        })

    return blocks


def _check_synchronizer(verilog_code: str, signal: str) -> bool:
    """Check if a signal has a synchronizer."""
    # Look for synchronizer patterns
    sync_patterns = [
        rf'{signal}\s*_sync',
        rf'sync_\w*_{signal}',
    ]

    for pattern in sync_patterns:
        if re.search(pattern, verilog_code, re.IGNORECASE):
            return True

    # Check for multi-stage flop (common synchronizer pattern)
    # This is a simplified check
    stages = _count_sync_stages(verilog_code, signal)
    return stages >= 2


def _count_sync_stages(verilog_code: str, signal: str) -> int:
    """Count the number of synchronizer stages for a signal."""
    # Look for patterns like signal_sync, signal_sync_reg, etc.
    pattern = rf'\b{signal}_sync\w*\b'
    matches = list(re.finditer(pattern, verilog_code, re.IGNORECASE))
    return len(matches)


def _find_signal_line(verilog_code: str, signal: str) -> int:
    """Find the line number where a signal is declared."""
    pattern = rf'(?:reg|wire|logic|input|output)\s+(?:\[\d+:\d+\]\s+)?{signal}\b'
    match = re.search(pattern, verilog_code, re.IGNORECASE)
    if match:
        return verilog_code[:match.start()].count('\n') + 1
    return 0
