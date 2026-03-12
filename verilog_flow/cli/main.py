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
from verilog_flow.common.project_layout import ProjectLayout
from verilog_flow.common.coding_style import CodingStyleManager
from verilog_flow.common.stage_gate import StageGateChecker
from verilog_flow.common.post_run_analyzer import PostRunAnalyzer

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


@cli.command(name="init")
@click.option('--vendor', '-V', type=click.Choice(['generic', 'xilinx', 'intel']),
              default='generic', help='Target vendor for coding style')
@click.option('--project-dir', '-d', type=click.Path(path_type=Path),
              default=Path('.'), help='Project root directory')
@click.pass_context
def init_project(ctx, vendor: str, project_dir: Path):
    """Initialize a VeriFlow project directory with standard layout."""
    verbose = ctx.obj.get('verbose', False)
    console.print(Panel.fit(f"[bold blue]Initializing VeriFlow project ({vendor})[/]"))

    try:
        layout = ProjectLayout(project_dir)
        layout.initialize()
        console.print("[green]✓[/] Created standard directory layout")

        # Initialize coding style defaults
        mgr = CodingStyleManager(layout)
        mgr.initialize_defaults()
        console.print(f"[green]✓[/] Copied coding style docs & templates for: {', '.join(mgr.list_vendors())}")

        # Attempt legacy migration
        actions = layout.migrate_legacy()
        if actions:
            console.print(f"[green]✓[/] Migrated {len(actions)} items from legacy layout:")
            for a in actions:
                console.print(f"  • {a}")
        else:
            console.print("[dim]No legacy directories to migrate[/]")

        console.print(f"\n[green]Project initialized at:[/] {layout.root}")
        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


@cli.command()
@click.option('--stage', '-s', type=int, default=None, help='Check a specific stage (1-5)')
@click.option('--project-dir', '-d', type=click.Path(path_type=Path),
              default=Path('.'), help='Project root directory')
@click.pass_context
def check(ctx, stage: Optional[int], project_dir: Path):
    """Run stage gate quality checks."""
    verbose = ctx.obj.get('verbose', False)
    console.print(Panel.fit("[bold blue]VeriFlow Stage Gate Check[/]"))

    try:
        layout = ProjectLayout(project_dir)
        checker = StageGateChecker(layout)

        if stage:
            results = [checker.check_stage(stage)]
        else:
            results = checker.check_all()

        # Display results
        result_table = Table(title="Gate Check Results")
        result_table.add_column("Stage", style="cyan")
        result_table.add_column("Status", justify="center")
        result_table.add_column("Errors", style="red", justify="right")
        result_table.add_column("Warnings", style="yellow", justify="right")
        result_table.add_column("Metrics", style="dim")

        all_passed = True
        for r in results:
            status = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"
            if not r.passed:
                all_passed = False
            metrics_str = ", ".join(f"{k}={v}" for k, v in r.metrics.items())
            result_table.add_row(
                str(r.stage), status,
                str(len(r.errors)), str(len(r.warnings)),
                metrics_str)

        console.print(result_table)

        # Show details for failures
        for r in results:
            if r.issues:
                for issue in r.issues:
                    icon = "[red]✗[/]" if issue.severity == "error" else "[yellow]![/]"
                    console.print(f"  {icon} Stage {r.stage}: {issue.message}")

        return 0 if all_passed else 1

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


@cli.command(name="analyze")
@click.option('--runs', '-n', default=10, help='Number of recent runs to analyze')
@click.option('--project-dir', '-d', type=click.Path(path_type=Path),
              default=Path('.'), help='Project root directory')
@click.pass_context
def analyze(ctx, runs: int, project_dir: Path):
    """Run post-execution analysis for self-evolution insights."""
    verbose = ctx.obj.get('verbose', False)
    console.print(Panel.fit("[bold blue]VeriFlow Post-Run Analysis[/]"))

    try:
        layout = ProjectLayout(project_dir)
        analyzer = PostRunAnalyzer(layout)
        report = analyzer.analyze(n_recent=runs)

        console.print(f"Analyzed [cyan]{report.run_count}[/] recent runs\n")

        if not report.insights:
            console.print("[green]No issues found — pipeline is healthy.[/]")
            return 0

        # Display insights
        insight_table = Table(title="Insights")
        insight_table.add_column("Severity", justify="center")
        insight_table.add_column("Category", style="cyan")
        insight_table.add_column("Message")

        for ins in report.insights:
            sev_style = {"high": "[red]HIGH[/]", "medium": "[yellow]MED[/]",
                         "low": "[dim]LOW[/]"}.get(ins.severity, ins.severity)
            insight_table.add_row(sev_style, ins.category, ins.message)

        console.print(insight_table)

        # Stage stats
        if report.stage_stats:
            console.print("\n[bold]Stage Performance:[/]")
            for name, stats in report.stage_stats.items():
                console.print(f"  {name}: avg {stats['avg_s']}s ({stats['runs']} runs)")

        console.print(f"\n[dim]Full report: {layout.get_reports_dir() / 'post_run_analysis.json'}[/]")
        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        return 1


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