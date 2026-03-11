"""Code generation CLI for VeriFlow-Agent."""

import sys
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from verilog_flow.stage1.spec_generator import MicroArchSpec
from verilog_flow.stage3 import RTLCodeGenerator, LintChecker
from verilog_flow.stage3.skill_d import analyze_logic_depth, analyze_cdc

console = Console()


@click.group()
@click.version_option(version="3.0.0", prog_name="vf-codegen")
def cli():
    """VeriFlow Code Generation: Generate RTL from specifications."""
    pass


@cli.command()
@click.argument('spec_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('output'),
              help='Output directory')
@click.option('--lint/--no-lint', default=True, help='Run lint checks')
@click.option('--analyze', is_flag=True, help='Run logic depth and CDC analysis')
def generate(spec_file: Path, output: Path, lint: bool, analyze: bool):
    """Generate RTL code from micro-architecture specification."""

    console.print(Panel.fit(f"[bold blue]Generating RTL from: {spec_file.name}[/]"))

    try:
        # Load specification
        spec = MicroArchSpec.from_file(spec_file)
        console.print(f"[green]✓[/] Loaded spec: [cyan]{spec.module_name}[/]")

        # Generate code
        generator = RTLCodeGenerator()
        module = generator.generate_from_spec(spec)

        # Save generated code
        output.mkdir(parents=True, exist_ok=True)
        file_path = module.save(output)
        console.print(f"[green]✓[/] Generated: [cyan]{file_path}[/]")

        # Run lint if requested
        if lint:
            console.print("\n[bold]Running lint checks...[/]")
            lint_checker = LintChecker()
            lint_result = lint_checker.check(module.verilog_code, str(file_path))

            table = Table(title="Lint Results")
            table.add_column("Severity", style="cyan")
            table.add_column("Rule", style="yellow")
            table.add_column("Message", style="white")
            table.add_column("Line", style="dim")

            for issue in lint_result.issues:
                color = "red" if issue.severity == 'error' else "yellow" if issue.severity == 'warning' else "dim"
                table.add_row(
                    f"[{color}]{issue.severity}[/{color}]",
                    issue.rule_id,
                    issue.message,
                    str(issue.line_number)
                )

            console.print(table)

            if lint_result.passed:
                console.print(f"[green]✓ Lint passed[/]")
            else:
                console.print(f"[red]✗ Lint failed with {lint_result.error_count} errors[/]")

        # Run analysis if requested
        if analyze:
            console.print("\n[bold]Running analysis...[/]")

            # Logic depth analysis
            depth_result = analyze_logic_depth(module.verilog_code)
            if depth_result['violation_count'] > 0:
                console.print(f"[yellow]⚠[/] Found {depth_result['violation_count']} logic depth violations")
                for v in depth_result['violations']:
                    console.print(f"  - {v['signal']}: depth {v['depth']} (line {v['line_number']})")
            else:
                console.print(f"[green]✓[/] Logic depth within target")

            # CDC analysis
            cdc_result = analyze_cdc(module.verilog_code)
            if cdc_result.unsafe_crossings:
                console.print(f"[red]✗[/] Found {len(cdc_result.unsafe_crossings)} unsafe CDC crossings")
            else:
                console.print(f"[green]✓[/] No unsafe CDC crossings detected")

        # Save metadata
        meta_path = output / f"{spec.module_name}_meta.json"
        meta = {
            "module_name": module.module_name,
            "file_path": str(file_path),
            "lines_of_code": module.lines_of_code,
            "parameters": module.parameters,
            "ports": module.ports,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')

        return 0

    except Exception as e:
        console.print(f"[red]Error:[/] {str(e)}")
        import traceback
        console.print(traceback.format_exc())
        return 1


@cli.command()
@click.option('--depth', default=16, help='FIFO depth')
@click.option('--width', default=32, help='Data width')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('output'),
              help='Output directory')
def fifo(depth: int, width: int, output: Path):
    """Generate a synchronous FIFO module."""

    console.print(Panel.fit(f"[bold blue]Generating FIFO (depth={depth}, width={width})[/]"))

    generator = RTLCodeGenerator()
    module = generator.generate_fifo(depth=depth, data_width=width)

    output.mkdir(parents=True, exist_ok=True)
    file_path = module.save(output)

    console.print(f"[green]✓[/] Generated: [cyan]{file_path}[/]")
    console.print(f"  Lines of code: {module.lines_of_code}")

    return 0


@cli.command()
@click.option('--width', default=32, help='Data width')
@click.option('--output', '-o', type=click.Path(path_type=Path), default=Path('output'),
              help='Output directory')
def handshake(width: int, output: Path):
    """Generate a handshake register module."""

    console.print(Panel.fit(f"[bold blue]Generating Handshake Register (width={width})[/]"))

    generator = RTLCodeGenerator()
    module = generator.generate_handshake_register(data_width=width)

    output.mkdir(parents=True, exist_ok=True)
    file_path = module.save(output)

    console.print(f"[green]✓[/] Generated: [cyan]{file_path}[/]")
    console.print(f"  Lines of code: {module.lines_of_code}")

    return 0


@cli.command()
@click.argument('verilog_file', type=click.Path(exists=True, path_type=Path))
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='Save lint report to file')
def lint(verilog_file: Path, output: Path):
    """Run lint checks on a Verilog file."""

    console.print(Panel.fit(f"[bold blue]Linting: {verilog_file.name}[/]"))

    lint_checker = LintChecker()
    result = lint_checker.check_file(verilog_file)

    table = Table(title="Lint Results")
    table.add_column("Severity", style="cyan")
    table.add_column("Rule", style="yellow")
    table.add_column("Message", style="white")
    table.add_column("Line", style="dim")

    for issue in result.issues:
        color = "red" if issue.severity == 'error' else "yellow" if issue.severity == 'warning' else "dim"
        table.add_row(
            f"[{color}]{issue.severity}[/{color}]",
            issue.rule_id,
            issue.message,
            str(issue.line_number)
        )

    console.print(table)
    console.print(f"\nSummary: {result.error_count} errors, {result.warning_count} warnings, {result.info_count} info")

    if output:
        output.write_text(json.dumps(result.to_dict(), indent=2), encoding='utf-8')
        console.print(f"[green]✓[/] Report saved to: {output}")

    return 0 if result.passed else 1


def main():
    """Entry point for the codegen CLI."""
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
