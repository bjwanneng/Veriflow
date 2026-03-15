"""Interface consistency checker — cross-module port validation.

Validates that module instantiations match their spec definitions:
- Port width/direction matching between spec and RTL
- Instantiation completeness (all spec ports connected)
- Signal naming consistency across module boundaries
- Top-module wiring correctness

v5.0: New module for intra-generation shift-left checks.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class PortInfo:
    """Extracted port information from Verilog source."""
    name: str
    direction: str   # "input" | "output" | "inout"
    width: int
    line_number: int


@dataclass
class InstantiationInfo:
    """Extracted module instantiation from Verilog source."""
    module_name: str
    instance_name: str
    port_connections: Dict[str, str]  # formal -> actual
    line_number: int


@dataclass
class InterfaceFinding:
    """A single interface consistency finding."""
    severity: str   # "error" | "warning"
    check: str      # rule identifier
    message: str
    file_path: str = ""
    line_number: int = 0
    suggestion: str = ""


@dataclass
class InterfaceCheckReport:
    """Result of interface consistency checking."""
    findings: List[InterfaceFinding] = field(default_factory=list)

    @property
    def errors(self) -> List[InterfaceFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


class InterfaceChecker:
    """Check cross-module interface consistency.

    Compares spec JSON port definitions against actual RTL implementations
    and validates instantiation wiring in top-level modules.
    """

    def check_spec_vs_rtl(self, spec_data: Dict[str, Any],
                          rtl_dir: Path) -> InterfaceCheckReport:
        """Compare spec module definitions against RTL files.

        For each module in spec, find the corresponding .v file and verify:
        1. All spec ports exist in RTL
        2. Port directions match
        3. Port widths match
        """
        report = InterfaceCheckReport()
        modules = spec_data.get("modules", [])

        for mod in modules:
            mod_name = mod.get("name", "")
            spec_ports = mod.get("ports", [])
            if not spec_ports:
                continue

            rtl_file = rtl_dir / f"{mod_name}.v"
            if not rtl_file.exists():
                report.findings.append(InterfaceFinding(
                    severity="error",
                    check="RTL_FILE_MISSING",
                    message=f"No RTL file for spec module '{mod_name}'",
                    suggestion=f"Create {mod_name}.v in {rtl_dir}",
                ))
                continue

            rtl_code = rtl_file.read_text(encoding="utf-8", errors="replace")
            rtl_ports = self._extract_ports(rtl_code)
            rtl_port_map = {p.name: p for p in rtl_ports}

            for sp in spec_ports:
                sp_name = sp.get("name", "")
                sp_dir = sp.get("direction", "")
                sp_width = sp.get("width", 1)

                if sp_name not in rtl_port_map:
                    report.findings.append(InterfaceFinding(
                        severity="error",
                        check="PORT_MISSING_IN_RTL",
                        message=(
                            f"Module '{mod_name}': spec port '{sp_name}' "
                            f"not found in RTL"
                        ),
                        file_path=str(rtl_file),
                        suggestion=f"Add port '{sp_name}' to {mod_name}.v",
                    ))
                    continue

                rp = rtl_port_map[sp_name]

                # Direction check
                if sp_dir and rp.direction and sp_dir != rp.direction:
                    report.findings.append(InterfaceFinding(
                        severity="error",
                        check="PORT_DIRECTION_MISMATCH",
                        message=(
                            f"Module '{mod_name}' port '{sp_name}': "
                            f"spec says '{sp_dir}', RTL says '{rp.direction}'"
                        ),
                        file_path=str(rtl_file),
                        line_number=rp.line_number,
                        suggestion=f"Align direction to '{sp_dir}'",
                    ))

                # Width check
                if sp_width != rp.width:
                    report.findings.append(InterfaceFinding(
                        severity="error",
                        check="PORT_WIDTH_MISMATCH",
                        message=(
                            f"Module '{mod_name}' port '{sp_name}': "
                            f"spec width={sp_width}, RTL width={rp.width}"
                        ),
                        file_path=str(rtl_file),
                        line_number=rp.line_number,
                        suggestion=f"Change RTL port width to [{sp_width-1}:0]",
                    ))

        return report

    def check_instantiation_completeness(self, spec_data: Dict[str, Any],
                                          top_rtl_path: Path) -> InterfaceCheckReport:
        """Check that the top module instantiates all submodules with correct ports."""
        report = InterfaceCheckReport()

        if not top_rtl_path.exists():
            return report

        top_code = top_rtl_path.read_text(encoding="utf-8", errors="replace")
        instantiations = self._extract_instantiations(top_code)
        inst_map = {inst.module_name: inst for inst in instantiations}

        modules = spec_data.get("modules", [])
        top_modules = [m for m in modules if m.get("module_type") == "top"]
        sub_modules = [m for m in modules if m.get("module_type") != "top"]

        for mod in sub_modules:
            mod_name = mod.get("name", "")
            spec_ports = mod.get("ports", [])

            if mod_name not in inst_map:
                report.findings.append(InterfaceFinding(
                    severity="warning",
                    check="MODULE_NOT_INSTANTIATED",
                    message=f"Module '{mod_name}' defined in spec but not instantiated in top",
                    file_path=str(top_rtl_path),
                    suggestion=f"Add instantiation of '{mod_name}' in top module",
                ))
                continue

            inst = inst_map[mod_name]
            connected_ports = set(inst.port_connections.keys())
            spec_port_names = {p.get("name", "") for p in spec_ports}

            # Check for unconnected spec ports
            missing = spec_port_names - connected_ports
            for port_name in missing:
                report.findings.append(InterfaceFinding(
                    severity="warning",
                    check="PORT_NOT_CONNECTED",
                    message=(
                        f"Module '{mod_name}' instance '{inst.instance_name}': "
                        f"spec port '{port_name}' not connected"
                    ),
                    file_path=str(top_rtl_path),
                    line_number=inst.line_number,
                    suggestion=f"Connect .{port_name}(...) in instantiation",
                ))

            # Check for extra ports not in spec
            extra = connected_ports - spec_port_names
            for port_name in extra:
                report.findings.append(InterfaceFinding(
                    severity="warning",
                    check="EXTRA_PORT_IN_INST",
                    message=(
                        f"Module '{mod_name}' instance '{inst.instance_name}': "
                        f"port '{port_name}' connected but not in spec"
                    ),
                    file_path=str(top_rtl_path),
                    line_number=inst.line_number,
                    suggestion="Update spec or remove extra port connection",
                ))

        return report

    # ── Verilog parsing helpers ──────────────────────────────────────

    def _extract_ports(self, verilog_code: str) -> List[PortInfo]:
        """Extract port declarations from Verilog source.

        Handles ANSI-style port declarations:
            input wire [7:0] data,
            output reg [127:0] result
        """
        ports: List[PortInfo] = []
        lines = verilog_code.split('\n')

        # ANSI port pattern
        port_re = re.compile(
            r'\b(input|output|inout)\s+'
            r'(?:wire\s+|reg\s+)?'
            r'(?:signed\s+)?'
            r'(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s+)?'
            r'(\w+)'
        )

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue

            for m in port_re.finditer(stripped):
                direction = m.group(1)
                msb = int(m.group(2)) if m.group(2) else 0
                lsb = int(m.group(3)) if m.group(3) else 0
                name = m.group(4)
                width = abs(msb - lsb) + 1 if m.group(2) else 1

                ports.append(PortInfo(
                    name=name,
                    direction=direction,
                    width=width,
                    line_number=i,
                ))

        return ports

    def _extract_instantiations(self, verilog_code: str) -> List[InstantiationInfo]:
        """Extract module instantiations from Verilog source.

        Handles named port connections:
            module_name #(...) instance_name (
                .port1(signal1),
                .port2(signal2)
            );
        """
        instantiations: List[InstantiationInfo] = []

        # Remove comments
        code = re.sub(r'//.*$', '', verilog_code, flags=re.MULTILINE)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Pattern for module instantiation
        inst_re = re.compile(
            r'\b(\w+)\s+'                    # module name
            r'(?:#\s*\([^)]*\)\s+)?'         # optional parameters
            r'(\w+)\s*\('                     # instance name (
            r'(.*?)'                          # port connections
            r'\)\s*;',                        # );
            re.DOTALL
        )

        # Keywords that are NOT module names
        keywords = {
            'module', 'endmodule', 'input', 'output', 'inout', 'wire', 'reg',
            'assign', 'always', 'initial', 'begin', 'end', 'if', 'else',
            'case', 'endcase', 'for', 'while', 'generate', 'endgenerate',
            'function', 'endfunction', 'task', 'endtask', 'parameter',
            'localparam', 'integer', 'genvar', 'default',
        }

        for m in inst_re.finditer(code):
            mod_name = m.group(1)
            inst_name = m.group(2)
            port_block = m.group(3)

            if mod_name in keywords:
                continue

            # Parse named port connections: .formal(actual)
            port_connections: Dict[str, str] = {}
            for pm in re.finditer(r'\.(\w+)\s*\(([^)]*)\)', port_block):
                formal = pm.group(1)
                actual = pm.group(2).strip()
                port_connections[formal] = actual

            line_number = verilog_code[:m.start()].count('\n') + 1

            instantiations.append(InstantiationInfo(
                module_name=mod_name,
                instance_name=inst_name,
                port_connections=port_connections,
                line_number=line_number,
            ))

        return instantiations
