"""Waveform Diff Analyzer for Stage 4."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..stage2.golden_trace import GoldenTrace, TraceEvent


@dataclass
class DiffEvent:
    """A single difference event."""
    time_ps: int
    signal: str
    expected_value: Any
    actual_value: Any
    description: str = ""


@dataclass
class DiffResult:
    """Result of waveform diff analysis."""
    matched: bool
    differences: List[DiffEvent] = field(default_factory=list)
    signals_compared: List[str] = field(default_factory=list)
    time_range: Tuple[int, int] = (0, 0)

    @property
    def difference_count(self) -> int:
        return len(self.differences)

    @property
    def has_differences(self) -> bool:
        return len(self.differences) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "difference_count": self.difference_count,
            "signals_compared": self.signals_compared,
            "time_range": self.time_range,
            "differences": [
                {
                    "time_ps": d.time_ps,
                    "signal": d.signal,
                    "expected": str(d.expected_value),
                    "actual": str(d.actual_value),
                    "description": d.description
                }
                for d in self.differences
            ]
        }


class WaveformDiffAnalyzer:
    """Compare simulation waveforms against golden traces."""

    def __init__(self, tolerance_ps: int = 100):
        """Initialize analyzer.

        Args:
            tolerance_ps: Time tolerance in picoseconds for matching events
        """
        self.tolerance_ps = tolerance_ps

    def compare(self, golden_trace: GoldenTrace, vcd_file: Path) -> DiffResult:
        """Compare golden trace against VCD waveform."""

        # Parse VCD file
        actual_trace = self._parse_vcd(vcd_file)

        # Perform comparison
        return self._compare_traces(golden_trace, actual_trace)

    def compare_against_simulation_output(
        self,
        golden_trace: GoldenTrace,
        simulation_output: str
    ) -> DiffResult:
        """Compare golden trace against simulation text output."""

        result = DiffResult(matched=True)
        result.signals_compared = list(set(e.signal for e in golden_trace.events))

        # Extract signal values from simulation output
        sim_values = self._parse_simulation_output(simulation_output)

        # Compare each expected event
        for event in golden_trace.events:
            if event.signal == "__ASSERTION__":
                continue  # Skip assertion events

            # Find actual value at this time
            actual_value = sim_values.get(event.signal)

            if actual_value is None:
                result.differences.append(DiffEvent(
                    time_ps=event.time_ps,
                    signal=event.signal,
                    expected_value=event.value,
                    actual_value=None,
                    description=f"Signal {event.signal} not found in simulation output"
                ))
            elif str(actual_value) != str(event.value):
                result.differences.append(DiffEvent(
                    time_ps=event.time_ps,
                    signal=event.signal,
                    expected_value=event.value,
                    actual_value=actual_value,
                    description=f"Value mismatch at {event.time_ps}ps"
                ))

        result.matched = not result.has_differences
        return result

    def _parse_vcd(self, vcd_file: Path) -> Dict[str, List[Tuple[int, Any]]]:
        """Parse VCD file into signal timeline.

        Returns:
            Dictionary mapping signal names to list of (time, value) tuples
        """
        signals: Dict[str, str] = {}  # var_id -> signal name
        timeline: Dict[str, List[Tuple[int, Any]]] = {}  # signal -> [(time, value)]

        current_time = 0

        with open(vcd_file, 'r') as f:
            lines = f.readlines()

        in_definitions = True

        for line in lines:
            line = line.strip()

            if not line:
                continue

            # End of definitions
            if line == "$enddefinitions $end":
                in_definitions = False
                continue

            # Parse definitions
            if in_definitions:
                if line.startswith("$var"):
                    # $var type size id name $end
                    parts = line.split()
                    if len(parts) >= 5:
                        var_id = parts[3]
                        var_name = parts[4]
                        signals[var_id] = var_name
                        timeline[var_name] = []

            else:
                # Parse value changes
                if line.startswith('#'):
                    current_time = int(line[1:])
                elif line[0] in '01xXzZ':
                    # Binary value
                    var_id = line[1:].strip()
                    value = line[0]
                    if var_id in signals:
                        sig_name = signals[var_id]
                        timeline[sig_name].append((current_time, value))
                elif line[0] == 'b':
                    # Bus value
                    parts = line.split()
                    if len(parts) >= 2:
                        value = parts[0][1:]  # Remove 'b' prefix
                        var_id = parts[1]
                        if var_id in signals:
                            sig_name = signals[var_id]
                            timeline[sig_name].append((current_time, value))

        return timeline

    def _compare_traces(
        self,
        golden: GoldenTrace,
        actual: Dict[str, List[Tuple[int, Any]]]
    ) -> DiffResult:
        """Compare golden trace against actual waveform."""

        result = DiffResult(matched=True)
        result.signals_compared = list(set(e.signal for e in golden.events
                                           if e.signal != "__ASSERTION__"))

        if golden.events:
            times = [e.time_ps for e in golden.events]
            result.time_range = (min(times), max(times))

        # Compare each event in golden trace
        for event in golden.events:
            if event.signal == "__ASSERTION__":
                continue

            if event.signal not in actual:
                result.differences.append(DiffEvent(
                    time_ps=event.time_ps,
                    signal=event.signal,
                    expected_value=event.value,
                    actual_value=None,
                    description=f"Signal {event.signal} not found in waveform"
                ))
                continue

            # Find expected value at this time
            actual_value = self._get_value_at_time(
                actual[event.signal],
                event.time_ps
            )

            if not self._values_match(event.value, actual_value):
                result.differences.append(DiffEvent(
                    time_ps=event.time_ps,
                    signal=event.signal,
                    expected_value=event.value,
                    actual_value=actual_value,
                    description=f"Value mismatch at {event.time_ps}ps"
                ))

        result.matched = not result.has_differences
        return result

    def _get_value_at_time(
        self,
        timeline: List[Tuple[int, Any]],
        target_time: int
    ) -> Any:
        """Get signal value at a specific time."""

        current_value = None

        for time, value in timeline:
            if time <= target_time:
                current_value = value
            else:
                break

        return current_value

    def _values_match(self, expected: Any, actual: Any) -> bool:
        """Check if two values match."""

        # Handle don't care values
        if expected == 'x' or expected == 'X':
            return True

        # Convert to string for comparison
        expected_str = str(expected).lower()
        actual_str = str(actual).lower()

        return expected_str == actual_str

    def _parse_simulation_output(self, output: str) -> Dict[str, Any]:
        """Parse signal values from simulation output text."""

        values = {}

        # Look for patterns like:
        # signal_name = value
        # signal_name: value

        patterns = [
            r'(\w+)\s*=\s*(\w+)',
            r'(\w+)\s*:\s*(\w+)',
            r'(\w+)\s*=\s*(\d+)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, output):
                signal_name = match.group(1)
                value = match.group(2)
                values[signal_name] = value

        return values

    def generate_report(self, result: DiffResult, output_path: Path) -> Path:
        """Generate a detailed diff report."""

        lines = []
        lines.append("=" * 80)
        lines.append("Waveform Diff Analysis Report")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Matched: {result.matched}")
        lines.append(f"Differences Found: {result.difference_count}")
        lines.append(f"Signals Compared: {len(result.signals_compared)}")
        lines.append(f"Time Range: {result.time_range[0]}ps - {result.time_range[1]}ps")
        lines.append("")

        if result.differences:
            lines.append("Differences:")
            lines.append("-" * 80)
            for diff in result.differences:
                lines.append(f"  Time: {diff.time_ps}ps")
                lines.append(f"  Signal: {diff.signal}")
                lines.append(f"  Expected: {diff.expected_value}")
                lines.append(f"  Actual: {diff.actual_value}")
                lines.append(f"  Description: {diff.description}")
                lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
