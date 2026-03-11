"""Simulation CLI for VeriFlow-Agent."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from verilog_flow.stage2 import parse_yaml_scenario, generate_golden_trace
from verilog_flow.stage4 import TestbenchGenerator, TestbenchConfig
from verilog_flow.stage4 import SimulationRunner, WaveformDiffAnalyzer

console = Console()


@click.group()
@click.version_option(version="3.0.0", prog_name="vf-sim")
def cli():
    """VeriFlow Simulation: Run verification and check against golden traces."""
    pass


@cli.command()
@click.argument('design_file', type=click.Path(exists=True, path_type=Path))
@click.argument('scenario_file', type=click.Path(exists=True, path_type=Path))
@click.option('--top', '-t', default='dut', help='Top module name')
@click.option('--simulator', '-s', type=click.Choice(['iverilog', 'verilator']), default='iverilog')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('sim_output'),
              help='Output directory')
@click.option('--golden-trace', type=click.Path(path_type=Path),
              help='Golden trace file for comparison')
def run(design_file: Path, scenario_file: Path, top: str, simulator: str, output: Path, golden_trace: Path):
    """Run simulation with a scenario."""

    console.print(Panel.fit(f"[bold blue]Running Simulation: {design_file.name}[/]"))

    try:
        output.mkdir(parents=True, exist_ok=True)

        # Load scenario
        with open(scenario_file, 'r') as f:
            scenario = parse_yaml_scenario(f.read())
        console.print(f"[green]✓[/] Loaded scenario: [cyan]{scenario.name}[/]")

        # Generate testbench
        config = TestbenchConfig(
            module_name=top,
            dump_waveform=True
        )
        tb_generator = TestbenchGenerator(config)
        tb_code = tb_generator.generate_from_scenario(scenario, dut_module=top)

        tb_file = output / f"tb_{top}.sv"
        tb_file.write_text(tb_code, encoding='utf-8')
        console.print(f"[green]✓[/] Generated testbench: [cyan]{tb_file}[/]")

        # Generate golden trace if not provided
        if not golden_trace:
            trace = generate_golden_trace(scenario)
            golden_trace = output / "golden_trace.json"
            trace.save(golden_trace)
            console.print(f"[green]✓[/] Generated golden trace: [cyan]{golden_trace}[/]")

        # Run simulation
        console.print("\n[bold]Running simulation...[/]")
        runner = SimulationRunner(simulator=simulator, output_dir=output)
        result = runner.run(
            design_files=[design_file],
            testbench_file=tb_file,
            top_module=f"tb_{top}"
        )

        if result.success:
            console.print(f"[green]✓ Simulation completed successfully[/]")
        else:
            console.print(f"[red]✗ Simulation failed[/]")
            if result.error:
                console.print(f"Error: {result.error}")

        # Display results
        table = Table(title="Simulation Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Return Code", str(result.return_code))
        table.add_row("Tests Passed", str(result.tests_passed))
        table.add_row("Tests Failed", str(result.tests_failed))
        table.add_row("Assertions Passed", str(result.assertions_passed))
        table.add_row("Assertions Failed", str(result.assertions_failed))

        if result.waveform_file:
            table.add_row("Waveform", str(result.waveform_file))

        console.print(table)

        return 0 if result.success else 1

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        import traceback
        console.print(traceback.format_exc())
        return 1


@cli.command()
@click.argument('golden_file', type=click.Path(exists=True, path_type=Path))
@click.argument('vcd_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='Save diff report to file')
def diff(golden_file: Path, vcd_file: Path, output: Path):
    """Compare golden trace against simulation waveform."""

    console.print(Panel.fit(f"[bold blue]Comparing Traces[/]"))

    from verilog_flow.stage2.golden_trace import GoldenTrace

    # Load golden trace
    import json
    with open(golden_file, 'r') as f:
        trace_data = json.load(f)

    golden = GoldenTrace(
        scenario_id=trace_data.get('scenario_id', 'unknown'),
        scenario_name=trace_data.get('scenario_name', 'unknown'),
        clock_period_ps=trace_data.get('clock_period_ps', 10000),
    )

    # Compare
    analyzer = WaveformDiffAnalyzer()
    result = analyzer.compare(golden, vcd_file)

    if result.matched:
        console.print(f"[green]✓ Waveforms match![/]")
    else:
        console.print(f"[red]✗ Found {result.difference_count} differences[/]")

        table = Table(title="Differences")
        table.add_column("Time (ps)", style="cyan")
        table.add_column("Signal", style="yellow")
        table.add_column("Expected", style="green")
        table.add_column("Actual", style="red")

        for diff in result.differences[:10]:  # Show first 10
            table.add_row(
                str(diff.time_ps),
                diff.signal,
                str(diff.expected_value),
                str(diff.actual_value)
            )

        if result.difference_count > 10:
            table.add_row("...", "...", "...", f"(+{result.difference_count - 10} more)")

        console.print(table)

    if output:
        analyzer.generate_report(result, output)
        console.print(f"[green]✓[/] Report saved to: {output}")

    return 0 if result.matched else 1


@cli.command()
@click.argument('scenario_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('golden_trace.json'))
def trace(scenario_file: Path, output: Path):
    """Generate golden trace from scenario."""

    console.print(Panel.fit(f"[bold blue]Generating Golden Trace[/]"))

    with open(scenario_file, 'r') as f:
        scenario = parse_yaml_scenario(f.read())

    golden_trace = generate_golden_trace(scenario)
    golden_trace.save(output)

    console.print(f"[green]✓[/] Golden trace saved to: [cyan]{output}[/]")
    console.print(f"  Events: {len(golden_trace.events)}")
    console.print(f"  Clock period: {golden_trace.clock_period_ps} ps")

    return 0


def main():
    """Entry point for the sim CLI."""
    try:
        return cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/]")
        return 1


if __name__ == '__main__':
    sys.exit(main())
