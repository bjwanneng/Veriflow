"""
Stage 4 Enhanced: Waveform Diff with Diagnostic Enhancement.

Implements the full Stage 4 requirements from original design:
- Structured Diff with JSON format
- Assertion ID mapping
- Diagnostic enhancement (probable_cause, suggestion)
- Reference to Skill D / Stage 2 context
- Progressive coverage (critical signals first, then all)
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum
from pathlib import Path
from datetime import datetime


class DiffSeverity(Enum):
    """Severity of a waveform difference."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ProbableCause(Enum):
    """Probable cause categories for differences."""
    OFF_BY_ONE_CYCLE = "off_by_one_cycle"
    BYTE_ORDER_MISMATCH = "byte_order_mismatch"
    RESET_STATE_INCORRECT = "reset_state_incorrect"
    PIPELINE_DEPTH_MISMATCH = "pipeline_depth_mismatch"
    COMBINATIONAL_LOOP = "combinational_loop"
    CDC_METASTABILITY = "cdc_metastability"
    LOGIC_BUG = "logic_bug"
    TIMING_VIOLATION = "timing_violation"
    STIMULUS_MISMATCH = "stimulus_mismatch"
    UNKNOWN = "unknown"


@dataclass
class DiffSuggestion:
    """A suggestion for fixing a difference."""
    suggestion_id: str
    title: str
    description: str
    files_to_check: List[str] = field(default_factory=list)
    skill_d_reference: Optional[str] = None  # Reference to Skill D analysis
    stage2_reference: Optional[str] = None   # Reference to Stage 2 scenario
    priority: int = 5  # 1 = highest priority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "title": self.title,
            "description": self.description,
            "files_to_check": self.files_to_check,
            "skill_d_reference": self.skill_d_reference,
            "stage2_reference": self.stage2_reference,
            "priority": self.priority
        }


@dataclass
class EnhancedDiffEvent:
    """Enhanced difference event with diagnostics."""
    event_id: str
    time_ps: int
    signal_name: str
    expected_value: Any
    actual_value: Any
    severity: DiffSeverity = DiffSeverity.ERROR
    probable_cause: ProbableCause = ProbableCause.UNKNOWN
    probable_cause_confidence: float = 0.0
    description: str = ""
    assertion_id: Optional[str] = None  # Link to Stage 2 assertion
    suggestions: List[DiffSuggestion] = field(default_factory=list)
    context_snippet: Optional[str] = None  # Code snippet near issue

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "time_ps": self.time_ps,
            "signal_name": self.signal_name,
            "expected_value": str(self.expected_value),
            "actual_value": str(self.actual_value),
            "severity": self.severity.value,
            "probable_cause": self.probable_cause.value,
            "probable_cause_confidence": self.probable_cause_confidence,
            "description": self.description,
            "assertion_id": self.assertion_id,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "context_snippet": self.context_snippet
        }


@dataclass
class CoverageLayer:
    """A layer in progressive coverage."""
    layer_name: str
    priority: int
    signals: List[str] = field(default_factory=list)
    covered: bool = False
    issues_found: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_name": self.layer_name,
            "priority": self.priority,
            "signal_count": len(self.signals),
            "signals": self.signals,
            "covered": self.covered,
            "issues_found": self.issues_found
        }


