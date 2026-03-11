"""YAML DSL Schema validation for Stage 2."""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import jsonschema
from jsonschema import validate, ValidationError as JsonSchemaError


# JSON Schema for YAML DSL validation
YAML_DSL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["scenario", "clocks", "phases"],
    "properties": {
        "scenario_id": {
            "type": "string",
            "description": "Unique identifier for this scenario"
        },
        "scenario": {
            "type": "string",
            "description": "Human-readable scenario name"
        },
        "description": {
            "type": "string"
        },
        "parameters": {
            "type": "object",
            "additionalProperties": True
        },
        "clocks": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {
                "type": "object",
                "required": ["period"],
                "properties": {
                    "period": {
                        "type": "string",
                        "pattern": r"^\\d+(\\.\\d+)?(ns|ps|us|ms)$"
                    },
                    "jitter": {
                        "type": "string"
                    },
                    "duty_cycle": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100
                    }
                }
            }
        },
        "phases": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string"
                    },
                    "duration_ns": {
                        "type": "number",
                        "minimum": 0
                    },
                    "repeat": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "minimum": 1
                            },
                            "var": {
                                "type": "string"
                            }
                        }
                    },
                    "signals": {
                        "type": "object",
                        "additionalProperties": {
                            "oneOf": [
                                {"type": "integer"},
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "value": {},
                                        "transition": {"type": "string"},
                                        "delay_ps": {"type": "integer"}
                                    }
                                }
                            ]
                        }
                    },
                    "assertions": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "required": ["expression"],
                                    "properties": {
                                        "type": {"type": "string"},
                                        "expression": {"type": "string"},
                                        "description": {"type": "string"},
                                        "severity": {"type": "string"}
                                    }
                                }
                            ]
                        }
                    },
                    "description": {"type": "string"}
                }
            }
        },
        "global_assertions": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "required": ["expression"],
                        "properties": {
                            "type": {"type": "string"},
                            "expression": {"type": "string"},
                            "description": {"type": "string"}
                        }
                    }
                ]
            }
        }
    }
}


@dataclass
class ValidationResult:
    """Result of YAML DSL validation."""
    valid: bool
    errors: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, path: str, message: str, schema_path: str = ""):
        """Add an error to the result."""
        self.errors.append({
            "path": path,
            "message": message,
            "schema_path": schema_path
        })
        self.valid = False

    def add_warning(self, message: str):
        """Add a warning to the result."""
        self.warnings.append(message)

    def to_dict(self) -> Dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


def validate_scenario(data: Dict, strict: bool = True) -> ValidationResult:
    """Validate a YAML timing scenario against the schema.

    Args:
        data: Parsed YAML data as dictionary
        strict: If True, treat warnings as errors

    Returns:
        ValidationResult with validation status and details
    """
    result = ValidationResult(valid=True)

    try:
        validate(instance=data, schema=YAML_DSL_SCHEMA)
    except JsonSchemaError as e:
        result.add_error(
            path="/".join(str(p) for p in e.path),
            message=e.message,
            schema_path="/".join(str(p) for p in e.schema_path)
        )
        return result

    # Additional semantic validation
    _validate_semantics(data, result)

    if strict and result.warnings:
        result.valid = False

    return result


def _validate_semantics(data: Dict, result: ValidationResult):
    """Perform semantic validation beyond schema checks."""
    # Check clock period consistency
    clocks = data.get("clocks", {})
    for clock_name, clock_config in clocks.items():
        period_str = clock_config.get("period", "")
        # Extract numeric value from period string (e.g., "5ns" -> 5)
        import re
        match = re.match(r"(\d+(?:\.\d+)?)", period_str)
        if match:
            period_val = float(match.group(1))
            if period_val <= 0:
                result.add_error(
                    path=f"clocks/{clock_name}/period",
                    message=f"Clock period must be positive, got {period_val}"
                )

    # Check phase durations
    phases = data.get("phases", [])
    for i, phase in enumerate(phases):
        duration = phase.get("duration_ns", 0)
        if duration < 0:
            result.add_error(
                path=f"phases/{i}/duration_ns",
                message=f"Phase duration must be non-negative, got {duration}"
            )

    # Check for signal name consistency
    all_signals = set()
    for phase in phases:
        signals = phase.get("signals", {})
        all_signals.update(signals.keys())

    # Warn about undefined signals in assertions
    for i, phase in enumerate(phases):
        assertions = phase.get("assertions", [])
        for j, assertion in enumerate(assertions):
            if isinstance(assertion, dict):
                expr = assertion.get("expression", "")
            else:
                expr = str(assertion)

            # Simple check for signal references
            for sig in all_signals:
                if sig in expr and sig not in ["full", "empty"]:  # Common signal names
                    break
            else:
                # No known signals referenced
                if any(keyword in expr.lower() for keyword in ["==", "!=", ">", "<"]):
                    result.add_warning(
                        f"Assertion in phase {i}, assertion {j} may reference undefined signals: {expr}"
                    )


def load_schema() -> Dict:
    """Get the YAML DSL JSON Schema."""
    return YAML_DSL_SCHEMA


def save_schema(output_path: Path):
    """Save the schema to a file."""
    with open(output_path, 'w') as f:
        json.dump(YAML_DSL_SCHEMA, f, indent=2)