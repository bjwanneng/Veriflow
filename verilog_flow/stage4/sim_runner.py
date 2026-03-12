"""Simulation Runner for Stage 4."""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..common.toolchain_detect import detect_toolchain
from ..common.experience_db import ExperienceDB, FailureCase, DesignPattern


@dataclass
class SimulationResult:
    """Result of a simulation run."""

    success: bool
    output: str = ""
    error: str = ""
    return_code: int = 0

    # Metrics
    simulation_time: float = 0.0  # seconds
    cycles_simulated: int = 0

    # Files generated
    waveform_file: Optional[Path] = None
    log_file: Optional[Path] = None

    # Pass/fail status
    tests_passed: int = 0
    tests_failed: int = 0
    assertions_passed: int = 0
    assertions_failed: int = 0

    @property
    def tests_total(self) -> int:
        return self.tests_passed + self.tests_failed

    @property
    def assertions_total(self) -> int:
        return self.assertions_passed + self.assertions_failed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "return_code": self.return_code,
            "simulation_time": self.simulation_time,
            "cycles_simulated": self.cycles_simulated,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_total": self.tests_total,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "assertions_total": self.assertions_total,
            "waveform_file": str(self.waveform_file) if self.waveform_file else None,
            "log_file": str(self.log_file) if self.log_file else None,
        }


