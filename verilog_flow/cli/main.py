#!/usr/bin/env python3
"""Main CLI entry point for VeriFlow-Agent."""

import sys
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from verilog_flow.stage2 import parse_yaml_scenario, validate_scenario
from verilog_flow.stage2 import generate_wavedrom, generate_golden_trace
from verilog_flow.common.kpi import KPITracker

console = Console()


@click.group()
@click.version_option(version="3.0.0", prog_name="verilog-flow")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """VeriFlow-Agent 3.0: Industrial-grade Verilog code generation."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


@cli.command()
@click.argument('yaml_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), help='Output file for validation report')
@click.pass_context
def validate(ctx, yaml_file: Path, output: Optional[Path]):
    """Validate a YAML timing scenario against the schema."""
    verbose = ctx.obj.get('verbose', False)

    console.print(Panel.fit(f"[bold blue]Validating: {yaml_file.name}[/]"))

    try:
        # Read and parse YAML
        with open(yaml_file, 'r') as f:
            yaml_content = f.read()

        # Parse the scenario
        scenario = parse_yaml_scenario(yaml_content)
        console.print(f"[green]✓[/] Parsed scenario: [cyan]{scenario.name}[/]")

        # Validate against schema
        result = validate_scenario(scenario.to_dict())

        # Display results
        if result.valid:
            console.print(f"[green]✓ Validation passed[/]")
        else:
            console.print(f"[red]✗ Validation failed[/]")

        # Display errors if any
        if result.errors:
            error_table = Table(title="Validation Errors")
            error_table.add_column("Path", style="cyan")
            error_table.add_column("Message", style="red")
            for error in result.errors:
                error_table.add_row(error.get('path', 'N/A'), error.get('message', 'Unknown'))
            console.print(error_table)

        # Display warnings
        if result.warnings:
            console.print("[yellow]Warnings:[/]")
            for warning in result.warnings:
                console.print(f"  • {warning}")

        # Save report if requested
        if output:
            report = {
                "file": str(yaml_file),
                "valid": result.valid,
                "errors": result.errors,
                "warnings": result.warnings,
                "scenario": {
                    "id": scenario.scenario_id,
                    "name": scenario.name,
                    "phases": len(scenario.phases)
                }
            }
            with open(output, 'w') as f:
                json.dump(report, f, indent=2)
            console.print(f"[green]✓[/] Report saved to: {output}")

        return 0 if result.valid else 1

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


@cli.command()
@click.argument('yaml_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('waveform.html'),
              help='Output HTML file')
@click.option('--format', 'fmt', type=click.Choice(['html', 'json', 'svg']), default='html',
              help='Output format')
@click.pass_context
def waveform(ctx, yaml_file: Path, output: Path, fmt: str):
    """Generate WaveDrom waveform from YAML scenario."""
    verbose = ctx.obj.get('verbose', False)

    console.print(Panel.fit(f"[bold blue]Generating Waveform: {yaml_file.name}[/]"))

    try:
        # Read and parse YAML
        with open(yaml_file, 'r') as f:
            yaml_content = f.read()

        scenario = parse_yaml_scenario(yaml_content)
        console.print(f"[green]✓[/] Parsed scenario: [cyan]{scenario.name}[/]")

        # Generate waveform
        if fmt == 'html':
            from verilog_flow.stage2 import generate_wavedrom
            html = generate_wavedrom(scenario, output_path=output)
            console.print(f"[green]✓[/] Waveform HTML saved to: [cyan]{output}[/]")
        elif fmt == 'json':
            from verilog_flow.stage2 import generate_wavedrom_json
            wavedrom_json = generate_wavedrom_json(scenario)
            with open(output, 'w') as f:
                json.dump(wavedrom_json, f, indent=2)
            console.print(f"[green]✓[/] WaveDrom JSON saved to: [cyan]{output}[/]")
        elif fmt == 'svg':
            console.print("[yellow]Note:[/] SVG generation requires wavedrom-cli or Node.js")
            from verilog_flow.stage2 import generate_wavedrom_json
            wavedrom_json = generate_wavedrom_json(scenario)
            # Save JSON for external processing
            json_path = output.with_suffix('.json')
            with open(json_path, 'w') as f:
                json.dump(wavedrom_json, f, indent=2)
            console.print(f"[green]✓[/] WaveDrom JSON saved to: [cyan]{json_path}[/]")
            console.print(f"[dim]Run: wavedrom -i {json_path} -s {output}[/]")

        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


@cli.command()
@click.argument('yaml_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('golden_trace.json'),
              help='Output trace file')
@click.option('--format', 'fmt', type=click.Choice(['json', 'vcd']), default='json',
              help='Output format')
@click.pass_context
def trace(ctx, yaml_file: Path, output: Path, fmt: str):
    """Generate Golden Trace from YAML scenario."""
    verbose = ctx.obj.get('verbose', False)

    console.print(Panel.fit(f"[bold blue]Generating Golden Trace: {yaml_file.name}[/]"))

    try:
        # Read and parse YAML
        with open(yaml_file, 'r') as f:
            yaml_content = f.read()

        scenario = parse_yaml_scenario(yaml_content)
        console.print(f"[green]✓[/] Parsed scenario: [cyan]{scenario.name}[/]")

        # Generate golden trace
        golden_trace = generate_golden_trace(scenario)
        console.print(f"[green]✓[/] Generated trace with [cyan]{len(golden_trace.events)}[/] events")

        # Export
        if fmt == 'json':
            golden_trace.save(output)
            console.print(f"[green]✓[/] Golden trace saved to: [cyan]{output}[/]")
        elif fmt == 'vcd':
            vcd_path = output.with_suffix('.vcd')
            vcd_content = golden_trace.to_vcd()
            with open(vcd_path, 'w') as f:
                f.write(vcd_content)
            console.print(f"[green]✓[/] VCD saved to: [cyan]{vcd_path}[/]")

        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


@cli.command()
@click.option('--runs', '-n', default=10, help='Number of recent runs to show')
def dashboard(runs: int):
    """Display KPI dashboard."""
    console.print(Panel.fit("[bold blue]VeriFlow KPI Dashboard[/]"))

    tracker = KPITracker()
    summary = tracker.get_summary(n_runs=runs)

    if isinstance(summary, dict) and "message" in summary:
        console.print(f"[yellow]{summary['message']}[/]")
        return

    # Display metrics
    metrics_table = Table(title=f"Metrics (Last {summary.get('total_runs', 0)} Runs)")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="green")

    metrics_table.add_row("Total Runs", str(summary.get('total_runs', 0)))
    metrics_table.add_row("Pass@1 Rate", f"{summary.get('pass_at_1_rate', 0)*100:.1f}%")
    metrics_table.add_row("Timing Closure", f"{summary.get('timing_closure_rate', 0)*100:.1f}%")
    metrics_table.add_row("Avg Duration", f"{summary.get('avg_duration', 0):.1f}s")
    metrics_table.add_row("Avg Tokens", f"{summary.get('avg_tokens', 0):.0f}")

    console.print(metrics_table)


# Entry point
def main():
    """Entry point for the CLI."""
    try:
        return cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/]")
        import traceback
        console.print(traceback.format_exc())
        return 1


if __name__ == '__main__':
    sys.exit(main())