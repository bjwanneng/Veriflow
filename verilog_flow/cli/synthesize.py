"""Synthesis CLI for VeriFlow-Agent."""

import sys
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from verilog_flow.stage5 import SynthesisRunner, TimingAnalyzer, AreaEstimator

console = Console()


@click.group()
@click.version_option(version="3.0.0", prog_name="vf-synth")
def cli():
    """VeriFlow Synthesis: Run synthesis and analyze timing/area."""
    pass


@cli.command()
@click.argument('verilog_file', type=click.Path(exists=True, path_type=Path))
@click.option('--top', '-t', required=True, help='Top module name')
@click.option('--target', type=click.Choice(['generic', 'ice40', 'ecp5', 'xilinx']), default='generic')
@click.option('--freq', '-f', default=100.0, help='Target frequency in MHz')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('synth_output'),
              help='Output directory')
def run(verilog_file: Path, top: str, target: str, freq: float, output: Path):
    """Run synthesis on a Verilog design."""

    console.print(Panel.fit(f"[bold blue]Synthesizing: {verilog_file.name}[/]"))
    console.print(f"Target: [cyan]{target}[/] @ [cyan]{freq} MHz[/]")

    try:
        output.mkdir(parents=True, exist_ok=True)

        # Run synthesis
        runner = SynthesisRunner(output_dir=output)
        result = runner.run(
            verilog_files=[verilog_file],
            top_module=top,
            target_frequency_mhz=freq,
            target_device=target,
        )

        # Display results
        if result.success:
            console.print(f"[green]✓ Synthesis completed successfully[/]")
        else:
            console.print(f"[red]✗ Synthesis failed[/]")
            for error in result.errors:
                console.print(f"  [red]Error:[/] {error}")

        # Summary table
        table = Table(title="Synthesis Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Module", result.module_name)
        table.add_row("Target Freq", f"{result.target_frequency_mhz:.2f} MHz")
        table.add_row("Est. Max Freq", f"{result.estimated_max_frequency_mhz:.2f} MHz")

        timing_status = "[green]MET[/]" if result.timing_met else "[red]VIOLATED[/]"
        table.add_row("Timing", timing_status)

        if result.worst_negative_slack_ns < 0:
            table.add_row("WNS", f"[red]{result.worst_negative_slack_ns:.3f} ns[/]")
        else:
            table.add_row("WNS", f"[green]+{result.worst_negative_slack_ns:.3f} ns[/]")

        table.add_row("Cell Count", str(result.cell_count))
        table.add_row("LUTs", str(result.lut_count))
        table.add_row("Flip-Flops", str(result.flip_flop_count))

        if result.bram_count > 0:
            table.add_row("BRAMs", str(result.bram_count))
        if result.dsp_count > 0:
            table.add_row("DSPs", str(result.dsp_count))

        table.add_row("Synthesis Time", f"{result.synthesis_time_seconds:.2f}s")

        console.print(table)

        # Save results
        result.save(output / "synthesis_result.json")
        console.print(f"\n[green]✓[/] Results saved to: {output}")

        return 0 if result.success else 1

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        import traceback
        console.print(traceback.format_exc())
        return 1


@cli.command()
@click.argument('verilog_file', type=click.Path(exists=True, path_type=Path))
@click.option('--top', '-t', required=True, help='Top module name')
@click.option('--target', type=click.Choice(['generic', 'ice40', 'ecp5', 'xilinx']), default='generic')
@click.option('--freq', '-f', default=100.0, help='Target frequency in MHz')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('synth_output'),
              help='Output directory')