class SimulationRunner:
    """Run Verilog simulations using various simulators."""

    def __init__(self, simulator: str = "iverilog", output_dir: Optional[Path] = None,
                 experience_db: Optional[ExperienceDB] = None):
        self.simulator = simulator
        self.output_dir = output_dir or Path("sim_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Auto-detect toolchain for correct PATH (esp. Windows + oss-cad-suite)
        self._toolchain = detect_toolchain()
        self._env = self._toolchain.shell_env()
        # Optional experience DB for auto-recording sim results
        self._exp_db = experience_db

    def run(
        self,
        design_files: List[Path],
        testbench_file: Path,
        top_module: str = "tb",
        run_timeout: int = 300,
    ) -> SimulationResult:
        """Run simulation."""

        if self.simulator == "iverilog":
            result = self._run_iverilog(design_files, testbench_file, top_module, run_timeout)
        elif self.simulator == "verilator":
            result = self._run_verilator(design_files, testbench_file, top_module, run_timeout)
        else:
            raise ValueError(f"Unsupported simulator: {self.simulator}")

        # Auto-record to experience DB
        if self._exp_db:
            self._record_experience(result, top_module)

        return result

    def _record_experience(self, result: SimulationResult, top_module: str):
        """Record simulation result to experience DB."""
        try:
            if not result.success:
                self._exp_db.record_failure(FailureCase(
                    case_id="",
                    module_name=top_module,
                    target_frequency_mhz=0,
                    stage="4",
                    failure_type="sim_failure",
                    error_message=result.error[:500] if result.error else "Unknown",
                ))
            else:
                self._exp_db.save_pattern(DesignPattern(
                    pattern_id=f"sim_pass_{top_module}",
                    name=f"{top_module} simulation pass",
                    description=f"Simulation passed: {result.tests_passed} tests, {result.assertions_passed} assertions",
                    module_type="simulation",
                    target_frequency_mhz=0,
                    micro_arch_spec={},
                    yaml_template="",
                    success_count=1,
                    tags=["sim_pass", top_module],
                ))
        except Exception:
            pass  # Don't let DB errors break simulation flow

    def _run_iverilog(
        self,
        design_files: List[Path],
        testbench_file: Path,
        top_module: str,
        timeout: int,
    ) -> SimulationResult:
        """Run simulation using Icarus Verilog."""

        result = SimulationResult(success=False)
        log_path = self.output_dir / "simulation.log"

        try:
            # Create temporary directory for compilation
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                compiled_file = tmpdir_path / "simulation.out"

                # Compile
                compile_cmd = [
                    "iverilog",
                    "-g2012",  # SystemVerilog 2012
                    "-o",
                    str(compiled_file),
                    "-s",
                    top_module,
                ]

                # Add all design files
                for f in design_files:
                    compile_cmd.append(str(f))
                compile_cmd.append(str(testbench_file))

                # Run compilation (use auto-detected toolchain env)
                compile_result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=self._env,
                )

                if compile_result.returncode != 0:
                    result.return_code = compile_result.returncode
                    result.error = f"Compilation failed:\n{compile_result.stderr}"
                    log_path.write_text(result.error, encoding="utf-8")
                    result.log_file = log_path
                    return result

                # Run simulation
                vcd_path = self.output_dir / "waveform.vcd"
                run_result = subprocess.run(
                    ["vvp", str(compiled_file)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=self._env,
                )

                result.return_code = run_result.returncode
                result.output = run_result.stdout
                result.error = run_result.stderr
                result.success = run_result.returncode == 0

                # Parse output for metrics
                result = self._parse_simulation_output(result)

                # Save log
                log_content = f"STDOUT:\n{result.output}\n\nSTDERR:\n{result.error}"
                log_path.write_text(log_content, encoding="utf-8")
                result.log_file = log_path

                # Check for VCD file
                if (self.output_dir / "waveform.vcd").exists():
                    result.waveform_file = self.output_dir / "waveform.vcd"

        except subprocess.TimeoutExpired:
            result.error = f"Simulation timed out after {timeout} seconds"
        except FileNotFoundError as e:
            result.error = f"Simulator not found: {e}"
        except Exception as e:
            result.error = f"Simulation error: {e}"

        return result

    def _run_verilator(
        self,
        design_files: List[Path],
        testbench_file: Path,
        top_module: str,
        timeout: int,
    ) -> SimulationResult:
        """Run simulation using Verilator."""

        result = SimulationResult(success=False)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Verilator compilation command
                compile_cmd = [
                    "verilator",
                    "--cc",
                    "--exe",
                    "--build",
                    "-j", "0",
                    "--trace",  # Enable VCD tracing
                    "--top-module",
                    top_module,
                    "-Mdir",
                    str(tmpdir_path / "obj_dir"),
                ]

                # Add all files
                for f in design_files:
                    compile_cmd.append(str(f))
                compile_cmd.append(str(testbench_file))

                # Compile
                compile_result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                if compile_result.returncode != 0:
                    result.return_code = compile_result.returncode
                    result.error = f"Compilation failed:\n{compile_result.stderr}"
                    return result

                # Run the compiled simulation
                exe_path = tmpdir_path / "obj_dir" / f"V{top_module}"
                run_result = subprocess.run(
                    [str(exe_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                result.return_code = run_result.returncode
                result.output = run_result.stdout
                result.error = run_result.stderr
                result.success = run_result.returncode == 0

                result = self._parse_simulation_output(result)

        except subprocess.TimeoutExpired:
            result.error = f"Simulation timed out after {timeout} seconds"
        except FileNotFoundError as e:
            result.error = f"Simulator not found: {e}"
        except Exception as e:
            result.error = f"Simulation error: {e}"

        return result

    def _parse_simulation_output(self, result: SimulationResult) -> SimulationResult:
        """Parse simulation output for metrics."""

        output = result.output + "\n" + result.error

        # Look for pass/fail patterns
        if "Simulation completed successfully" in output:
            result.success = True

        # Count assertions
        import re

        # Parse assertion results
        assertion_matches = re.findall(r"Assertion\s+(\w+)\s*:\s*(PASSED|FAILED)", output, re.IGNORECASE)
        for _, status in assertion_matches:
            if status.upper() == "PASSED":
                result.assertions_passed += 1
            else:
                result.assertions_failed += 1

        # Parse test results
        test_matches = re.findall(r"Test\s+(\w+)\s*:\s*(PASS|FAIL)", output, re.IGNORECASE)
        for _, status in test_matches:
            if status.upper() == "PASS":
                result.tests_passed += 1
            else:
                result.tests_failed += 1

        return result
