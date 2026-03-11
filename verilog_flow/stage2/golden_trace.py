"""Golden Trace generation from timing scenarios (Stage 2)."""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json

from .yaml_dsl import TimingScenario, Phase, SignalTransition, TransitionType


class TraceValueType(Enum):
    """Types of trace values."""
    BINARY = "binary"
    HEX = "hex"
    DECIMAL = "decimal"
    STRING = "string"
    DONT_CARE = "dont_care"


@dataclass
class TraceEvent:
    """A single event in the golden trace."""
    time_ps: int  # Time in picoseconds
    signal: str
    value: Union[int, str]
    value_type: TraceValueType = TraceValueType.BINARY
    transition: TransitionType = TransitionType.HOLD
    phase_name: str = ""
    assertion_checked: Optional[str] = None  # Assertion that was checked

    def to_dict(self) -> Dict:
        return {
            "time_ps": self.time_ps,
            "signal": self.signal,
            "value": self.value,
            "value_type": self.value_type.value,
            "transition": self.transition.value,
            "phase_name": self.phase_name,
            "assertion_checked": self.assertion_checked
        }

    def to_vcd_value(self) -> str:
        """Convert to VCD (Value Change Dump) format."""
        if self.value_type == TraceValueType.BINARY:
            return f"{self.value}"
        elif self.value_type == TraceValueType.HEX:
            return f"h{self.value:X}"
        elif self.value_type == TraceValueType.DECIMAL:
            return f"d{self.value}"
        else:
            return f"{self.value}"


@dataclass
class GoldenTrace:
    """Complete golden trace for a timing scenario."""
    scenario_id: str
    scenario_name: str
    clock_period_ps: int
    events: List[TraceEvent] = field(default_factory=list)

    # Index for fast lookup
    _signal_events: Dict[str, List[TraceEvent]] = field(default_factory=dict, repr=False)
    _time_index: Dict[int, List[TraceEvent]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """Build indexes after initialization."""
        self._rebuild_indexes()

    def _rebuild_indexes(self):
        """Rebuild lookup indexes."""
        self._signal_events.clear()
        self._time_index.clear()

        for event in self.events:
            # Index by signal
            if event.signal not in self._signal_events:
                self._signal_events[event.signal] = []
            self._signal_events[event.signal].append(event)

            # Index by time
            time_key = event.time_ps // self.clock_period_ps
            if time_key not in self._time_index:
                self._time_index[time_key] = []
            self._time_index[time_key].append(event)

    def add_event(self, event: TraceEvent):
        """Add an event to the trace."""
        self.events.append(event)

        # Update indexes
        if event.signal not in self._signal_events:
            self._signal_events[event.signal] = []
        self._signal_events[event.signal].append(event)

        time_key = event.time_ps // self.clock_period_ps
        if time_key not in self._time_index:
            self._time_index[time_key] = []
        self._time_index[time_key].append(event)

    def get_signal_events(self, signal: str) -> List[TraceEvent]:
        """Get all events for a specific signal."""
        return self._signal_events.get(signal, [])

    def get_events_at_time(self, time_ps: int) -> List[TraceEvent]:
        """Get all events at a specific time."""
        time_key = time_ps // self.clock_period_ps
        return self._time_index.get(time_key, [])

    def get_signal_value_at_time(self, signal: str, time_ps: int) -> Optional[Any]:
        """Get the value of a signal at a specific time."""
        events = self.get_signal_events(signal)

        # Find the most recent event at or before the requested time
        current_value = None
        for event in events:
            if event.time_ps <= time_ps:
                current_value = event.value
            else:
                break

        return current_value

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "clock_period_ps": self.clock_period_ps,
            "events": [e.to_dict() for e in self.events]
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, output_path: Path):
        """Save trace to file."""
        output_path = Path(output_path)
        output_path.write_text(self.to_json(), encoding='utf-8')

    def to_vcd(self, timescale: str = "1ps") -> str:
        """Convert to VCD (Value Change Dump) format.

        VCD is a standard format for digital waveform viewing.
        """
        lines = []

        # Header
        lines.append(f"$timescale {timescale} $end")
        lines.append(f"$version VeriFlow-Agent 3.0 $end")
        lines.append(f"$date {__import__('datetime').datetime.now().isoformat()} $end")

        # Scope and variables
        lines.append("$scope module test $end")

        # Collect all signals
        signals = sorted(self._signal_events.keys())
        var_ids = {}
        for i, sig in enumerate(signals):
            var_id = chr(ord('!') + i) if i < 90 else f"v{i}"
            var_ids[sig] = var_id
            # Determine bit width (simplified)
            lines.append(f"$var wire 1 {var_id} {sig} $end")

        lines.append("$upscope $end")
        lines.append("$enddefinitions $end")
        lines.append("$dumpvars")

        # Initial values
        for sig in signals:
            val = self.get_signal_value_at_time(sig, 0)
            if val is None:
                val = "x"
            lines.append(f"{val}{var_ids[sig]}")

        lines.append("$end")

        # Value changes, sorted by time
        all_events = sorted(self.events, key=lambda e: e.time_ps)
        current_time = 0

        for event in all_events:
            if event.time_ps != current_time:
                current_time = event.time_ps
                lines.append(f"#{current_time}")

            var_id = var_ids.get(event.signal)
            if var_id:
                val = event.value if event.value is not None else "x"
                lines.append(f"{val}{var_id}")

        return "\n".join(lines)


