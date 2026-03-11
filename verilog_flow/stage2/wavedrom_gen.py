"""WaveDrom waveform generation from timing scenarios."""

import json
from typing import Dict, List, Any, Optional
from pathlib import Path

from .yaml_dsl import TimingScenario, Phase, SignalTransition, TransitionType


def generate_wavedrom_json(scenario: TimingScenario) -> Dict[str, Any]:
    """Generate WaveDrom JSON from a timing scenario."""
    # Collect all unique signals
    all_signals = set()
    for phase in scenario.phases:
        for sig in phase.signals:
            all_signals.add(sig.signal)

    signal_list = sorted(list(all_signals))

    # Build signal waveforms
    signal_waves = []

    for sig_name in signal_list:
        wave = []
        node_map = {}
        node_counter = 0

        for phase in scenario.phases:
            # Find signal transition in this phase
            transition = None
            for sig in phase.signals:
                if sig.signal == sig_name:
                    transition = sig
                    break

            # Determine wave character
            if transition is None:
                # No change, extend previous state
                wave.append(".")
            else:
                # Determine wave based on transition and value
                char = _value_to_wave_char(transition.value, transition.transition)
                wave.append(char)

                # Add node if significant
                if transition.value != ".":
                    node_name = f"n{node_counter}"
                    node_counter += 1
                    pos = len(wave) - 1
                    if pos not in node_map:
                        node_map[pos] = []
                    node_map[pos].append({"name": node_name, "value": str(transition.value)})

        # Build wave string
        wave_str = "".join(wave)

        signal_entry = {
            "name": sig_name,
            "wave": wave_str
        }

        # Add node data if present
        if node_map:
            signal_entry["node"] = node_map

        signal_waves.append(signal_entry)

    # Assemble WaveDrom JSON
    wavedrom = {
        "signal": signal_waves,
        "head": {
            "text": scenario.name,
            "tick": 0
        },
        "foot": {
            "text": scenario.description
        }
    }

    return wavedrom


def _value_to_wave_char(value: Any, transition: TransitionType) -> str:
    """Convert a value to WaveDrom wave character."""
    if transition == TransitionType.RISE:
        return "r"
    elif transition == TransitionType.FALL:
        return "f"
    elif transition == TransitionType.TOGGLE:
        return "t"

    # Value-based
    if isinstance(value, int):
        if value == 0:
            return "0"
        elif value == 1:
            return "1"
        else:
            # Multi-bit value
            return "x"
    elif isinstance(value, str):
        if value in ["0", "1"]:
            return value
        else:
            return "x"  # Unknown/variable

    return "."


def generate_wavedrom(scenario: TimingScenario, output_path: Path = None) -> str:
    """Generate WaveDrom HTML/SVG output."""
    wavedrom_json = generate_wavedrom_json(scenario)

    # Create HTML with embedded WaveDrom
    html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/wavedrom/3.1.0/skins/default.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/wavedrom/3.1.0/wavedrom.min.js"></script>
</head>
<body>
    <h1>{title}</h1>
    <p>{description}</p>
    <script type="WaveDrom">
{wavedrom_json}
    </script>
    <script>
        WaveDrom.ProcessAll();
    </script>
</body>
</html>
"""

    html_content = html_template.format(
        title=scenario.name,
        description=scenario.description,
        wavedrom_json=json.dumps(wavedrom_json, indent=2)
    )

    if output_path:
        output_path = Path(output_path)
        output_path.write_text(html_content, encoding='utf-8')

    return html_content


def generate_wavedrom_svg(wavedrom_json: Dict) -> str:
    """Generate standalone SVG from WaveDrom JSON.

    Note: This is a placeholder. Full implementation would require
    the wavedrom Python library or calling out to Node.js.
    """
    # For now, return a note about implementation
    return """
    <svg xmlns="http://www.w3.org/2000/svg">
        <text x="10" y="20">WaveDrom SVG generation requires wavedrom-cli or Node.js</text>
        <text x="10" y="40">Install: npm install -g wavedrom-cli</text>
        <text x="10" y="60">Usage: wavedrom -i input.json -s output.svg</text>
    </svg>
    """