@dataclass
class EnhancedDiffResult:
    """Enhanced diff result with full diagnostics."""
    result_id: str
    matched: bool = False
    differences: List[EnhancedDiffEvent] = field(default_factory=list)
    coverage_layers: List[CoverageLayer] = field(default_factory=list)
    signals_compared: List[str] = field(default_factory=list)
    time_range: Tuple[int, int] = (0, 0)
    assertion_mapping: Dict[str, List[str]] = field(default_factory=dict)  # assertion_id -> event_ids
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def difference_count(self) -> int:
        return len(self.differences)

    @property
    def has_differences(self) -> bool:
        return len(self.differences) > 0

    @property
    def critical_count(self) -> int:
        return sum(1 for d in self.differences if d.severity == DiffSeverity.CRITICAL)

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.differences if d.severity == DiffSeverity.ERROR)

    def add_difference(self, event: EnhancedDiffEvent):
        """Add a difference event and update assertion mapping."""
        self.differences.append(event)
        if event.assertion_id:
            if event.assertion_id not in self.assertion_mapping:
                self.assertion_mapping[event.assertion_id] = []
            self.assertion_mapping[event.assertion_id].append(event.event_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "matched": self.matched,
            "difference_count": self.difference_count,
            "critical_count": self.critical_count,
            "error_count": self.error_count,
            "differences": [d.to_dict() for d in self.differences],
            "coverage_layers": [c.to_dict() for c in self.coverage_layers],
            "signals_compared": self.signals_compared,
            "time_range": self.time_range,
            "assertion_mapping": self.assertion_mapping,
            "generated_at": self.generated_at
        }

    def save_json(self, output_path: Path):
        """Save result as JSON."""
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_markdown(self) -> str:
        """Generate human-readable markdown report."""
        md = "# Enhanced Waveform Diff Report\n\n"
        md += f"Generated: {self.generated_at}\n\n"
        md += f"**Overall Result**: {'✅ MATCHED' if self.matched and not self.has_differences else '❌ MISMATCHED'}\n\n"

        if self.has_differences:
            md += f"## Differences Found: {self.difference_count}\n\n"
            md += f"- Critical: {self.critical_count}\n"
            md += f"- Error: {self.error_count}\n\n"

            md += "### Detailed Differences\n\n"
            for diff in self.differences:
                md += f"#### {diff.signal_name} @ {diff.time_ps}ps\n\n"
                md += f"- **Severity**: {diff.severity.value.upper()}\n"
                md += f"- **Expected**: {diff.expected_value}\n"
                md += f"- **Actual**: {diff.actual_value}\n"
                if diff.description:
                    md += f"- **Description**: {diff.description}\n"
                if diff.probable_cause != ProbableCause.UNKNOWN:
                    md += f"- **Probable Cause**: {diff.probable_cause.value} ({diff.probable_cause_confidence*100:.0f}%)\n"
                if diff.assertion_id:
                    md += f"- **Assertion**: {diff.assertion_id}\n"
                if diff.suggestions:
                    md += f"- **Suggestions**:\n"
                    for sugg in diff.suggestions:
                        md += f"  1. **{sugg.title}**: {sugg.description}\n"
                        if sugg.files_to_check:
                            md += f"     - Files: {', '.join(sugg.files_to_check)}\n"
                md += "\n---\n\n"

        if self.coverage_layers:
            md += "## Progressive Coverage\n\n"
            for layer in self.coverage_layers:
                status = "✅" if layer.covered else "🔴"
                md += f"### {status} Layer {layer.priority}: {layer.layer_name}\n"
                md += f"- Signals: {len(layer.signals)}\n"
                if layer.issues_found:
                    md += f"- Issues: {', '.join(layer.issues_found)}\n"
                md += "\n"

        return md