def generate_golden_trace(scenario: TimingScenario) -> GoldenTrace:
    """Generate a GoldenTrace from a TimingScenario.

    This converts the high-level YAML scenario into cycle-by-cycle
    trace events that can be compared against actual simulation.
    """
    # Determine clock period from scenario
    clock_period_ps = 10000  # Default 10ns = 100MHz

    if scenario.clocks:
        # Use first clock's period
        first_clock = list(scenario.clocks.values())[0]
        period_str = first_clock.get("period", "10ns")
        # Parse period string (e.g., "5ns", "10ps")
        import re
        match = re.match(r"(\d+(?:\.\d+)?)\s*(ps|ns|us|ms)?", period_str)
        if match:
            val = float(match.group(1))
            unit = match.group(2) or "ns"
            multiplier = {"ps": 1, "ns": 1000, "us": 1000000, "ms": 1000000000}
            clock_period_ps = int(val * multiplier.get(unit, 1000))

    trace = GoldenTrace(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        clock_period_ps=clock_period_ps
    )

    # Generate events from phases
    current_time_ps = 0

    for phase in scenario.phases:
        # Calculate phase duration
        phase_duration_ns = getattr(phase, 'duration_ns', 10.0)
        phase_duration_ps = int(phase_duration_ns * 1000)

        # Handle repeats
        repeat_count = 1
        if hasattr(phase, 'repeat') and phase.repeat:
            repeat_count = phase.repeat.get('count', 1)

        for repeat_idx in range(repeat_count):
            # Generate events for signals
            for sig in phase.signals:
                event = TraceEvent(
                    time_ps=current_time_ps + sig.delay_ps,
                    signal=sig.signal,
                    value=sig.value,
                    transition=sig.transition,
                    phase_name=phase.name
                )
                trace.add_event(event)

            # Generate assertion check events at end of phase
            for assertion in phase.assertions:
                event = TraceEvent(
                    time_ps=current_time_ps + phase_duration_ps,
                    signal="__ASSERTION__",
                    value=assertion.expression,
                    transition=TransitionType.HOLD,
                    phase_name=phase.name,
                    assertion_checked=assertion.description or assertion.expression
                )
                trace.add_event(event)

            current_time_ps += phase_duration_ps

    # Rebuild indexes after all events are added
    trace._rebuild_indexes()

    return trace