"""
Stage 2 Enhanced: Assertion Explainer and Stimulus Exporter.

Implements the full Stage 2 requirements from original design:
- Layered YAML description with repeat/phase/assertion
- Assertion-driven design with SVA-like properties
- Assertion physical meaning explanation
- Violation scenario analysis
- Stimulus export to Testbench
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum
from pathlib import Path


class AssertionType(Enum):
    """Types of assertions supported."""
    IMMEDIATE = "immediate"  # Combinational check
    DELAYED = "delayed"      # ##[min:max] style
    EVENTUAL = "eventual"    # Eventually true
    NEVER = "never"          # Must never happen
    IMPLIES = "implies"      # req |-> ack style


class ViolationSeverity(Enum):
    """Severity of a violation."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass
class ViolationScenario:
    """A scenario that would violate the assertion."""
    scenario_name: str
    description: str
    signal_values: Dict[str, Any] = field(default_factory=dict)
    timing_ns: Optional[float] = None
    severity: ViolationSeverity = ViolationSeverity.ERROR
    recovery_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "description": self.description,
            "signal_values": self.signal_values,
            "timing_ns": self.timing_ns,
            "severity": self.severity.value,
            "recovery_hint": self.recovery_hint
        }


@dataclass
class AssertionExplanation:
    """Complete explanation of an assertion."""
    assertion_id: str
    expression: str
    assertion_type: AssertionType

    # Physical meaning
    physical_meaning: str = ""
    design_intent: str = ""
    protocol_impact: str = ""

    # Timing characteristics
    min_delay_cycles: int = 0
    max_delay_cycles: Optional[int] = None
    clock_domain: str = "clk"

    # Violation analysis
    violation_scenarios: List[ViolationScenario] = field(default_factory=list)

    # Coverage
    covered_by_tests: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "expression": self.expression,
            "assertion_type": self.assertion_type.value,
            "physical_meaning": self.physical_meaning,
            "design_intent": self.design_intent,
            "protocol_impact": self.protocol_impact,
            "min_delay_cycles": self.min_delay_cycles,
            "max_delay_cycles": self.max_delay_cycles,
            "clock_domain": self.clock_domain,
            "violation_scenarios": [v.to_dict() for v in self.violation_scenarios],
            "covered_by_tests": self.covered_by_tests
        }

    def to_markdown(self) -> str:
        """Generate markdown documentation for this assertion."""
        md = f"### Assertion: {self.assertion_id}\n\n"
        md += f"**Type**: {self.assertion_type.value}\n\n"
        md += f"**Expression**: `{self.expression}`\n\n"

        if self.physical_meaning:
            md += f"**Physical Meaning**: {self.physical_meaning}\n\n"
        if self.design_intent:
            md += f"**Design Intent**: {self.design_intent}\n\n"
        if self.protocol_impact:
            md += f"**Protocol Impact**: {self.protocol_impact}\n\n"

        if self.min_delay_cycles or self.max_delay_cycles is not None:
            md += "**Timing**: "
            if self.max_delay_cycles is None:
                md += f"min {self.min_delay_cycles} cycles\n\n"
            else:
                md += f"[{self.min_delay_cycles}:{self.max_delay_cycles}] cycles\n\n"

        if self.violation_scenarios:
            md += "**Violation Scenarios**:\n\n"
            for v in self.violation_scenarios:
                md += f"- **{v.scenario_name}**: {v.description}\n"
                if v.signal_values:
                    md += f"  - Signal values: {v.signal_values}\n"
                if v.recovery_hint:
                    md += f"  - Recovery: {v.recovery_hint}\n"
            md += "\n"

        return md


