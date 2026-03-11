"""YAML DSL for timing scenario description (Stage 2)."""

import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import yaml


class TransitionType(Enum):
    """Signal transition types."""
    RISE = "rise"
    FALL = "fall"
    TOGGLE = "toggle"
    HOLD = "hold"
    HIGH = "high"
    LOW = "low"


class AssertionType(Enum):
    """Types of assertions supported."""
    IMMEDIATE = "immediate"  # Combinational check
    DELAYED = "delayed"      # ##[min:max] style
    EVENTUAL = "eventual"    # Eventually true
    NEVER = "never"          # Must never happen


@dataclass
class SignalTransition:
    """A single signal transition in a phase."""
    signal: str
    value: Union[int, str]  # Can be 0, 1, expression like "$i * 2"
    transition: TransitionType = TransitionType.HOLD
    delay_ps: int = 0  # Delay from phase start in picoseconds

    def to_dict(self) -> Dict:
        return {
            "signal": self.signal,
            "value": self.value,
            "transition": self.transition.value,
            "delay_ps": self.delay_ps
        }


@dataclass
class Assertion:
    """An assertion to check during simulation."""
    assertion_type: AssertionType
    expression: str  # e.g., "full == 0 until i == $DEPTH-1"
    description: str = ""
    min_delay: int = 0  # For DELAYED type
    max_delay: Optional[int] = None
    severity: str = "error"  # error, warning, info

    def __post_init__(self):
        """Parse expression for physical meaning."""
        self.physical_meaning = self._derive_physical_meaning()

    def _derive_physical_meaning(self) -> str:
        """Derive physical meaning from assertion expression."""
        meanings = []

        # Check for common patterns
        if "full" in self.expression.lower():
            meanings.append("FIFO full condition - backpressure handling")
        if "empty" in self.expression.lower():
            meanings.append("FIFO empty condition - underrun prevention")
        if "valid" in self.expression.lower():
            meanings.append("Data valid handshake protocol")
        if "ready" in self.expression.lower():
            meanings.append("Flow control ready signal")
        if "ack" in self.expression.lower():
            meanings.append("Acknowledgment response timing")

        if not meanings:
            return "Custom protocol assertion - review manually"

        return "; ".join(meanings)

    def to_dict(self) -> Dict:
        return {
            "type": self.assertion_type.value,
            "expression": self.expression,
            "description": self.description,
            "physical_meaning": getattr(self, "physical_meaning", ""),
            "severity": self.severity
        }

    def to_sva(self) -> str:
        """Convert to SystemVerilog Assertion format."""
        if self.assertion_type == AssertionType.IMMEDIATE:
            return f"assert property ({self.expression});"
        elif self.assertion_type == AssertionType.DELAYED:
            max_d = f":{self.max_delay}" if self.max_delay else ""
            return f"assert property ({self.expression} |-> ##[{self.min_delay}{max_d}] {self.expression});"
        else:
            return f"// TODO: Convert assertion: {self.expression}"


@dataclass
class Phase:
    """A phase in the timing scenario."""
    name: str
    duration_ns: float
    repeat: Optional[Dict] = None  # {count: int, var: str}
    signals: List[SignalTransition] = field(default_factory=list)
    assertions: List[Assertion] = field(default_factory=list)
    description: str = ""

    def expand_repeats(self) -> List["Phase"]:
        """Expand phases with repeat count."""
        if not self.repeat:
            return [self]

        count = self.repeat.get("count", 1)
        var = self.repeat.get("var", "i")

        phases = []
        for i in range(count):
            # Create a copy with variable substitution
            phase_copy = Phase(
                name=f"{self.name}_{i}",
                duration_ns=self.duration_ns,
                signals=self._substitute_vars(self.signals, var, i),
                assertions=self.assertions,
                description=self.description
            )
            phases.append(phase_copy)

        return phases

    def _substitute_vars(self, signals: List[SignalTransition], var: str, value: int) -> List[SignalTransition]:
        """Substitute variable references in signal values."""
        result = []
        for sig in signals:
            new_value = sig.value
            if isinstance(sig.value, str):
                # Simple variable substitution
                new_value = sig.value.replace(f"${var}", str(value))
                # Simple arithmetic evaluation (e.g., "$i * 2")
                try:
                    if new_value.startswith("$"):
                        expr = new_value[1:].replace(var, str(value))
                        new_value = eval(expr)
                except:
                    pass

            result.append(SignalTransition(
                signal=sig.signal,
                value=new_value,
                transition=sig.transition,
                delay_ps=sig.delay_ps
            ))
        return result

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "duration_ns": self.duration_ns,
            "repeat": self.repeat,
            "signals": [s.to_dict() for s in self.signals],
            "assertions": [a.to_dict() for a in self.assertions],
            "description": self.description
        }


@dataclass
class TimingScenario:
    """Complete timing scenario for Stage 2."""
    scenario_id: str
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    clocks: Dict[str, Dict] = field(default_factory=dict)
    phases: List[Phase] = field(default_factory=list)
    global_assertions: List[Assertion] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "clocks": self.clocks,
            "phases": [p.to_dict() for p in self.phases],
            "global_assertions": [a.to_dict() for a in self.global_assertions]
        }

    def to_yaml(self) -> str:
        """Export to YAML format."""
        import yaml
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)


# YAML Parsing Functions

def parse_yaml_scenario(yaml_content: str) -> TimingScenario:
    """Parse a YAML timing scenario."""
    import yaml

    data = yaml.safe_load(yaml_content)

    # Parse phases
    phases = []
    for phase_data in data.get("phases", []):
        # Parse signals
        signals = []
        for sig_name, sig_value in phase_data.get("signals", {}).items():
            if isinstance(sig_value, dict):
                signals.append(SignalTransition(
                    signal=sig_name,
                    value=sig_value.get("value", 0),
                    transition=TransitionType(sig_value.get("transition", "hold")),
                    delay_ps=sig_value.get("delay_ps", 0)
                ))
            else:
                signals.append(SignalTransition(
                    signal=sig_name,
                    value=sig_value
                ))

        # Parse assertions
        assertions = []
        for assertion_data in phase_data.get("assertions", []):
            if isinstance(assertion_data, str):
                assertions.append(Assertion(
                    assertion_type=AssertionType.IMMEDIATE,
                    expression=assertion_data
                ))
            else:
                assertions.append(Assertion(
                    assertion_type=AssertionType(assertion_data.get("type", "immediate")),
                    expression=assertion_data["expression"],
                    description=assertion_data.get("description", ""),
                    severity=assertion_data.get("severity", "error")
                ))

        phase = Phase(
            name=phase_data["name"],
            duration_ns=phase_data.get("duration_ns", 10.0),
            repeat=phase_data.get("repeat"),
            signals=signals,
            assertions=assertions,
            description=phase_data.get("description", "")
        )
        phases.append(phase)

    # Create scenario
    scenario = TimingScenario(
        scenario_id=data.get("scenario_id", f"scen_{hash(yaml_content) % 10000}"),
        name=data.get("scenario", "Unnamed Scenario"),
        description=data.get("description", ""),
        parameters=data.get("parameters", {}),
        clocks=data.get("clocks", {}),
        phases=phases,
        global_assertions=[]
    )

    return scenario