def analyze(verilog_file: Path, top: str, target: str, freq: float, output: Path):
    """Run synthesis and perform detailed timing/area analysis."""

    console.print(Panel.fit(f"[bold blue]Analyzing: {verilog_file.name}[/]"))

    try:
        output.mkdir(parents=True, exist_ok=True)

        # Run synthesis
        runner = SynthesisRunner(output_dir=output)
        synth_result = runner.run(
            verilog_files=[verilog_file],
            top_module=top,
            target_frequency_mhz=freq,
            target_device=target,
        )

        if not synth_result.success:
            console.print(f"[red]✗ Synthesis failed[/]")
            return 1

        # Timing analysis
        console.print("\n[bold]Timing Analysis[/]")
        timing_analyzer = TimingAnalyzer(target_frequency_mhz=freq)
        timing_result = timing_analyzer.analyze_from_synthesis(
            synth_result.json_output,
            synth_result.to_dict()
        )

        timing_table = Table(title="Timing Results")
        timing_table.add_column("Metric", style="cyan")
        timing_table.add_column("Value", style="green")

        timing_table.add_row("Target Frequency", f"{freq:.2f} MHz")
        timing_table.add_row("Estimated Fmax", f"{timing_result.fmax_mhz:.2f} MHz")
        timing_table.add_row("Setup Slack", f"{timing_result.worst_setup_slack_ns:.3f} ns")
        timing_table.add_row("Timing Met", "Yes" if timing_result.timing_met else "No")
        timing_table.add_row("Violating Paths", str(timing_result.violating_paths))

        console.print(timing_table)

        # Area analysis
        console.print("\n[bold]Area Analysis[/]")
        area_estimator = AreaEstimator(target_device=target)
        area_result = area_estimator.estimate_from_synthesis(synth_result.to_dict())

        area_table = Table(title="Area Results")
        area_table.add_column("Resource", style="cyan")
        area_table.add_column("Count", style="green")
        area_table.add_column("Utilization", style="yellow")

        area_table.add_row("LUTs", str(area_result.breakdown.lut_count),
                          f"{area_result.utilization.lut_utilization*100:.1f}%")
        area_table.add_row("Flip-Flops", str(area_result.breakdown.flip_flop_count),
                          f"{area_result.utilization.ff_utilization*100:.1f}%")
        area_table.add_row("BRAMs", str(area_result.breakdown.bram_count),
                          f"{area_result.utilization.bram_utilization*100:.1f}%")
        area_table.add_row("DSPs", str(area_result.breakdown.dsp_count),
                          f"{area_result.utilization.dsp_utilization*100:.1f}%")
        area_table.add_row("Total Cells", str(area_result.cell_count), "")

        console.print(area_table)

        console.print(f"\nEstimated Power: ~{area_result.estimated_power_mw:.2f} mW @ 100MHz")

        # Save reports
        timing_analyzer.generate_timing_report(timing_result, output / "timing_report.txt")
        area_estimator.generate_area_report(area_result, output / "area_report.txt")

        console.print(f"\n[green]✓[/] Reports saved to: {output}")

        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        import traceback
        console.print(traceback.format_exc())
        return 1


@cli.command()
@click.argument('synth_result', type=click.Path(exists=True, path_type=Path))
def report(synth_result: Path):
    """Display a synthesis result JSON file."""

    data = json.loads(synth_result.read_text(encoding='utf-8'))

    tree = Tree(f"[bold]{data.get('module_name', 'Unknown')}[/]")

    timing_branch = tree.add("[cyan]Timing[/]")
    timing_branch.add(f"Target: {data.get('target_frequency_mhz', 0):.2f} MHz")
    timing_branch.add(f"Estimated Fmax: {data.get('estimated_max_frequency_mhz', 0):.2f} MHz")
    timing_branch.add(f"Timing Met: {data.get('timing_met', False)}")

    area_branch = tree.add("[cyan]Area[/]")
    area_branch.add(f"Cell Count: {data.get('cell_count', 0)}")
    area_branch.add(f"LUTs: {data.get('lut_count', 0)}")
    area_branch.add(f"Flip-Flops: {data.get('flip_flop_count', 0)}")

    console.print(tree)

    return 0


def main():
    """Entry point for the synth CLI."""
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