class AssertionExplainer:
    """
    Explains the physical meaning of assertions and analyzes violation scenarios.

    Parses SVA-like expressions and generates human-readable explanations.
    """

    # Common assertion patterns and their meanings
    PATTERN_MEANINGS = {
        r'req\s*\|\->\s*##\[(\d+):(\d+)\]\s*ack': {
            "meaning": "请求(req)必须在指定周期范围内得到确认(ack)",
            "intent": "握手协议完成延迟约束",
            "protocol": "AXI-Stream/Avalon-ST握手规范"
        },
        r'req\s*\|\->\s*##(\d+)\s*ack': {
            "meaning": "请求(req)必须在精确N个周期后得到确认(ack)",
            "intent": "固定延迟握手协议",
            "protocol": "确定性延迟接口"
        },
        r'valid\s*&&\s*!ready\s*\|\->\s*valid': {
            "meaning": "valid拉高且ready未拉低时，valid必须保持",
            "intent": "AXI-Stream握手不变性",
            "protocol": "AXI-Stream协议"
        },
        r'^!\s*rst_n\s*\|\->': {
            "meaning": "复位信号有效时的行为约束",
            "intent": "复位状态保护",
            "protocol": "复位序列"
        },
        r'full': {
            "meaning": "FIFO满状态条件",
            "intent": "防止FIFO溢出",
            "protocol": "FIFO流控"
        },
        r'empty': {
            "meaning": "FIFO空状态条件",
            "intent": "防止FIFO下溢",
            "protocol": "FIFO流控"
        },
        r'wr_en': {
            "meaning": "写使能信号约束",
            "intent": "存储器写保护",
            "protocol": "存储器接口"
        },
        r'rd_en': {
            "meaning": "读使能信号约束",
            "intent": "存储器读保护",
            "protocol": "存储器接口"
        }
    }

    def __init__(self):
        self.explanations: Dict[str, AssertionExplanation] = {}

    def explain_assertion(
        self,
        assertion_id: str,
        expression: str,
        assertion_type: AssertionType = AssertionType.IMPLICES
    ) -> AssertionExplanation:
        """
        Explain an assertion's physical meaning.

        Args:
            assertion_id: Unique identifier for this assertion
            expression: SVA-like expression (e.g., "req |-> ##[1:3] ack")
            assertion_type: Type of assertion

        Returns:
            AssertionExplanation object with full analysis
        """
        explanation = AssertionExplanation(
            assertion_id=assertion_id,
            expression=expression,
            assertion_type=assertion_type
        )

        # Parse timing from expression
        self._parse_timing(explanation, expression)

        # Match against known patterns
        self._match_patterns(explanation, expression)

        # Generate violation scenarios
        self._generate_violation_scenarios(explanation)

        self.explanations[assertion_id] = explanation
        return explanation

    def _parse_timing(self, explanation: AssertionExplanation, expression: str):
        """Parse timing constraints from expression."""
        # Match ##[min:max] pattern
        range_match = re.search(r'##\[(\d+):(\d+)\]', expression)
        if range_match:
            explanation.min_delay_cycles = int(range_match.group(1))
            explanation.max_delay_cycles = int(range_match.group(2))
            explanation.assertion_type = AssertionType.DELAYED
            return

        # Match ##N pattern
        fixed_match = re.search(r'##(\d+)', expression)
        if fixed_match:
            explanation.min_delay_cycles = int(fixed_match.group(1))
            explanation.max_delay_cycles = int(fixed_match.group(1))
            explanation.assertion_type = AssertionType.DELAYED

    def _match_patterns(self, explanation: AssertionExplanation, expression: str):
        """Match expression against known patterns to derive meaning."""
        for pattern, info in self.PATTERN_MEANINGS.items():
            if re.search(pattern, expression):
                if not explanation.physical_meaning:
                    explanation.physical_meaning = info["meaning"]
                if not explanation.design_intent:
                    explanation.design_intent = info["intent"]
                if not explanation.protocol_impact:
                    explanation.protocol_impact = info["protocol"]

        # If no pattern matched, provide generic explanation
        if not explanation.physical_meaning:
            explanation.physical_meaning = "自定义协议断言 - 需要手动审查"

    def _generate_violation_scenarios(self, explanation: AssertionExplanation):
        """Generate possible violation scenarios."""
        expr = explanation.expression

        # Implication-style violation (req |-> ack)
        if "|->" in expr:
            parts = expr.split("|->")
            antecedent = parts[0].strip() if len(parts) > 0 else ""
            consequent = parts[1].strip() if len(parts) > 1 else ""

            # Extract signal names (simplified)
            ant_signals = self._extract_signals(antecedent)
            cons_signals = self._extract_signals(consequent)

            # Scenario 1: Antecedent true, consequent never true
            scenario1 = ViolationScenario(
                scenario_name="antecedent_true_consequent_never",
                description=f"{antecedent} 为真但 {consequent} 从未发生",
                signal_values={s: 1 for s in ant_signals},
                severity=ViolationSeverity.ERROR,
                recovery_hint=f"检查 {cons_signals} 的生成逻辑"
            )
            explanation.violation_scenarios.append(scenario1)

            # Scenario 2: Consequent too late (if timing constraints)
            if explanation.max_delay_cycles:
                scenario2 = ViolationScenario(
                    scenario_name="consequent_too_late",
                    description=f"{consequent} 发生但超过了 {explanation.max_delay_cycles} 周期的最大延迟",
                    timing_ns=explanation.max_delay_cycles * 10.0,  # Assume 100MHz for example
                    severity=ViolationSeverity.ERROR,
                    recovery_hint="考虑插入流水线寄存器或优化关键路径"
                )
                explanation.violation_scenarios.append(scenario2)

    def _extract_signals(self, expression: str) -> List[str]:
        """Extract signal names from an expression (simplified)."""
        # Remove SVA syntax
        clean = re.sub(r'##\[\d+:\d+\]', '', expression)
        clean = re.sub(r'##\d+', '', clean)
        clean = re.sub(r'[|-><+\-*/&|^~]', ' ', clean)

        # Extract words that look like signal names
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', clean)
        keywords = {'and', 'or', 'not', 'xor', 'xnor', 'nand', 'nor'}
        return [w for w in words if w.lower() not in keywords]

    def generate_documentation(self, output_path: Path):
        """Generate assertion documentation to a file."""
        md = "# Assertion Documentation\n\n"
        md += f"Generated: {__import__('datetime').datetime.now().isoformat()}\n\n"
        md += "---\n\n"

        for expl in self.explanations.values():
            md += expl.to_markdown()
            md += "---\n\n"

        output_path.write_text(md, encoding='utf-8')


