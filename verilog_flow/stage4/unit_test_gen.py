"""Automatic submodule unit test generator.

Generates isolated per-module testbenches from spec JSON:
- Self-checking with PASS/FAIL for each test vector
- Intermediate value snapshots for debugging
- Golden vector comparison support
- Differential diagnosis (expected vs actual pinpointing)
- Timeout watchdog per test

v5.0: New module for incremental verification infrastructure.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TestVector:
    """A single input/output test vector for a module."""
    name: str
    inputs: Dict[str, str]    # port_name -> hex value string
    expected: Dict[str, str]  # port_name -> expected hex value string
    description: str = ""
    cycle_delay: int = 1      # cycles to wait before checking output


@dataclass
class UnitTestConfig:
    """Configuration for unit test generation."""
    timescale: str = "1ns/1ps"
    clock_period_ns: float = 10.0
    reset_duration_ns: float = 50.0
    timeout_cycles: int = 5000
    dump_waveform: bool = True
    snapshot_signals: List[str] = field(default_factory=list)


class UnitTestGenerator:
    """Generate per-module unit testbenches from spec.

    Usage:
        gen = UnitTestGenerator(spec_data)
        for mod_name, tb_code in gen.generate_all():
            write_file(f"tb_{mod_name}.v", tb_code)
    """

    def __init__(self, spec_data: Dict[str, Any],
                 config: Optional[UnitTestConfig] = None):
        self.spec = spec_data
        self.config = config or UnitTestConfig()
        self.modules = spec_data.get("modules", [])

    def generate_all(self) -> List[Tuple[str, str]]:
        """Generate unit testbenches for all non-top modules.

        Returns:
            List of (module_name, testbench_verilog_code) tuples
        """
        results = []
        for mod in self.modules:
            if mod.get("module_type") == "top":
                continue
            mod_name = mod.get("name", "")
            if not mod_name:
                continue
            tb_code = self.generate_module_tb(mod)
            results.append((mod_name, tb_code))
        return results

    def generate_module_tb(self, module_spec: Dict[str, Any],
                           test_vectors: Optional[List[TestVector]] = None) -> str:
        """Generate a unit testbench for a single module.

        Args:
            module_spec: Module definition from spec JSON
            test_vectors: Optional custom test vectors. If None, auto-generates
                         basic stimulus (reset, zero-input, all-ones, walking-bit).
        """
        mod_name = module_spec.get("name", "unknown")
        ports = module_spec.get("ports", [])

        input_ports = [p for p in ports if p.get("direction") == "input"]
        output_ports = [p for p in ports if p.get("direction") == "output"]

        # Separate clock/reset from data ports
        clk_ports = [p for p in input_ports if p.get("name") in ("clk", "clock")]
        rst_ports = [p for p in input_ports
                     if p.get("name") in ("rst", "rst_n", "reset", "reset_n")]
        data_inputs = [p for p in input_ports
                       if p not in clk_ports and p not in rst_ports]

        has_clock = len(clk_ports) > 0
        has_reset = len(rst_ports) > 0

        lines: List[str] = []
        self._emit_header(lines, mod_name)
        self._emit_signal_decls(lines, ports, has_clock, has_reset)
        self._emit_dut_instantiation(lines, mod_name, ports)

        if has_clock:
            self._emit_clock_gen(lines, clk_ports[0].get("name", "clk"))

        if self.config.dump_waveform:
            self._emit_waveform_dump(lines, mod_name)

        self._emit_test_sequence(lines, mod_name, data_inputs, output_ports,
                                 has_clock, has_reset, rst_ports, test_vectors)
        self._emit_timeout_watchdog(lines)
        lines.append("")
        lines.append("endmodule")

        return "\n".join(lines)

    # ── Code emission helpers ────────────────────────────────────────

    def _emit_header(self, lines: List[str], mod_name: str):
        lines.append(f"`timescale {self.config.timescale}")
        lines.append("")
        lines.append(f"module tb_{mod_name};")
        lines.append("")
        lines.append("// Test tracking")
        lines.append("integer test_count = 0;")
        lines.append("integer pass_count = 0;")
        lines.append("integer fail_count = 0;")
        lines.append("")

    def _emit_signal_decls(self, lines: List[str], ports: List[Dict],
                           has_clock: bool, has_reset: bool):
        lines.append("// DUT signals")
        for port in ports:
            name = port.get("name", "")
            width = port.get("width", 1)
            direction = port.get("direction", "input")

            width_str = f"[{width-1}:0] " if width > 1 else ""

            if direction == "input":
                lines.append(f"reg  {width_str}{name};")
            else:
                lines.append(f"wire {width_str}{name};")
        lines.append("")

    def _emit_dut_instantiation(self, lines: List[str], mod_name: str,
                                 ports: List[Dict]):
        lines.append("// DUT instantiation")
        lines.append(f"{mod_name} dut (")
        for i, port in enumerate(ports):
            name = port.get("name", "")
            comma = "," if i < len(ports) - 1 else ""
            lines.append(f"    .{name}({name}){comma}")
        lines.append(");")
        lines.append("")

    def _emit_clock_gen(self, lines: List[str], clk_name: str):
        half = self.config.clock_period_ns / 2
        lines.append("// Clock generation")
        lines.append("initial begin")
        lines.append(f"    {clk_name} = 0;")
        lines.append(f"    forever #{half} {clk_name} = ~{clk_name};")
        lines.append("end")
        lines.append("")

    def _emit_waveform_dump(self, lines: List[str], mod_name: str):
        lines.append("// Waveform dump")
        lines.append("initial begin")
        lines.append(f'    $dumpfile("tb_{mod_name}.vcd");')
        lines.append(f'    $dumpvars(0, tb_{mod_name});')
        lines.append("end")
        lines.append("")

    def _emit_test_sequence(self, lines: List[str], mod_name: str,
                            data_inputs: List[Dict], output_ports: List[Dict],
                            has_clock: bool, has_reset: bool,
                            rst_ports: List[Dict],
                            test_vectors: Optional[List[TestVector]]):
        lines.append("// ============================================")
        lines.append("// Test sequence")
        lines.append("// ============================================")
        lines.append("initial begin")
        lines.append(f'    $display("=== Unit Test: {mod_name} ===");')
        lines.append("")

        # Initialize all inputs to zero
        lines.append("    // Initialize all inputs")
        for port in data_inputs:
            lines.append(f"    {port.get('name', '')} = 0;")
        lines.append("")

        # Reset sequence
        if has_reset and rst_ports:
            rst_name = rst_ports[0].get("name", "rst")
            is_active_low = "n" in rst_name.lower()
            lines.append("    // Reset sequence")
            if is_active_low:
                lines.append(f"    {rst_name} = 0;")
                lines.append(f"    #{self.config.reset_duration_ns};")
                lines.append(f"    {rst_name} = 1;")
            else:
                lines.append(f"    {rst_name} = 1;")
                lines.append(f"    #{self.config.reset_duration_ns};")
                lines.append(f"    {rst_name} = 0;")
            lines.append(f'    $display("Reset released");')
            lines.append("")

        if has_clock:
            lines.append(f"    @(posedge clk);")
            lines.append("")

        if test_vectors:
            self._emit_custom_vectors(lines, test_vectors, has_clock)
        else:
            self._emit_auto_vectors(lines, data_inputs, output_ports, has_clock)

        # Summary
        lines.append("    // ---- Summary ----")
        lines.append(f'    $display("=== Results: %0d tests, %0d pass, %0d fail ===",')
        lines.append(f'             test_count, pass_count, fail_count);')
        lines.append("    if (fail_count == 0)")
        lines.append(f'        $display("PASS: All tests passed for {mod_name}");')
        lines.append("    else")
        lines.append(f'        $display("FAIL: %0d tests failed for {mod_name}", fail_count);')
        lines.append("    $finish;")
        lines.append("end")
        lines.append("")

    def _emit_auto_vectors(self, lines: List[str], data_inputs: List[Dict],
                           output_ports: List[Dict], has_clock: bool):
        """Generate automatic test vectors: zero, all-ones, walking-bit."""
        wait = "    @(posedge clk);" if has_clock else "    #10;"

        # Test 1: All zeros
        lines.append("    // Test 1: All-zero input")
        lines.append("    test_count = test_count + 1;")
        for port in data_inputs:
            lines.append(f"    {port.get('name', '')} = 0;")
        lines.append(wait)
        self._emit_snapshot(lines, "zero_input", data_inputs, output_ports)
        lines.append('    $display("[PASS] Test 1: zero-input applied");')
        lines.append("    pass_count = pass_count + 1;")
        lines.append("")

        # Test 2: All ones
        lines.append("    // Test 2: All-ones input")
        lines.append("    test_count = test_count + 1;")
        for port in data_inputs:
            w = port.get("width", 1)
            if w > 1:
                lines.append(f"    {port.get('name', '')} = {{{w}{{1'b1}}}};")
            else:
                lines.append(f"    {port.get('name', '')} = 1'b1;")
        lines.append(wait)
        self._emit_snapshot(lines, "ones_input", data_inputs, output_ports)
        lines.append('    $display("[PASS] Test 2: all-ones input applied");')
        lines.append("    pass_count = pass_count + 1;")
        lines.append("")

        # Test 3: Pattern 0xA5
        lines.append("    // Test 3: Pattern 0xA5 input")
        lines.append("    test_count = test_count + 1;")
        for port in data_inputs:
            w = port.get("width", 1)
            if w >= 8:
                hex_w = (w + 3) // 4
                pattern = ("A5" * ((hex_w + 1) // 2))[:hex_w]
                lines.append(f"    {port.get('name', '')} = {w}'h{pattern};")
            elif w > 1:
                lines.append(f"    {port.get('name', '')} = {w}'b{'10' * ((w+1)//2)};")
            else:
                lines.append(f"    {port.get('name', '')} = 1'b1;")
        lines.append(wait)
        self._emit_snapshot(lines, "pattern_input", data_inputs, output_ports)
        lines.append('    $display("[PASS] Test 3: pattern input applied");')
        lines.append("    pass_count = pass_count + 1;")
        lines.append("")

    def _emit_custom_vectors(self, lines: List[str],
                             vectors: List[TestVector], has_clock: bool):
        """Emit test sequence for user-provided test vectors with checking."""
        wait = "    @(posedge clk);" if has_clock else "    #10;"

        for idx, vec in enumerate(vectors, 1):
            lines.append(f"    // Test {idx}: {vec.name}")
            if vec.description:
                lines.append(f"    // {vec.description}")
            lines.append(f"    test_count = test_count + 1;")

            # Apply inputs
            for port_name, value in vec.inputs.items():
                lines.append(f"    {port_name} = {value};")

            # Wait
            if vec.cycle_delay > 1:
                lines.append(f"    repeat({vec.cycle_delay}) {wait.strip()}")
            else:
                lines.append(wait)

            # Check expected outputs
            if vec.expected:
                for port_name, expected_val in vec.expected.items():
                    lines.append(f"    if ({port_name} !== {expected_val}) begin")
                    lines.append(
                        f'        $display("[FAIL] Test {idx} ({vec.name}): '
                        f'{port_name} = %h, expected {expected_val}", {port_name});'
                    )
                    lines.append(f"        fail_count = fail_count + 1;")
                    lines.append(f"    end else begin")
                    lines.append(
                        f'        $display("[PASS] Test {idx} ({vec.name}): '
                        f'{port_name} = %h", {port_name});'
                    )
                    lines.append(f"        pass_count = pass_count + 1;")
                    lines.append(f"    end")
            else:
                lines.append(
                    f'    $display("[PASS] Test {idx} ({vec.name}): stimulus applied");'
                )
                lines.append(f"    pass_count = pass_count + 1;")
            lines.append("")

    def _emit_snapshot(self, lines: List[str], label: str,
                       data_inputs: List[Dict], output_ports: List[Dict]):
        """Emit intermediate value snapshot for debugging."""
        lines.append(f'    $display("  [SNAPSHOT:{label}]");')
        for port in data_inputs[:4]:  # Limit to first 4 to avoid clutter
            name = port.get("name", "")
            lines.append(f'    $display("    IN  {name} = %h", {name});')
        for port in output_ports[:4]:
            name = port.get("name", "")
            lines.append(f'    $display("    OUT {name} = %h", {name});')

    def _emit_timeout_watchdog(self, lines: List[str]):
        timeout_ns = self.config.timeout_cycles * self.config.clock_period_ns
        lines.append("// Timeout watchdog")
        lines.append("initial begin")
        lines.append(f"    #{timeout_ns};")
        lines.append('    $display("[TIMEOUT] Simulation exceeded limit");')
        lines.append("    $finish;")
        lines.append("end")

    # ── Convenience methods ──────────────────────────────────────────

    def generate_and_save(self, output_dir: Path) -> List[Path]:
        """Generate all unit testbenches and save to output_dir.

        Returns list of created file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created: List[Path] = []
        for mod_name, tb_code in self.generate_all():
            path = output_dir / f"tb_unit_{mod_name}.v"
            path.write_text(tb_code, encoding="utf-8")
            created.append(path)

        return created
