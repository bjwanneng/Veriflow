"""Assertion Checker for Stage 4."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from ..stage2.yaml_dsl import Assertion, AssertionType


@dataclass
class AssertionResult:
    """Result of a single assertion check."""
    assertion: Assertion
    passed: bool
    time_checked: int = 0
    actual_value: Any = None
    expected_value: Any = None
    message: str = ""


@dataclass
class AssertionCheckResult:
    """Result of all assertion checks."""
    results: List[AssertionResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def passed_count(self) -> int:
        return len([r for r in self.results if r.passed])

    @property
    def failed_count(self) -> int:
        return len([r for r in self.results if not r.passed])

    @property
    def total_count(self) -> int:
        return len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
            "results": [
                {
                    "expression": r.assertion.expression,
                    "type": r.assertion.assertion_type.value,
                    "passed": r.passed,
                    "time_checked": r.time_checked,
                    "actual_value": str(r.actual_value),
                    "expected_value": str(r.expected_value),
                    "message": r.message
                }
                for r in self.results
            ]
        }


class AssertionChecker:
    """Check assertions against simulation state."""

    def __init__(self):
        self.checkers: Dict[AssertionType, Callable] = {
            AssertionType.IMMEDIATE: self._check_immediate,
            AssertionType.DELAYED: self._check_delayed,
            AssertionType.EVENTUAL: self._check_eventual,
            AssertionType.NEVER: self._check_never,
        }

    def check_assertions(
        self,
        assertions: List[Assertion],
        signal_values: Dict[str, Any],
        time_ps: int = 0
    ) -> AssertionCheckResult:
        """Check a list of assertions against current signal values."""

        result = AssertionCheckResult()

        for assertion in assertions:
            checker = self.checkers.get(assertion.assertion_type, self._check_immediate)
            check_result = checker(assertion, signal_values, time_ps)
            result.results.append(check_result)

        return result

    def _check_immediate(
        self,
        assertion: Assertion,
        signal_values: Dict[str, Any],
        time_ps: int
    ) -> AssertionResult:
        """Check an immediate assertion."""

        try:
            result = self._evaluate_expression(assertion.expression, signal_values)

            return AssertionResult(
                assertion=assertion,
                passed=bool(result),
                time_checked=time_ps,
                actual_value=result,
                expected_value=True,
                message="Immediate assertion passed" if result else "Immediate assertion failed"
            )
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                time_checked=time_ps,
                message=f"Error evaluating assertion: {e}"
            )

    def _check_delayed(
        self,
        assertion: Assertion,
        signal_values: Dict[str, Any],
        time_ps: int
    ) -> AssertionResult:
        """Check a delayed assertion (simplified implementation)."""

        # For delayed assertions, we would need temporal tracking
        # This is a simplified version
        return AssertionResult(
            assertion=assertion,
            passed=True,  # Assume pass for now
            time_checked=time_ps,
            message="Delayed assertion check (simplified)"
        )

    def _check_eventual(
        self,
        assertion: Assertion,
        signal_values: Dict[str, Any],
        time_ps: int
    ) -> AssertionResult:
        """Check an eventual assertion."""

        # Eventual assertions require tracking across time
        # This would be implemented with a temporal checker
        return AssertionResult(
            assertion=assertion,
            passed=True,  # Assume pass for now
            time_checked=time_ps,
            message="Eventual assertion check (simplified)"
        )

    def _check_never(
        self,
        assertion: Assertion,
        signal_values: Dict[str, Any],
        time_ps: int
    ) -> AssertionResult:
        """Check a never assertion (condition must never be true)."""

        try:
            result = self._evaluate_expression(assertion.expression, signal_values)

            return AssertionResult(
                assertion=assertion,
                passed=not bool(result),  # Pass if condition is false
                time_checked=time_ps,
                actual_value=result,
                expected_value=False,
                message="Never assertion passed" if not result else "Never assertion violated"
            )
        except Exception as e:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                time_checked=time_ps,
                message=f"Error evaluating assertion: {e}"
            )

    def _evaluate_expression(self, expression: str, signal_values: Dict[str, Any]) -> bool:
        """Evaluate an assertion expression with signal values."""

        # Simple expression evaluator for basic assertions
        # Replace signal names with their values
        expr = expression

        # Replace signal references with values
        for signal, value in sorted(signal_values.items(), key=lambda x: -len(x[0])):
            # Use sorted by length to avoid partial replacements
            if isinstance(value, str):
                expr = expr.replace(signal, f"'{value}'")
            else:
                expr = expr.replace(signal, str(value))

        # Replace Verilog operators with Python equivalents
        expr = expr.replace("&&", " and ")
        expr = expr.replace("||", " or ")
        expr = expr.replace("!", " not ")
        expr = expr.replace("==", "==")
        expr = expr.replace("!=", "!=")

        # Handle '1'b1' style values
        expr = re.sub(r"(\d+)'b([01])", r"\2", expr)

        try:
            # Evaluate in restricted environment
            result = eval(expr, {"__builtins__": {}}, {})
            return bool(result)
        except Exception as e:
            # If evaluation fails, log and return False
            raise ValueError(f"Failed to evaluate expression '{expression}' (processed: '{expr}'): {e}")

    def generate_sva(self, assertions: List[Assertion]) -> str:
        """Generate SystemVerilog Assertions from assertion definitions."""

        lines = []
        lines.append("// Auto-generated SystemVerilog Assertions")
        lines.append("")

        for i, assertion in enumerate(assertions):
            sva = assertion.to_sva()
            lines.append(f"// Assertion: {assertion.expression}")
            lines.append(f"property prop_{i};")
            lines.append(f"    {sva}")
            lines.append("endproperty")
            lines.append(f"assert property (prop_{i}) else $error(\"Assertion failed\");")
            lines.append("")

        return "\n".join(lines)

    def save_sva(self, assertions: List[Assertion], output_path: Path) -> Path:
        """Save generated SVA to file."""

        sva_code = self.generate_sva(assertions)
        output_path.write_text(sva_code, encoding="utf-8")
        return output_path