class DiagnosticAnalyzer:
    """
    Analyzes waveform differences to determine probable causes.

    Uses heuristics to identify common failure patterns.
    """

    # Patterns for common issues
    PATTERNS = {
        ProbableCause.OFF_BY_ONE_CYCLE: [
            (r'valid.*1.*cycle', 0.7),
            (r'latency.*mismatch', 0.6),
            (r'delay.*1.*cycle', 0.7),
        ],
        ProbableCause.BYTE_ORDER_MISMATCH: [
            (r'byte.*order', 0.8),
            (r'endian.*mismatch', 0.8),
            (r'[0-9a-f]{8}.*[0-9a-f]{8}.*reverse', 0.6),
        ],
        ProbableCause.RESET_STATE_INCORRECT: [
            (r'reset.*state', 0.8),
            (r'rst.*value', 0.7),
            (r'initial.*value', 0.6),
        ],
        ProbableCause.PIPELINE_DEPTH_MISMATCH: [
            (r'pipeline.*depth', 0.7),
            (r'stage.*count', 0.6),
        ],
        ProbableCause.COMBINATIONAL_LOOP: [
            (r'combinational.*loop', 0.9),
            (r'loop.*detected', 0.8),
        ],
        ProbableCause.TIMING_VIOLATION: [
            (r'setup.*violation', 0.8),
            (r'hold.*violation', 0.8),
            (r'timing.*fail', 0.7),
        ],
    }

    def __init__(self):
        pass

    def analyze_difference(
        self,
        event: EnhancedDiffEvent,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[ProbableCause, float, List[DiffSuggestion]]:
        """
        Analyze a difference to find probable cause and suggestions.

        Args:
            event: The difference event
            context: Optional context (Skill D analysis, Stage 2 scenarios, etc.)

        Returns:
            (probable_cause, confidence, suggestions)
        """
        context = context or {}
        description = event.description.lower() if event.description else ""
        signal_name = event.signal_name.lower()

        best_cause = ProbableCause.UNKNOWN
        best_confidence = 0.0

        # Check against known patterns
        for cause, patterns in self.PATTERNS.items():
            for pattern, base_conf in patterns:
                if re.search(pattern, description) or re.search(pattern, signal_name):
                    if base_conf > best_confidence:
                        best_cause = cause
                        best_confidence = base_conf

        # Additional heuristics based on value pattern
        if best_cause == ProbableCause.UNKNOWN:
            expected = str(event.expected_value)
            actual = str(event.actual_value)
            if self._is_reversed_pattern(expected, actual):
                best_cause = ProbableCause.BYTE_ORDER_MISMATCH
                best_confidence = 0.75

        # Generate suggestions
        suggestions = self._generate_suggestions(best_cause, event, context)

        return best_cause, best_confidence, suggestions

    def _is_reversed_pattern(self, expected: str, actual: str) -> bool:
        """Check if values look reversed (byte order issue)."""
        # Remove 0x prefix and common separators
        exp_clean = expected.lower().replace('0x', '').replace('_', '').replace(' ', '')
        act_clean = actual.lower().replace('0x', '').replace('_', '').replace(' ', '')

        if len(exp_clean) == len(act_clean) and len(exp_clean) % 2 == 0:
            # Reverse in byte chunks
            bytes_exp = [exp_clean[i:i+2] for i in range(0, len(exp_clean), 2)]
            bytes_act = [act_clean[i:i+2] for i in range(0, len(act_clean), 2)]
            if bytes_exp == list(reversed(bytes_act)):
                return True

        return False

    def _generate_suggestions(
        self,
        cause: ProbableCause,
        event: EnhancedDiffEvent,
        context: Dict[str, Any]
    ) -> List[DiffSuggestion]:
        """Generate suggestions based on probable cause."""
        suggestions = []
        skill_d_ref = context.get('skill_d_reference')
        stage2_ref = context.get('stage2_reference')

        if cause == ProbableCause.OFF_BY_ONE_CYCLE:
            suggestions.append(DiffSuggestion(
                suggestion_id="check_pipeline_depth",
                title="Check pipeline depth configuration",
                description="Verify that the number of pipeline stages in RTL matches the spec.",
                files_to_check=["rtl/*top*.v", "stage_1_spec/*spec.json"],
                skill_d_reference=skill_d_ref,
                stage2_reference=stage2_ref,
                priority=1
            ))

        elif cause == ProbableCause.BYTE_ORDER_MISMATCH:
            suggestions.append(DiffSuggestion(
                suggestion_id="check_byte_order",
                title="Verify byte order (MSB/LSB)",
                description="Check that byte ordering matches between spec and RTL.",
                files_to_check=["rtl/*.v"],
                skill_d_reference=skill_d_ref,
                priority=1
            ))

        elif cause == ProbableCause.RESET_STATE_INCORRECT:
            suggestions.append(DiffSuggestion(
                suggestion_id="check_reset",
                title="Check reset initialization",
                description="Verify all registers have correct reset values.",
                files_to_check=["rtl/*.v"],
                priority=2
            ))

        elif cause == ProbableCause.TIMING_VIOLATION:
            suggestions.append(DiffSuggestion(
                suggestion_id="check_skill_d",
                title="Review Skill D timing analysis",
                description="Check logic depth estimates and CDC analysis from Stage 3.",
                files_to_check=["stage_3_rtl/*summary*.md"],
                skill_d_reference=skill_d_ref,
                priority=1
            ))

        # Generic suggestions
        if not suggestions:
            suggestions.append(DiffSuggestion(
                suggestion_id="check_golden_trace",
                title="Compare against Stage 2 Golden Trace",
                description="Verify that the expected waveform matches the Stage 2 scenario.",
                files_to_check=["stage_2_timing/*.yaml", "stage_2_timing/*trace*.json"],
                stage2_reference=stage2_ref,
                priority=3
            ))

        return suggestions


class ProgressiveCoverageManager:
    """
    Manages progressive coverage: critical signals first, then all.

    Coverage layers:
    1. Clock & Reset (highest priority)
    2. Control signals (valid, ready, enable)
    3. Critical data signals
    4. All other signals
    """

    LAYER_DEFINITIONS = [
        ("clock_reset", 1, ["clk", "clock", "rst", "reset", "rst_n", "reset_n"]),
        ("control", 2, ["valid", "ready", "enable", "en", "wr_en", "rd_en", "we", "re"]),
        ("critical_data", 3, ["data", "key", "state", "o_data", "i_data"]),
        ("all_signals", 4, []),
    ]

    def __init__(self):
        self.layers: List[CoverageLayer] = []

    def initialize_layers(self, all_signals: List[str]):
        """Initialize coverage layers from signal list."""
        self.layers = []
        remaining_signals = set(all_signals)

        for layer_name, priority, patterns in self.LAYER_DEFINITIONS:
            layer = CoverageLayer(layer_name=layer_name, priority=priority)

            if patterns:
                # Match by patterns
                for signal in list(remaining_signals):
                    signal_lower = signal.lower()
                    if any(p in signal_lower for p in patterns):
                        layer.signals.append(signal)
                        remaining_signals.remove(signal)
            else:
                # Last layer gets all remaining
                layer.signals = list(remaining_signals)
                remaining_signals = set()

            self.layers.append(layer)

        return self.layers

    def mark_layer_covered(self, layer_name: str, issues_found: Optional[List[str]] = None):
        """Mark a layer as covered."""
        for layer in self.layers:
            if layer.layer_name == layer_name:
                layer.covered = True
                if issues_found:
                    layer.issues_found = issues_found

    def get_next_layer_to_cover(self) -> Optional[CoverageLayer]:
        """Get the next priority layer that hasn't been covered."""
        for layer in sorted(self.layers, key=lambda l: l.priority):
            if not layer.covered:
                return layer
        return None


class EnhancedWaveformDiffAnalyzer:
    """
    Enhanced waveform diff analyzer with full diagnostics.

    Features:
    - Structured JSON output
    - Assertion ID mapping
    - Probable cause analysis
    - Fix suggestions with Skill D/Stage 2 references
    - Progressive coverage
    """

    def __init__(
        self,
        tolerance_ps: int = 100,
        context: Optional[Dict[str, Any]] = None
    ):
        self.tolerance_ps = tolerance_ps
        self.context = context or {}
        self.diagnostic_analyzer = DiagnosticAnalyzer()
        self.coverage_manager = ProgressiveCoverageManager()

    def compare_with_diagnostics(
        self,
        golden_trace: Dict[str, Any],
        actual_waveform: Dict[str, Any],
        assertion_map: Optional[Dict[str, List[str]]] = None
    ) -> EnhancedDiffResult:
        """
        Compare waveforms with full diagnostic analysis.

        Args:
            golden_trace: Golden trace from Stage 2
            actual_waveform: Actual waveform from simulation
            assertion_map: Optional mapping from assertion_id to signal names

        Returns:
            Enhanced diff result with diagnostics
        """
        result = EnhancedDiffResult(
            result_id=f"diff_{int(datetime.now().timestamp())}"
        )

        # Extract all signals
        golden_signals = self._extract_signals(golden_trace)
        actual_signals = self._extract_signals(actual_waveform)
        all_signals = list(set(golden_signals + actual_signals))

        # Initialize progressive coverage
        self.coverage_manager.initialize_layers(all_signals)
        result.coverage_layers = self.coverage_manager.layers

        # Get assertion map for signal -> assertion links
        assertion_map = assertion_map or {}
        signal_to_assertion: Dict[str, List[str]] = {}
        for assertion_id, signals in assertion_map.items():
            for signal in signals:
                if signal not in signal_to_assertion:
                    signal_to_assertion[signal] = []
                signal_to_assertion[signal].append(assertion_id)

        # Compare signals (progressive coverage order)
        event_counter = 0
        for layer in sorted(self.coverage_manager.layers, key=lambda l: l.priority):
            layer_issues = []

            for signal in layer.signals:
                diffs = self._compare_signal(golden_trace, actual_waveform, signal)

                for time_ps, exp_val, act_val in diffs:
                    event = EnhancedDiffEvent(
                        event_id=f"evt_{event_counter}",
                        time_ps=time_ps,
                        signal_name=signal,
                        expected_value=exp_val,
                        actual_value=act_val,
                        description=f"Value mismatch on {signal}"
                    )

                    # Link to assertion if available
                    if signal in signal_to_assertion:
                        event.assertion_id = signal_to_assertion[signal][0]

                    # Analyze for probable cause
                    cause, confidence, suggestions = self.diagnostic_analyzer.analyze_difference(
                        event, self.context
                    )
                    event.probable_cause = cause
                    event.probable_cause_confidence = confidence
                    event.suggestions = suggestions

                    # Severity based on signal type
                    if layer.priority == 1:
                        event.severity = DiffSeverity.CRITICAL
                    elif layer.priority == 2:
                        event.severity = DiffSeverity.ERROR
                    else:
                        event.severity = DiffSeverity.ERROR if cause != ProbableCause.UNKNOWN else DiffSeverity.WARNING

                    result.add_difference(event)
                    layer_issues.append(signal)
                    event_counter += 1

            self.coverage_manager.mark_layer_covered(layer.layer_name, layer_issues)

        # Final result
        result.matched = len(result.differences) == 0
        result.signals_compared = all_signals

        if golden_trace.get('events'):
            times = [e.get('time_ps', 0) for e in golden_trace['events']]
            if times:
                result.time_range = (min(times), max(times))

        return result

    def _extract_signals(self, waveform: Dict[str, Any]) -> List[str]:
        """Extract signal names from waveform data."""
        signals = []
        if 'events' in waveform:
            for event in waveform['events']:
                if 'signal' in event:
                    signals.append(event['signal'])
        elif 'signals' in waveform:
            signals = list(waveform['signals'].keys())
        return list(set(signals))

    def _compare_signal(
        self,
        golden: Dict[str, Any],
        actual: Dict[str, Any],
        signal: str
    ) -> List[Tuple[int, Any, Any]]:
        """Compare a single signal and return differences."""
        differences = []

        # Get golden timeline for this signal
        golden_timeline = self._get_signal_timeline(golden, signal)
        actual_timeline = self._get_signal_timeline(actual, signal)

        # Compare at each time point
        all_times = set(t for t, _ in golden_timeline + actual_timeline)

        for time_ps in sorted(all_times):
            golden_val = self._get_value_at_time(golden_timeline, time_ps)
            actual_val = self._get_value_at_time(actual_timeline, time_ps)

            if golden_val is not None and actual_val is not None:
                if str(golden_val) != str(actual_val):
                    # Check if within tolerance
                    if self._values_are_close(golden_val, actual_val):
                        continue
                    differences.append((time_ps, golden_val, actual_val))

        return differences

    def _get_signal_timeline(self, waveform: Dict[str, Any], signal: str) -> List[Tuple[int, Any]]:
        """Get timeline for a specific signal."""
        timeline = []
        if 'events' in waveform:
            for event in waveform['events']:
                if event.get('signal') == signal:
                    timeline.append((
                        event.get('time_ps', 0),
                        event.get('value')
                    ))
        return timeline

    def _get_value_at_time(self, timeline: List[Tuple[int, Any]], target_time: int) -> Any:
        """Get signal value at a specific time."""
        current_value = None
        for time_ps, value in timeline:
            if time_ps <= target_time:
                current_value = value
            else:
                break
        return current_value

    def _values_are_close(self, val1: Any, val2: Any) -> bool:
        """Check if values are close enough (within tolerance)."""
        # For x/z values, they match anything
        if str(val1).lower() in ('x', 'z') or str(val2).lower() in ('x', 'z'):
            return True
        return str(val1) == str(val2)