# =============================================================================
# Stimulus Exporter - Export Golden Trace to Testbench
# =============================================================================

@dataclass
class StimulusTransaction:
    """A single transaction in the stimulus."""
    transaction_id: str
    time_ns: float
    signal_values: Dict[str, Any]
    description: str = ""

    def to_verilog(self) -> str:
        """Generate Verilog stimulus code for this transaction."""
        lines = []
        for signal, value in self.signal_values.items():
            if isinstance(value, int):
                # Determine bit width from value (simplified)
                width = max(1, value.bit_length())
                lines.append(f"        {signal} = {width}'d{value};")
            elif isinstance(value, str):
                lines.append(f"        {signal} = {value};")
            else:
                lines.append(f"        {signal} = {value};")
        return "\n".join(lines)


@dataclass
class StimulusConfig:
    """Configuration for stimulus generation."""
    time_unit: str = "1ns"
    time_precision: str = "1ps"
    clock_name: str = "clk"
    reset_name: str = "rst_n"
    clock_period_ns: float = 10.0
    reset_active_low: bool = True


class StimulusExporter:
    """
    Exports stimulus from Golden Trace to Verilog Testbench.

    Ensures Stage 4 stimulus is consistent with Stage 2 Golden Trace.
    """

    def __init__(self, config: Optional[StimulusConfig] = None):
        self.config = config or StimulusConfig()
        self.transactions: List[StimulusTransaction] = []

    def add_transaction(self, transaction: StimulusTransaction):
        """Add a transaction to the stimulus."""
        self.transactions.append(transaction)

    def load_from_golden_trace(self, golden_trace_json: Path):
        """Load stimulus from a Golden Trace JSON file."""
        with open(golden_trace_json, 'r') as f:
            data = json.load(f)

        for event in data.get('events', []):
            tx = StimulusTransaction(
                transaction_id=event.get('event_id', f"tx_{len(self.transactions)}"),
                time_ns=event.get('time_ps', 0) / 1000.0,  # ps to ns
                signal_values=event.get('signal_values', {}),
                description=event.get('description', '')
            )
            self.transactions.append(tx)

    def generate_testbench_stimulus(
        self,
        module_name: str,
        output_path: Path,
        include_clock_reset: bool = True
    ) -> str:
        """
        Generate Verilog testbench stimulus code.

        Returns:
            Verilog code as string
        """
        lines = []

        # Header
        lines.append("//")
        lines.append(f"// Stimulus for {module_name}")
        lines.append("// Auto-generated from Golden Trace")
        lines.append("//")
        lines.append("")

        if include_clock_reset:
            # Clock generation
            half_period = self.config.clock_period_ns / 2.0
            lines.append("    // Clock generation")
            lines.append(f"    initial begin")
            lines.append(f"        {self.config.clock_name} = 0;")
            lines.append(f"        forever #({half_period}) {self.config.clock_name} = ~{self.config.clock_name};")
            lines.append(f"    end")
            lines.append("")

            # Reset generation
            reset_val = 0 if self.config.reset_active_low else 1
            release_val = 1 if self.config.reset_active_low else 0
            lines.append("    // Reset sequence")
            lines.append(f"    initial begin")
            lines.append(f"        {self.config.reset_name} = {reset_val};")
            lines.append(f"        #(100);")
            lines.append(f"        {self.config.reset_name} = {release_val};")
            lines.append(f"    end")
            lines.append("")

        # Stimulus application
        lines.append("    // Stimulus from Golden Trace")
        lines.append("    initial begin")
        lines.append("        // Wait for reset release")
        lines.append("        @(posedge clk);")
        lines.append("        @(posedge clk);")
        lines.append("")

        # Group transactions by time
        tx_by_time: Dict[float, List[StimulusTransaction]] = {}
        for tx in self.transactions:
            if tx.time_ns not in tx_by_time:
                tx_by_time[tx.time_ns] = []
            tx_by_time[tx.time_ns].append(tx)

        prev_time = 0.0
        for time_ns in sorted(tx_by_time.keys()):
            delay = time_ns - prev_time
            if delay > 0:
                lines.append(f"        #({delay});")

            lines.append(f"        // Time: {time_ns}ns")
            for tx in tx_by_time[time_ns]:
                if tx.description:
                    lines.append(f"        // {tx.description}")
                lines.append(tx.to_verilog())
            lines.append("")
            prev_time = time_ns

        lines.append("        // End of stimulus")
        lines.append("        #1000;")
        lines.append('        $display("Stimulus complete");')
        lines.append("        $finish;")
        lines.append("    end")

        content = "\n".join(lines)
        output_path.write_text(content, encoding='utf-8')
        return content

    def generate_include_file(self, output_path: Path) -> str:
        """Generate a Verilog include file with stimulus tasks."""
        lines = []
        lines.append("//")
        lines.append("// Stimulus Tasks Include File")
        lines.append("//")
        lines.append("")

        for i, tx in enumerate(self.transactions):
            lines.append(f"task apply_transaction_{i};")
            lines.append("    begin")
            lines.append(tx.to_verilog())
            lines.append("    end")
            lines.append("endtask")
            lines.append("")

        content = "\n".join(lines)
        output_path.write_text(content, encoding='utf-8')
        return content


