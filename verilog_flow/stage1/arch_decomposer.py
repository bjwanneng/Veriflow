"""
Architecture Decomposer - Structured LLM-guided architecture decomposition engine.

Guides the LLM through a top-down 6-step decomposition process.
"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from .spec_generator import (
    MicroArchSpec, ModuleSpec, PortSpec, ModuleConnection,
    DataFlowPath, PipelineStage, TimingConstraint
)
from .arch_prompts import get_prompt_for_step


@dataclass
class ValidationResult:
    """Validation result for a decomposition step."""
    valid: bool
    errors: list[str]
    warnings: list[str]

    def __bool__(self):
        return self.valid


class ArchDecomposer:
    """
    Structured architecture decomposition engine.

    Guides the LLM through 6 steps of architecture decomposition:
    1. Requirements understanding and functional decomposition
    2. Module partitioning
    3. Interface definition
    4. Data flow analysis
    5. Timing constraints
    6. Architecture summary

    Note: This class does NOT call the LLM API directly. It generates
    prompts and validates outputs. Actual LLM calls are made by the
    outer agent (SKILL.md).
    """

    def __init__(self, target_frequency_mhz: float = 156.25):
        self.target_frequency_mhz = target_frequency_mhz
        self.clock_period_ns = 1000.0 / target_frequency_mhz
        self.context = {}  # Store outputs from each step

    def get_prompt_for_step(self, step: int, requirement: str = "") -> str:
        """
        Get the prompt for a given decomposition step.

        Args:
            step: Step number (1-6)
            requirement: Natural language requirement (only needed for step 1)

        Returns:
            Formatted prompt string
        """
        context = {
            'requirement': requirement,
            'target_frequency_mhz': self.target_frequency_mhz,
            'clock_period_ns': self.clock_period_ns,
        }

        # Inject outputs from previous steps
        for i in range(1, step):
            step_key = f'step{i}_output'
            if step_key in self.context:
                context[step_key] = json.dumps(self.context[step_key], indent=2, ensure_ascii=False)

        return get_prompt_for_step(step, context)

    def validate_step_output(self, step: int, output: Dict[str, Any]) -> ValidationResult:
        """
        Validate the LLM output for a given step.

        Args:
            step: Step number (1-6)
            output: JSON data from LLM output

        Returns:
            ValidationResult object
        """
        errors = []
        warnings = []

        try:
            if step == 1:
                # Validate Step 1: Requirements
                required_keys = ['functional_requirements', 'data_flows', 'performance_constraints']
                for key in required_keys:
                    if key not in output:
                        errors.append(f"Missing required key: {key}")

                if 'functional_requirements' in output:
                    for req in output['functional_requirements']:
                        if 'id' not in req or 'description' not in req:
                            errors.append(f"Invalid functional requirement: {req}")

            elif step == 2:
                # Validate Step 2: Module Partition
                if 'modules' not in output:
                    errors.append("Missing 'modules' key")
                else:
                    for module in output['modules']:
                        required = ['name', 'description', 'module_type']
                        for key in required:
                            if key not in module:
                                errors.append(f"Module missing {key}: {module.get('name', 'unknown')}")

                        if module.get('module_type') not in ['processing', 'control', 'memory', 'interface']:
                            warnings.append(f"Unknown module_type: {module.get('module_type')}")

            elif step == 3:
                # Validate Step 3: Interface Definition
                if 'module_interfaces' not in output:
                    errors.append("Missing 'module_interfaces' key")
                else:
                    for iface in output['module_interfaces']:
                        if 'module_name' not in iface or 'ports' not in iface:
                            errors.append(f"Invalid interface definition: {iface}")

                        for port in iface.get('ports', []):
                            required = ['name', 'direction', 'width']
                            for key in required:
                                if key not in port:
                                    errors.append(f"Port missing {key}: {port.get('name', 'unknown')}")

            elif step == 4:
                # Validate Step 4: Data Flow
                if 'data_flow_paths' not in output:
                    errors.append("Missing 'data_flow_paths' key")
                if 'module_connections' not in output:
                    errors.append("Missing 'module_connections' key")

            elif step == 5:
                # Validate Step 5: Timing Constraints
                if 'timing_constraints' not in output:
                    errors.append("Missing 'timing_constraints' key")
                if 'pipeline_stages' not in output:
                    warnings.append("No pipeline_stages defined")

            elif step == 6:
                # Validate Step 6: Summary
                required_keys = ['architecture_summary', 'design_constraints', 'validation_results']
                for key in required_keys:
                    if key not in output:
                        errors.append(f"Missing required key: {key}")

        except Exception as e:
            errors.append(f"Validation exception: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def save_step_output(self, step: int, output: Dict[str, Any]):
        """Save a step's output to the context."""
        self.context[f'step{step}_output'] = output

    def assemble_spec(self, design_name: str, description: str) -> MicroArchSpec:
        """
        Assemble a complete MicroArchSpec from all step outputs.

        Args:
            design_name: Design name
            description: Design description

        Returns:
            MicroArchSpec object
        """
        # Extract modules from Step 2
        modules = []
        step2 = self.context.get('step2_output', {})
        for mod_data in step2.get('modules', []):
            modules.append(ModuleSpec(
                name=mod_data['name'],
                description=mod_data['description'],
                module_type=mod_data['module_type'],
                ports=[],  # Will be populated in the next step
                parameters=mod_data.get('parameters', {}),
                estimated_complexity=mod_data.get('estimated_complexity', 'medium')
            ))

        # Populate ports from Step 3
        step3 = self.context.get('step3_output', {})
        for iface in step3.get('module_interfaces', []):
            module_name = iface['module_name']
            # Find the matching module
            module = next((m for m in modules if m.name == module_name), None)
            if module:
                for port_data in iface.get('ports', []):
                    module.ports.append(PortSpec(
                        name=port_data['name'],
                        direction=port_data['direction'],
                        width=port_data['width'],
                        protocol=port_data.get('protocol', 'custom'),
                        description=port_data.get('description', '')
                    ))

        # Extract connections and data flows from Step 4
        step4 = self.context.get('step4_output', {})
        module_connections = []
        for conn_data in step4.get('module_connections', []):
            module_connections.append(ModuleConnection(
                source_module=conn_data['source_module'],
                source_port=conn_data['source_port'],
                dest_module=conn_data['dest_module'],
                dest_port=conn_data['dest_port'],
                data_width=conn_data['data_width'],
                protocol=conn_data.get('protocol', 'custom'),
                description=conn_data.get('description', '')
            ))

        data_flow_paths = []
        for flow_data in step4.get('data_flow_paths', []):
            data_flow_paths.append(DataFlowPath(
                name=flow_data['name'],
                description=flow_data['description'],
                modules=flow_data['modules'],
                latency_cycles=flow_data.get('latency_cycles'),
                throughput=flow_data.get('throughput')
            ))

        # Extract timing constraints and pipeline from Step 5
        step5 = self.context.get('step5_output', {})
        timing_constraints = []
        for tc_data in step5.get('timing_constraints', []):
            timing_constraints.append(TimingConstraint(
                constraint_type=tc_data['constraint_type'],
                target=tc_data['target'],
                value=tc_data['value'],
                description=tc_data.get('description', '')
            ))

        pipeline_stages = []
        for ps_data in step5.get('pipeline_stages', []):
            pipeline_stages.append(PipelineStage(
                stage_id=ps_data['stage_id'],
                name=ps_data['name'],
                operations=ps_data['operations'],
                estimated_delay_ns=ps_data.get('estimated_delay_ns')
            ))

        # Extract summary from Step 6
        step6 = self.context.get('step6_output', {})
        architecture_summary = step6.get('architecture_summary', '')
        design_constraints = step6.get('design_constraints', [])

        # Build hierarchy tree
        hierarchy_tree = step2.get('module_hierarchy', {})

        # Create MicroArchSpec
        spec = MicroArchSpec(
            design_name=design_name,
            description=description,
            target_frequency_mhz=self.target_frequency_mhz,
            data_width=128,  # Default value, can be extracted from requirements
            modules=modules,
            module_connections=module_connections,
            data_flow_paths=data_flow_paths,
            hierarchy_tree=hierarchy_tree,
            pipeline_stages=pipeline_stages,
            total_pipeline_depth=len(pipeline_stages),
            timing_constraints=timing_constraints,
            clock_period_ns=self.clock_period_ns,
            design_constraints=design_constraints,
            architecture_summary=architecture_summary,
            vendor='generic',
            metadata={
                'decomposition_steps': list(self.context.keys()),
                'validation_passed': True
            }
        )

        return spec

    def generate_review_summary(self, spec: MicroArchSpec) -> str:
        """
        Generate a human-readable review summary.

        Args:
            spec: MicroArchSpec object

        Returns:
            Markdown-formatted review summary
        """
        summary = f"""# Architecture Review Summary

## Design Overview
- **Name**: {spec.design_name}
- **Description**: {spec.description}
- **Target Frequency**: {spec.target_frequency_mhz} MHz
- **Clock Period**: {spec.clock_period_ns:.2f} ns

## Module Summary
Total Modules: {len(spec.modules)}

"""
        for module in spec.modules:
            summary += f"- **{module.name}** ({module.module_type}): {module.description}\n"
            summary += f"  - Complexity: {module.estimated_complexity}\n"
            summary += f"  - Ports: {len(module.ports)}\n"

        summary += f"\n## Data Flow Paths\n"
        for path in spec.data_flow_paths:
            summary += f"- **{path.name}**: {path.description}\n"
            summary += f"  - Modules: {' → '.join(path.modules)}\n"
            if path.latency_cycles:
                summary += f"  - Latency: {path.latency_cycles} cycles\n"
            if path.throughput:
                summary += f"  - Throughput: {path.throughput}\n"

        summary += f"\n## Pipeline Structure\n"
        summary += f"Total Depth: {spec.total_pipeline_depth} stages\n\n"
        for stage in spec.pipeline_stages:
            summary += f"- Stage {stage.stage_id}: {stage.name}\n"
            summary += f"  - Operations: {', '.join(stage.operations)}\n"

        summary += f"\n## Design Constraints\n"
        for constraint in spec.design_constraints:
            summary += f"- {constraint}\n"

        summary += f"\n## Architecture Summary\n{spec.architecture_summary}\n"

        return summary
