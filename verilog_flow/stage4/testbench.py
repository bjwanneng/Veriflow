"""Testbench Generator for Stage 4."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..stage1.spec_generator import MicroArchSpec
from ..stage2.yaml_dsl import TimingScenario


@dataclass
class TestbenchConfig:
    """Configuration for testbench generation."""

    module_name: str
    timescale: str = "1ns/1ps"
    dump_waveform: bool = True
    timeout_cycles: int = 10000

    # Signal configuration
    clock_period_ns: float = 10.0
    reset_duration_ns: float = 50.0

    # Test configuration
    random_seed: Optional[int] = None
    num_random_tests: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_name": self.module_name,
            "timescale": self.timescale,
            "dump_waveform": self.dump_waveform,
            "timeout_cycles": self.timeout_cycles,
            "clock_period_ns": self.clock_period_ns,
            "reset_duration_ns": self.reset_duration_ns,
            "random_seed": self.random_seed,
            "num_random_tests": self.num_random_tests,
        }


class TestbenchGenerator:
    """Generate SystemVerilog testbenches."""

    def __init__(self, config: TestbenchConfig):
        self.config = config

    def generate_from_scenario(
        self, scenario: TimingScenario, dut_module: str = "dut"
    ) -> str:
        """Generate a testbench from a timing scenario."""

        lines = []

        # Timescale
        lines.append(f"`timescale {self.config.timescale}")
        lines.append("")

        # Module declaration
        lines.append(f"module tb_{self.config.module_name};")
        lines.append("")

        # Parameters
        if scenario.parameters:
            lines.append("// Parameters")
            for name, value in scenario.parameters.items():
                lines.append(f"localparam {name} = {value};")
            lines.append("")

        # Clock and reset
        lines.append("// Clock and reset")
        lines.append("reg clk;")
        lines.append("reg rst_n;")
        lines.append("")

        # Collect all signals from scenario
        signals = self._collect_signals(scenario)

        # Signal declarations
        lines.append("// Test signals")
        for sig_name, sig_info in signals.items():
            if sig_name not in ["clk", "rst_n"]:
                direction = sig_info.get("direction", "input")
                width = sig_info.get("width", 1)

                if direction == "input":
                    lines.append(f"reg  [{width-1}:0] {sig_name};")
                else:
                    lines.append(f"wire [{width-1}:0] {sig_name};")
        lines.append("")

        # DUT instantiation
        lines.append("// DUT instantiation")
        lines.append(f"{dut_module} #(")
        if scenario.parameters:
            for name in scenario.parameters.keys():
                lines.append(f"    .{name}({name}),")
        # Remove trailing comma
        if scenario.parameters:
            lines[-1] = lines[-1].rstrip(",")
        lines.append(") dut (")
        lines.append("    .clk(clk),")
        lines.append("    .rst_n(rst_n),")

        # Connect signals
        for sig_name in signals:
            if sig_name not in ["clk", "rst_n"]:
                lines.append(f"    .{sig_name}({sig_name}),")

        # Remove trailing comma
        if lines[-1].endswith(","):
            lines[-1] = lines[-1].rstrip(",")

        lines.append(");")
        lines.append("")

        # Clock generation
        lines.append("// Clock generation")
        half_period = self.config.clock_period_ns / 2
        lines.append(f"initial begin")
        lines.append(f"    clk = 0;")
        lines.append(f"    forever #{half_period} clk = ~clk;")
        lines.append(f"end")
        lines.append("")

        # Waveform dump
        if self.config.dump_waveform:
            lines.append("// Waveform dump")
            lines.append("initial begin")
            lines.append(f'    $dumpfile("tb_{self.config.module_name}.vcd");')
            lines.append(f'    $dumpvars(0, tb_{self.config.module_name});')
            lines.append("end")
            lines.append("")

        # Main test sequence
        lines.append("// Test sequence")
        lines.append("initial begin")
        lines.append("    // Initialize inputs")
        for sig_name, sig_info in signals.items():
            if sig_info.get("direction") == "input" and sig_name not in ["clk", "rst_n"]:
                lines.append(f"    {sig_name} = 0;")
        lines.append("")

        lines.append("    // Reset")
        lines.append("    rst_n = 0;")
        lines.append(f"    #{self.config.reset_duration_ns};")
        lines.append("    rst_n = 1;")
        lines.append("")

        lines.append("    // Execute scenario phases")
        lines.append(self._generate_phase_sequence(scenario))

        lines.append("")
        lines.append("    // End simulation")
        lines.append("    #100;")
        lines.append('    $display("Simulation completed successfully!");')
        lines.append("    $finish;")
        lines.append("end")
        lines.append("")

        # Timeout watchdog
        lines.append("// Timeout watchdog")
        lines.append(f"initial begin")
        lines.append(
            f"    #{self.config.timeout_cycles * self.config.clock_period_ns};"
        )
        lines.append('    $display("ERROR: Simulation timeout!");')
        lines.append("    $finish;")
        lines.append("end")
        lines.append("")

        lines.append("endmodule")

        return "\n".join(lines)

    def generate_from_spec(self, spec: MicroArchSpec) -> str:
        """Generate a basic testbench from micro-architecture spec."""

        lines = []

        # Timescale
        lines.append(f"`timescale {self.config.timescale}")
        lines.append("")

        # Module declaration
        lines.append(f"module tb_{spec.module_name};")
        lines.append("")

        # Clock and reset
        lines.append("// Clock and reset")
        lines.append("reg clk;")
        lines.append("reg rst_n;")
        lines.append("")

        # Interface signals
        for interface in spec.interfaces:
            lines.append(f"// {interface.name} interface ({interface.protocol})")

            # Data
            if interface.data_width > 0:
                if interface.direction == "master":
                    lines.append(f"reg  [{interface.data_width-1}:0] {interface.name}_data;")
                    lines.append(f"wire [{interface.data_width-1}:0] {interface.name}_rdata;")
                else:
                    lines.append(f"wire [{interface.data_width-1}:0] {interface.name}_data;")

            # Address
            if interface.addr_width > 0:
                lines.append(f"reg  [{interface.addr_width-1}:0] {interface.name}_addr;")

            # Control
            if interface.protocol in ["AXI4-Lite", "AXI4", "Custom"]:
                lines.append(f"reg  {interface.name}_valid;")
                lines.append(f"wire {interface.name}_ready;")

            lines.append("")

        # DUT instantiation (simplified)
        lines.append("// DUT instantiation")
        lines.append(f"{spec.module_name} dut (")
        lines.append("    .clk(clk),")
        lines.append("    .rst_n(rst_n),")
        lines.append("    /* ... port connections ... */")
        lines.append(");")
        lines.append("")

        # Clock generation
        lines.append("// Clock generation")
        half_period = self.config.clock_period_ns / 2
        lines.append(f"initial begin")
        lines.append(f"    clk = 0;")
        lines.append(f"    forever #{half_period} clk = ~clk;")
        lines.append(f"end")
        lines.append("")

        # Waveform dump
        if self.config.dump_waveform:
            lines.append("// Waveform dump")
            lines.append("initial begin")
            lines.append(f'    $dumpfile("tb_{spec.module_name}.vcd");')
            lines.append(f'    $dumpvars(0, tb_{spec.module_name});')
            lines.append("end")
            lines.append("")

        # Basic test sequence
        lines.append("// Basic test sequence")
        lines.append("initial begin")
        lines.append("    // Initialize")
        for interface in spec.interfaces:
            if interface.protocol in ["AXI4-Lite", "AXI4", "Custom"]:
                lines.append(f"    {interface.name}_valid = 0;")
            if interface.data_width > 0 and interface.direction == "master":
                lines.append(f"    {interface.name}_data = 0;")
            if interface.addr_width > 0:
                lines.append(f"    {interface.name}_addr = 0;")
        lines.append("")

        lines.append("    // Reset")
        lines.append("    rst_n = 0;")
        lines.append(f"    #{self.config.reset_duration_ns};")
        lines.append("    rst_n = 1;")
        lines.append("")

        lines.append("    // TODO: Add test stimulus")
        lines.append(f"    repeat(10) @(posedge clk);")
        lines.append("")

        lines.append("    // End simulation")
        lines.append('    $display("Simulation completed!");')
        lines.append("    $finish;")
        lines.append("end")
        lines.append("")

        lines.append("endmodule")

        return "\n".join(lines)

    def _collect_signals(self, scenario: TimingScenario) -> Dict[str, Dict[str, Any]]:
        """Collect all signals from scenario phases."""
        signals = {}

        for phase in scenario.phases:
            for sig in phase.signals:
                if sig.signal not in signals:
                    signals[sig.signal] = {
                        "direction": "input",
                        "width": 32,  # Default width
                    }

        return signals

    def _generate_phase_sequence(self, scenario: TimingScenario) -> str:
        """Generate the sequence of phase executions."""
        lines = []

        for phase in scenario.phases:
            lines.append(f"    // Phase: {phase.name}")

            # Set signals
            for sig in phase.signals:
                value = sig.value
                if isinstance(value, str) and value.startswith("$"):
                    # Variable reference - handle specially
                    lines.append(f"    {sig.signal} = {value[1:]}; // Variable")
                else:
                    lines.append(f"    {sig.signal} = {value};")

            lines.append(f"    #{phase.duration_ns};")
            lines.append("")

        return "\n".join(lines)

    def save(self, output_dir: Path, verilog_code: str) -> Path:
        """Save the testbench to file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        file_path = output_dir / f"tb_{self.config.module_name}.sv"
        file_path.write_text(verilog_code, encoding="utf-8")

        return file_path