# =============================================================================
# Schema Validator for Stage 2 YAML
# =============================================================================

class Stage2SchemaValidator:
    """
    Validates Stage 2 YAML timing scenarios against schema.

    Ensures the YAML has all required fields before proceeding to Stage 3.
    """

    REQUIRED_SCENARIO_FIELDS = [
        "scenario_id",
        "name",
        "description",
        "clocks",
        "phases"
    ]

    REQUIRED_PHASE_FIELDS = [
        "name",
        "duration_ns"
    ]

    @classmethod
    def validate_scenario(cls, scenario_data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate a timing scenario.

        Returns:
            (is_valid, errors, warnings)
        """
        errors = []
        warnings = []

        # Check required fields
        for field in cls.REQUIRED_SCENARIO_FIELDS:
            if field not in scenario_data:
                errors.append(f"Missing required field: {field}")

        # Check clocks
        if "clocks" in scenario_data:
            if not scenario_data["clocks"]:
                warnings.append("No clocks defined in scenario")
            else:
                for clock_name, clock_def in scenario_data["clocks"].items():
                    if "period_ns" not in clock_def and "frequency_mhz" not in clock_def:
                        warnings.append(f"Clock {clock_name} has no period/frequency defined")

        # Check phases
        if "phases" in scenario_data:
            phases = scenario_data["phases"]
            if not phases:
                errors.append("No phases defined in scenario")
            else:
                for i, phase in enumerate(phases):
                    for field in cls.REQUIRED_PHASE_FIELDS:
                        if field not in phase:
                            errors.append(f"Phase {i} missing required field: {field}")

                    # Check for repeat structure if present
                    if "repeat" in phase:
                        repeat = phase["repeat"]
                        if "count" not in repeat:
                            warnings.append(f"Phase {i} repeat has no count")

        # Check assertions if present
        if "assertions" in scenario_data:
            for i, assertion in enumerate(scenario_data["assertions"]):
                if "expression" not in assertion:
                    warnings.append(f"Assertion {i} has no expression")

        is_valid = len(errors) == 0
        return is_valid, errors, warnings
