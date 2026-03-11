#!/usr/bin/env python3
"""
Demo script for Stage 2 - Virtual Timing Modeling.

This demonstrates how to use the YAML DSL, WaveDrom generation,
and Golden Trace features of VeriFlow-Agent 3.0.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from verilog_flow.stage2 import (
    parse_yaml_scenario,
    validate_scenario,
    generate_wavedrom,
    generate_golden_trace,
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def demo_yaml_parsing():
    """Demo 1: Parse YAML scenario."""
    console.print(Panel.fit("[bold blue]Demo 1: YAML DSL Parsing[/]"))

    yaml_content = """
scenario_id: "demo_001"
scenario: "Simple_AXI_Write"
description: "Basic AXI4-Lite write transaction"

parameters:
  ADDR: 0x1000
  DATA: 0xDEADBEEF

clocks:
  aclk:
    period: "10ns"  # 100MHz

phases:
  - name: "Setup"
    duration_ns: 20
    signals:
      aresetn: 1
      awvalid: 0
      wvalid: 0
      bready: 0
    assertions:
      - "awready == 0"

  - name: "Address_Phase"
    duration_ns: 10
    signals:
      awaddr: "$ADDR"
      awvalid: 1
      awprot: 0
    assertions:
      - "awready |-> ##[0:1] awvalid"
      - "awaddr == $ADDR"

  - name: "Data_Phase"
    duration_ns: 10
    signals:
      wdata: "$DATA"
      wvalid: 1
      wstrb: 0xF
    assertions:
      - "wready |-> ##[0:1] wvalid"
      - "wdata == $DATA"

  - name: "Response_Phase"
    duration_ns: 10
    signals:
      bready: 1
      awvalid: 0
      wvalid: 0
    assertions:
      - "bvalid |-> ##[0:1] bready"
      - "bresp == 0"
"""

    try:
        scenario = parse_yaml_scenario(yaml_content)
        console.print(f"[green]✓[/] Parsed scenario: [cyan]{scenario.name}[/]")
        console.print(f"[green]✓[/] Scenario ID: [cyan]{scenario.scenario_id}[/]")
        console.print(f"[green]✓[/] Phases: [cyan]{len(scenario.phases)}[/]")
        console.print(f"[green]✓[/] Parameters: [cyan]{list(scenario.parameters.keys())}[/]")

        # Validate
        result = validate_scenario(scenario.to_dict())
        if result.valid:
            console.print(f"[green]✓[/] Validation passed")
        else:
            console.print(f"[red]✗[/] Validation failed with {len(result.errors)} errors")

        return scenario

    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        raise


def demo_wavedrom(scenario):
    """Demo 2: Generate WaveDrom waveform."""
    console.print(Panel.fit("[bold blue]Demo 2: WaveDrom Generation[/]"))

    try:
        from verilog_flow.stage2 import generate_wavedrom_json

        wavedrom_json = generate_wavedrom_json(scenario)
        console.print(f"[green]✓[/] Generated WaveDrom JSON")
        console.print(f"[green]✓[/] Signals: [cyan]{len(wavedrom_json.get('signal', []))}[/]")

        # Show a snippet
        console.print("\n[dim]WaveDrom JSON snippet:[/]")
        snippet = json.dumps(wavedrom_json, indent=2)[:500]
        console.print(f"[dim]{snippet}...[/]")

        return wavedrom_json

    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        raise


def demo_golden_trace(scenario):
    """Demo 3: Generate Golden Trace."""
    console.print(Panel.fit("[bold blue]Demo 3: Golden Trace Generation[/]"))

    try:
        trace = generate_golden_trace(scenario)
        console.print(f"[green]✓[/] Generated Golden Trace")
        console.print(f"[green]✓[/] Events: [cyan]{len(trace.events)}[/]")
        console.print(f"[green]✓[/] Clock period: [cyan]{trace.clock_period_ps} ps[/]")
        console.print(f"[green]✓[/] Signals: [cyan]{len(trace._signal_events)}[/]")

        # Show event summary
        table = Table(title="Event Summary")
        table.add_column("Signal", style="cyan")
        table.add_column("Event Count", style="green")

        for signal, events in list(trace._signal_events.items())[:10]:
            table.add_row(signal, str(len(events)))

        if len(trace._signal_events) > 10:
            table.add_row("...", f"+{len(trace._signal_events) - 10} more")

        console.print(table)

        # Show first few events
        console.print("\n[dim]First 5 events:[/]")
        for i, event in enumerate(trace.events[:5]):
            console.print(f"  [dim]{event.time_ps}ps: {event.signal} = {event.value} ({event.phase_name})[/]")

        return trace

    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        import traceback
        console.print(traceback.format_exc())
        raise


def main():
    """Run all demos."""
    console.print(Panel.fit(
        "[bold green]VeriFlow-Agent 3.0 - Stage 2 Demo[/]\n"
        "[dim]Virtual Timing Modeling with YAML DSL[/]"
    ))

    try:
        # Demo 1: Parse YAML
        scenario = demo_yaml_parsing()

        # Demo 2: Generate WaveDrom
        wavedrom = demo_wavedrom(scenario)

        # Demo 3: Generate Golden Trace
        trace = demo_golden_trace(scenario)

        # Summary
        console.print(Panel.fit(
            "[bold green]All demos completed successfully![/]\n\n"
            f"[cyan]Scenario:[/] {scenario.name}\n"
            f"[cyan]Phases:[/] {len(scenario.phases)}\n"
            f"[cyan]Trace Events:[/] {len(trace.events)}\n"
            f"[cyan]Signals:[/] {len(trace._signal_events)}"
        ))

    except Exception as e:
        console.print(Panel.fit(f"[bold red]Demo failed: {e}[/]"))
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())