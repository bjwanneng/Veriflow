"""Pre-generation requirement validator — shift-left error detection.

Runs BEFORE any code generation to catch:
- Contradictions in requirements (latency vs pipeline depth)
- Constraint feasibility (frequency vs combinational depth)
- Resource estimates (LUT/BRAM/FF projections)
- Spec internal consistency (port mismatches, missing connections)

v5.0: New module implementing Shift-Left strategy.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ValidationFinding:
    """A single pre-generation validation finding."""
    category: str   # "contradiction" | "feasibility" | "resource" | "consistency"
    severity: str   # "error" | "warning" | "info"
    message: str
    suggestion: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceEstimate:
    """Projected resource usage for a design."""
    lut_count: int = 0
    ff_count: int = 0
    bram_count: int = 0
    dsp_count: int = 0
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.lut_count:
            parts.append(f"~{self.lut_count} LUTs")
        if self.ff_count:
            parts.append(f"~{self.ff_count} FFs")
        if self.bram_count:
            parts.append(f"~{self.bram_count} BRAMs")
        if self.dsp_count:
            parts.append(f"~{self.dsp_count} DSPs")
        return ", ".join(parts) if parts else "No estimate available"


@dataclass
class PreCheckReport:
    """Complete pre-generation validation report."""
    findings: List[ValidationFinding] = field(default_factory=list)
    resource_estimate: Optional[ResourceEstimate] = None
    passed: bool = True

    @property
    def errors(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[ValidationFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in self.findings
            ],
            "resource_estimate": (
                self.resource_estimate.summary()
                if self.resource_estimate else None
            ),
        }


class RequirementValidator:
    """Validate requirements and spec before code generation.

    Usage:
        validator = RequirementValidator()
        report = validator.validate_spec(spec_data)
        if not report.passed:
            # Block Stage 1 -> Stage 3 transition
            for finding in report.errors:
                print(f"[ERROR] {finding.message}")
    """

    # Typical combinational delay per logic level (ns) for modern FPGAs
    DELAY_PER_LEVEL_NS = 0.3
    # Typical setup time (ns)
    SETUP_TIME_NS = 0.1
    # LUT cost estimates per operation type
    RESOURCE_COSTS = {
        "sbox_rom": {"lut": 64, "ff": 0, "bram": 0},
        "sbox_ram": {"lut": 0, "ff": 0, "bram": 1},
        "sbox_lutram": {"lut": 64, "ff": 0, "bram": 0},
        "mixcolumns": {"lut": 108, "ff": 0, "bram": 0},
        "addroundkey": {"lut": 128, "ff": 0, "bram": 0},
        "shiftrows": {"lut": 0, "ff": 0, "bram": 0},
        "key_expand_round": {"lut": 200, "ff": 128, "bram": 0},
        "pipeline_register_128b": {"lut": 0, "ff": 128, "bram": 0},
    }

    def validate_spec(self, spec_data: Dict[str, Any]) -> PreCheckReport:
        """Run all pre-generation checks on a spec JSON.

        Args:
            spec_data: Parsed spec JSON (from stage_1_spec/*.json)

        Returns:
            PreCheckReport with findings and resource estimates
        """
        report = PreCheckReport()

        self._check_latency_consistency(spec_data, report)
        self._check_frequency_feasibility(spec_data, report)
        self._check_port_consistency(spec_data, report)
        self._check_pipeline_completeness(spec_data, report)
        self._check_module_connectivity(spec_data, report)
        self._check_crypto_constraints(spec_data, report)
        self._estimate_resources(spec_data, report)

        report.passed = len(report.errors) == 0
        return report

    def validate_requirement_text(self, requirement: str,
                                   spec_data: Dict[str, Any]) -> PreCheckReport:
        """Cross-check natural language requirement against generated spec.

        Detects mismatches between what the user asked for and what the spec defines.
        """
        report = PreCheckReport()
        req_lower = requirement.lower()

        # Check pipeline depth claim vs spec
        pipeline_stages = spec_data.get("pipeline_stages", [])
        stage_count = len(pipeline_stages)

        # Look for latency claims in requirement text
        import re
        latency_match = re.search(
            r'(?:latency|delay)\s*[:=]?\s*(\d+)\s*(?:cycle|clock|clk|stage)',
            req_lower
        )
        if latency_match:
            claimed_latency = int(latency_match.group(1))
            if stage_count > 0 and abs(claimed_latency - stage_count) > 2:
                report.findings.append(ValidationFinding(
                    category="contradiction",
                    severity="warning",
                    message=(
                        f"Requirement claims {claimed_latency}-cycle latency, "
                        f"but spec defines {stage_count} pipeline stages"
                    ),
                    suggestion=(
                        "Verify whether S-Box lookup adds extra pipeline stages. "
                        f"Expected latency: {stage_count} to {stage_count + 3} cycles"
                    ),
                ))

        # Check frequency claim vs spec
        freq_match = re.search(r'(\d+)\s*mhz', req_lower)
        spec_freq = spec_data.get("target_frequency_mhz", 0)
        if freq_match and spec_freq:
            claimed_freq = int(freq_match.group(1))
            if abs(claimed_freq - spec_freq) > 10:
                report.findings.append(ValidationFinding(
                    category="contradiction",
                    severity="error",
                    message=(
                        f"Requirement specifies {claimed_freq} MHz, "
                        f"but spec target is {spec_freq} MHz"
                    ),
                    suggestion="Align spec target_frequency_mhz with requirement",
                ))

        report.passed = len(report.errors) == 0
        return report

    # ── Internal check methods ───────────────────────────────────────

    def _check_latency_consistency(self, spec: Dict, report: PreCheckReport):
        """Verify pipeline stage count matches latency claims."""
        stages = spec.get("pipeline_stages", [])
        timing = spec.get("timing_constraints", {})

        if not stages:
            return

        stage_count = len(stages)

        # Check for duplicate stage IDs
        stage_ids = [s.get("stage_id", -1) for s in stages]
        if len(set(stage_ids)) != len(stage_ids):
            report.findings.append(ValidationFinding(
                category="consistency",
                severity="error",
                message="Duplicate stage_id values in pipeline_stages",
                suggestion="Each pipeline stage must have a unique stage_id",
            ))

        # Check stage ID continuity
        sorted_ids = sorted(stage_ids)
        if sorted_ids != list(range(sorted_ids[0], sorted_ids[0] + len(sorted_ids))):
            report.findings.append(ValidationFinding(
                category="consistency",
                severity="warning",
                message=f"Pipeline stage IDs are not contiguous: {sorted_ids}",
                suggestion="Use contiguous stage IDs starting from 0",
            ))

    def _check_frequency_feasibility(self, spec: Dict, report: PreCheckReport):
        """Check if target frequency is achievable given logic depth."""
        freq = spec.get("target_frequency_mhz", 0)
        if not freq:
            return

        clock_period = 1000.0 / freq
        timing = spec.get("timing_constraints", {})
        setup = timing.get("setup_ns", self.SETUP_TIME_NS)

        # Available time for combinational logic
        available_ns = clock_period - setup

        # Estimate worst-case logic depth per pipeline stage
        stages = spec.get("pipeline_stages", [])
        for stage in stages:
            ops = stage.get("operations", [])
            # Rough estimate: each operation adds 2-5 logic levels
            estimated_levels = len(ops) * 3
            estimated_delay = estimated_levels * self.DELAY_PER_LEVEL_NS

            if estimated_delay > available_ns:
                report.findings.append(ValidationFinding(
                    category="feasibility",
                    severity="warning",
                    message=(
                        f"Stage '{stage.get('name', '?')}' has ~{len(ops)} operations, "
                        f"estimated delay {estimated_delay:.1f} ns > "
                        f"available {available_ns:.1f} ns at {freq} MHz"
                    ),
                    suggestion=(
                        "Consider splitting this stage or reducing combinational depth. "
                        "SubBytes + MixColumns in one stage is typically the bottleneck."
                    ),
                    details={
                        "stage_name": stage.get("name"),
                        "estimated_delay_ns": estimated_delay,
                        "available_ns": available_ns,
                    },
                ))

    def _check_port_consistency(self, spec: Dict, report: PreCheckReport):
        """Check port definitions for internal consistency."""
        modules = spec.get("modules", [])

        for mod in modules:
            mod_name = mod.get("name", "unknown")
            ports = mod.get("ports", [])

            # Check for duplicate port names
            port_names = [p.get("name", "") for p in ports]
            seen: Set[str] = set()
            for pn in port_names:
                if pn in seen:
                    report.findings.append(ValidationFinding(
                        category="consistency",
                        severity="error",
                        message=f"Module '{mod_name}' has duplicate port '{pn}'",
                        suggestion="Remove or rename the duplicate port",
                    ))
                seen.add(pn)

            # Check port widths are positive
            for port in ports:
                width = port.get("width", 0)
                if width <= 0:
                    report.findings.append(ValidationFinding(
                        category="consistency",
                        severity="error",
                        message=(
                            f"Module '{mod_name}' port '{port.get('name')}' "
                            f"has invalid width: {width}"
                        ),
                        suggestion="Port width must be a positive integer",
                    ))

            # Check direction values
            valid_dirs = {"input", "output", "inout"}
            for port in ports:
                direction = port.get("direction", "")
                if direction not in valid_dirs:
                    report.findings.append(ValidationFinding(
                        category="consistency",
                        severity="error",
                        message=(
                            f"Module '{mod_name}' port '{port.get('name')}' "
                            f"has invalid direction: '{direction}'"
                        ),
                        suggestion=f"Use one of: {valid_dirs}",
                    ))

    def _check_pipeline_completeness(self, spec: Dict, report: PreCheckReport):
        """Verify all pipeline stages have required operations."""
        stages = spec.get("pipeline_stages", [])
        if not stages:
            return

        for stage in stages:
            ops = stage.get("operations", [])
            if not ops:
                report.findings.append(ValidationFinding(
                    category="consistency",
                    severity="warning",
                    message=(
                        f"Pipeline stage '{stage.get('name', '?')}' "
                        f"(id={stage.get('stage_id')}) has no operations defined"
                    ),
                    suggestion="Every pipeline stage should list its operations",
                ))

    def _check_module_connectivity(self, spec: Dict, report: PreCheckReport):
        """Check that all non-top modules are referenced by the top module."""
        modules = spec.get("modules", [])
        if len(modules) <= 1:
            return

        module_names = {m.get("name", "") for m in modules}
        top_modules = [m for m in modules if m.get("module_type") == "top"]

        if not top_modules:
            report.findings.append(ValidationFinding(
                category="consistency",
                severity="warning",
                message="No module with module_type='top' found in spec",
                suggestion="Designate one module as the top-level module",
            ))

    def _check_crypto_constraints(self, spec: Dict, report: PreCheckReport):
        """Crypto-specific checks (byte order, S-Box consistency)."""
        byte_order = spec.get("byte_order")
        modules = spec.get("modules", [])

        # Check if crypto modules exist but byte_order is not specified
        crypto_keywords = {"sbox", "subbytes", "mixcolumns", "addroundkey",
                           "shiftrows", "key_expand", "aes", "des", "cipher"}
        has_crypto = any(
            any(kw in m.get("name", "").lower() for kw in crypto_keywords)
            for m in modules
        )

        if has_crypto and not byte_order:
            report.findings.append(ValidationFinding(
                category="consistency",
                severity="warning",
                message="Crypto modules detected but no byte_order field in spec",
                suggestion=(
                    "Add byte_order: 'MSB_FIRST' or 'LSB_FIRST' to the spec. "
                    "This prevents byte-mapping bugs in SubBytes/MixColumns."
                ),
            ))

        # Check S-Box symmetry (forward + inverse)
        sbox_modules = [m for m in modules if "sbox" in m.get("name", "").lower()]
        has_forward = any("inv" not in m.get("name", "").lower() for m in sbox_modules)
        has_inverse = any("inv" in m.get("name", "").lower() for m in sbox_modules)

        if has_forward and not has_inverse:
            report.findings.append(ValidationFinding(
                category="consistency",
                severity="warning",
                message="Forward S-Box found but no inverse S-Box module",
                suggestion="Add inverse S-Box for decryption support",
            ))

    def _estimate_resources(self, spec: Dict, report: PreCheckReport):
        """Estimate FPGA resource usage from spec."""
        modules = spec.get("modules", [])
        stages = spec.get("pipeline_stages", [])
        estimate = ResourceEstimate()

        for mod in modules:
            name = mod.get("name", "").lower()
            ports = mod.get("ports", [])

            # S-Box estimation
            if "sbox" in name and "ram" in name:
                # RAM-based S-Box: 256x8 = 1 BRAM or 64 LUTs (LUTRAM)
                estimate.lut_count += 64
                estimate.notes.append(f"{mod.get('name')}: ~64 LUTs (LUTRAM 256x8)")
            elif "sbox" in name:
                estimate.lut_count += 64
                estimate.notes.append(f"{mod.get('name')}: ~64 LUTs (combinational)")

            # MixColumns estimation
            elif "mixcolumns" in name:
                estimate.lut_count += self.RESOURCE_COSTS["mixcolumns"]["lut"]
                estimate.notes.append(f"{mod.get('name')}: ~108 LUTs (GF multiply)")

            # AddRoundKey estimation
            elif "addroundkey" in name:
                estimate.lut_count += self.RESOURCE_COSTS["addroundkey"]["lut"]

            # Key expansion estimation
            elif "key_expand" in name:
                cost = self.RESOURCE_COSTS["key_expand_round"]
                # One key expansion per round
                num_rounds = len(stages) if stages else 10
                estimate.lut_count += cost["lut"] * num_rounds
                estimate.ff_count += cost["ff"] * num_rounds
                estimate.notes.append(
                    f"{mod.get('name')}: ~{cost['lut'] * num_rounds} LUTs, "
                    f"~{cost['ff'] * num_rounds} FFs ({num_rounds} rounds)"
                )

        # Pipeline registers
        if stages:
            reg_cost = self.RESOURCE_COSTS["pipeline_register_128b"]
            total_ff = reg_cost["ff"] * len(stages)
            estimate.ff_count += total_ff
            estimate.notes.append(
                f"Pipeline registers: ~{total_ff} FFs ({len(stages)} stages x 128b)"
            )

        report.resource_estimate = estimate

        # Warn if resource usage seems high
        if estimate.lut_count > 50000:
            report.findings.append(ValidationFinding(
                category="resource",
                severity="warning",
                message=f"Estimated LUT usage is high: ~{estimate.lut_count}",
                suggestion="Consider resource-sharing or time-multiplexing",
            ))

    @staticmethod
    def load_and_validate(spec_path: Path) -> PreCheckReport:
        """Convenience: load a spec JSON file and validate it."""
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec_data = json.load(f)
        validator = RequirementValidator()
        return validator.validate_spec(spec_data)
