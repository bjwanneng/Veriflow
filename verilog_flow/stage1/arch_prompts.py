"""
Structured Prompts for Architecture Decomposition.

Prompt templates that guide the LLM through top-down architecture decomposition.
"""

ARCH_PROMPTS = {
    "step1_requirements": """
# Step 1: Requirements Understanding and Functional Decomposition

You are a hardware architecture expert. Analyze the following natural language requirement and decompose it into structured functional blocks.

## Input Requirement:
{requirement}

## Your Task:
1. Extract key functional requirements
2. Identify main data processing flows
3. List critical performance/timing constraints
4. Identify interface requirements (protocols, data widths)
5. Determine resource constraints (if any)

## Output Format (JSON):
```json
{{
  "functional_requirements": [
    {{"id": "FR-1", "description": "...", "priority": "high|medium|low"}}
  ],
  "data_flows": [
    {{"name": "...", "description": "...", "throughput_requirement": "..."}}
  ],
  "performance_constraints": [
    {{"type": "throughput|latency|frequency", "value": "...", "unit": "..."}}
  ],
  "interface_requirements": [
    {{"name": "...", "protocol": "...", "data_width": ..., "direction": "input|output"}}
  ],
  "resource_constraints": [
    {{"type": "BRAM|DSP|LUT|FF", "limit": "...", "description": "..."}}
  ],
  "design_assumptions": ["..."]
}}
```

## Common Pitfalls to Avoid:
- Don't assume implementation details at this stage
- Focus on WHAT, not HOW
- Ensure all throughput/latency requirements are quantified
- Check for conflicting requirements

## Example:
Input: "Design a 32-bit synchronous FIFO with depth 128"
Output:
```json
{{
  "functional_requirements": [
    {{"id": "FR-1", "description": "Store up to 128 32-bit words", "priority": "high"}},
    {{"id": "FR-2", "description": "Synchronous read/write operations", "priority": "high"}}
  ],
  "data_flows": [
    {{"name": "write_path", "description": "Data input to storage", "throughput_requirement": "1 word/cycle"}},
    {{"name": "read_path", "description": "Storage to data output", "throughput_requirement": "1 word/cycle"}}
  ],
  "performance_constraints": [
    {{"type": "latency", "value": "1", "unit": "cycle"}}
  ],
  "interface_requirements": [
    {{"name": "write_interface", "protocol": "valid/ready", "data_width": 32, "direction": "input"}},
    {{"name": "read_interface", "protocol": "valid/ready", "data_width": 32, "direction": "output"}}
  ],
  "resource_constraints": [],
  "design_assumptions": ["Single clock domain", "No reset during operation"]
}}
```

Now analyze the requirement and provide your structured output.
""",

    "step2_module_partition": """
# Step 2: Module Partitioning

Based on the requirements analysis from Step 1, partition the design into logical modules.

## Input (from Step 1):
{step1_output}

## Your Task:
1. Identify distinct functional modules
2. Classify each module by type (processing/control/memory/interface)
3. Estimate complexity for each module
4. Define module responsibilities clearly
5. Ensure modules have clear boundaries and minimal coupling

## Output Format (JSON):
```json
{{
  "modules": [
    {{
      "name": "module_name",
      "description": "Clear description of module function",
      "module_type": "processing|control|memory|interface",
      "responsibilities": ["...", "..."],
      "estimated_complexity": "low|medium|high",
      "rationale": "Why this module is needed"
    }}
  ],
  "module_hierarchy": {{
    "top_module": "...",
    "submodules": {{
      "module_name": ["child1", "child2"]
    }}
  }},
  "design_rationale": "Overall partitioning strategy explanation"
}}
```

## Design Principles:
- Single Responsibility: Each module should have one clear purpose
- High Cohesion: Related functionality should be grouped together
- Low Coupling: Minimize dependencies between modules
- Reusability: Consider if modules can be reused
- Testability: Modules should be independently testable

## Module Types:
- **processing**: Data transformation, computation (e.g., AES core, HMAC engine)
- **control**: FSM, arbitration, scheduling (e.g., dispatcher, controller)
- **memory**: Storage elements (e.g., FIFO, buffer, register file)
- **interface**: Protocol conversion, I/O (e.g., AXI adapter, CDC)

## Example:
For a "10G AES-CBC encryption engine with HMAC":
```json
{{
  "modules": [
    {{
      "name": "aes_key_expander",
      "description": "Expands 256-bit key into round keys",
      "module_type": "processing",
      "responsibilities": ["Key schedule generation", "Round key storage"],
      "estimated_complexity": "medium",
      "rationale": "Key expansion is independent and can be pre-computed"
    }},
    {{
      "name": "aes_cbc_core",
      "description": "AES-CBC encryption engine",
      "module_type": "processing",
      "responsibilities": ["Block encryption", "CBC chaining"],
      "estimated_complexity": "high",
      "rationale": "Core cryptographic operation"
    }},
    {{
      "name": "input_fifo",
      "description": "Input data buffering",
      "module_type": "memory",
      "responsibilities": ["Absorb burst traffic", "Clock domain crossing"],
      "estimated_complexity": "low",
      "rationale": "Decouple input rate from processing rate"
    }}
  ],
  "module_hierarchy": {{
    "top_module": "crypto_tx_10g",
    "submodules": {{
      "crypto_tx_10g": ["dispatcher", "worker_channel", "gatherer"],
      "worker_channel": ["input_fifo", "aes_cbc_core", "hmac_gen", "output_fifo"]
    }}
  }},
  "design_rationale": "Worker pool architecture for parallel processing"
}}
```

Now partition the design into modules.
""",

    "step3_interface_define": """
# Step 3: Interface Definition

Define detailed port specifications for each module identified in Step 2.

## Input (from Step 2):
{step2_output}

## Your Task:
1. Define all ports for each module (name, direction, width, protocol)
2. Ensure interface consistency between connected modules
3. Specify standard protocols where applicable (AXI-Stream, AXI-Lite, etc.)
4. Add control signals (valid, ready, enable, etc.)
5. Document interface timing requirements

## Output Format (JSON):
```json
{{
  "module_interfaces": [
    {{
      "module_name": "...",
      "ports": [
        {{
          "name": "port_name",
          "direction": "input|output|inout",
          "width": 1,
          "protocol": "axi_stream|axi_lite|custom|clock|reset",
          "description": "Port function description",
          "timing_notes": "Setup/hold requirements if any"
        }}
      ]
    }}
  ],
  "protocol_specifications": {{
    "axi_stream": {{
      "handshake": "valid/ready",
      "data_signals": ["tdata", "tvalid", "tready", "tlast"],
      "optional_signals": ["tkeep", "tuser"]
    }}
  }},
  "interface_constraints": [
    "All AXI-Stream interfaces must support backpressure",
    "..."
  ]
}}
```

## Standard Protocols:
- **axi_stream**: TDATA, TVALID, TREADY, TLAST, [TKEEP, TUSER]
- **axi_lite**: AWADDR, AWVALID, AWREADY, WDATA, WVALID, WREADY, BRESP, BVALID, BREADY, ARADDR, ARVALID, ARREADY, RDATA, RRESP, RVALID, RREADY
- **custom**: Define your own handshake protocol
- **clock**: Single-bit clock input
- **reset**: Active-high or active-low reset

## Port Naming Conventions:
- Inputs: `s_axis_*` (slave), `cfg_*` (config)
- Outputs: `m_axis_*` (master), `status_*`
- Clocks: `clk`, `aclk`
- Resets: `rst_n` (active-low), `rst` (active-high)

## Example:
```json
{{
  "module_interfaces": [
    {{
      "module_name": "aes_cbc_core",
      "ports": [
        {{
          "name": "clk",
          "direction": "input",
          "width": 1,
          "protocol": "clock",
          "description": "System clock",
          "timing_notes": "156.25 MHz"
        }},
        {{
          "name": "rst_n",
          "direction": "input",
          "width": 1,
          "protocol": "reset",
          "description": "Active-low asynchronous reset",
          "timing_notes": ""
        }},
        {{
          "name": "s_axis_data_tdata",
          "direction": "input",
          "width": 128,
          "protocol": "axi_stream",
          "description": "Input plaintext data",
          "timing_notes": "Must be stable when tvalid=1"
        }},
        {{
          "name": "s_axis_data_tvalid",
          "direction": "input",
          "width": 1,
          "protocol": "axi_stream",
          "description": "Input data valid",
          "timing_notes": ""
        }},
        {{
          "name": "s_axis_data_tready",
          "direction": "output",
          "width": 1,
          "protocol": "axi_stream",
          "description": "Ready to accept data",
          "timing_notes": "Registered output"
        }}
      ]
    }}
  ]
}}
```

Now define interfaces for all modules.
""",

    "step4_data_flow": """
# Step 4: Data Flow Analysis

Analyze and document data flow paths through the system.

## Input (from Step 3):
{step3_output}

## Your Task:
1. Identify all major data paths from input to output
2. List modules traversed by each path
3. Estimate latency for each path (in clock cycles)
4. Calculate throughput for each path
5. Identify potential bottlenecks
6. Define module connections (source → destination)

## Output Format (JSON):
```json
{{
  "data_flow_paths": [
    {{
      "name": "main_data_path",
      "description": "Primary data processing flow",
      "modules": ["module1", "module2", "module3"],
      "latency_cycles": 10,
      "throughput": "1 block/cycle",
      "bottleneck_analysis": "Module2 has 5-cycle latency",
      "critical_path": true
    }}
  ],
  "module_connections": [
    {{
      "source_module": "module1",
      "source_port": "m_axis_data",
      "dest_module": "module2",
      "dest_port": "s_axis_data",
      "data_width": 128,
      "protocol": "axi_stream",
      "description": "Encrypted data transfer"
    }}
  ],
  "throughput_analysis": {{
    "system_throughput": "10 Gbps",
    "bottleneck_module": "...",
    "optimization_suggestions": ["..."]
  }}
}}
```

## Analysis Guidelines:
- Latency: Sum of all module latencies in the path
- Throughput: Limited by slowest module in the path
- Identify feedback loops and their impact
- Consider pipeline depth vs. throughput tradeoff

## Example:
```json
{{
  "data_flow_paths": [
    {{
      "name": "encrypt_path",
      "description": "Plaintext → Ciphertext",
      "modules": ["input_fifo", "aes_cbc_core", "hmac_gen", "output_fifo"],
      "latency_cycles": 25,
      "throughput": "128 bits/cycle",
      "bottleneck_analysis": "AES core has 10-cycle latency per block",
      "critical_path": true
    }}
  ],
  "module_connections": [
    {{
      "source_module": "input_fifo",
      "source_port": "m_axis_tdata",
      "dest_module": "aes_cbc_core",
      "dest_port": "s_axis_tdata",
      "data_width": 128,
      "protocol": "axi_stream",
      "description": "Buffered plaintext to AES"
    }}
  ],
  "throughput_analysis": {{
    "system_throughput": "10 Gbps (156.25 MHz × 128 bits / 2)",
    "bottleneck_module": "aes_cbc_core",
    "optimization_suggestions": [
      "Pipeline AES rounds for higher throughput",
      "Use 10 parallel channels for 10x throughput"
    ]
  }}
}}
```

Now analyze the data flows.
""",

    "step5_timing_constraints": """
# Step 5: Timing Constraints and Pipeline Design

Define timing constraints and pipeline structure.

## Input (from Step 4):
{step4_output}

## Additional Context:
- Target frequency: {target_frequency_mhz} MHz
- Clock period: {clock_period_ns} ns

## Your Task:
1. Define clock constraints
2. Identify critical timing paths
3. Design pipeline stages if needed
4. Specify setup/hold requirements
5. Define clock domain crossings (if any)

## Output Format (JSON):
```json
{{
  "timing_constraints": [
    {{
      "constraint_type": "clock_period",
      "target": "clk",
      "value": 6.4,
      "unit": "ns",
      "description": "156.25 MHz system clock"
    }},
    {{
      "constraint_type": "max_delay",
      "target": "input_to_output_path",
      "value": 5.0,
      "unit": "ns",
      "description": "Combinational path limit"
    }}
  ],
  "pipeline_stages": [
    {{
      "stage_id": 0,
      "name": "input_register",
      "operations": ["Capture input data", "Validate control signals"],
      "estimated_delay_ns": 1.5
    }},
    {{
      "stage_id": 1,
      "name": "processing",
      "operations": ["AES round computation"],
      "estimated_delay_ns": 4.0
    }}
  ],
  "total_pipeline_depth": 10,
  "clock_domains": [
    {{
      "domain_name": "clk_sys",
      "frequency_mhz": 156.25,
      "modules": ["module1", "module2"]
    }}
  ],
  "cdc_requirements": [
    {{
      "from_domain": "clk_sys",
      "to_domain": "clk_axi",
      "signals": ["data_bus"],
      "synchronizer_type": "async_fifo"
    }}
  ],
  "critical_paths": [
    {{
      "path_name": "aes_round_logic",
      "estimated_delay_ns": 5.5,
      "slack_ns": 0.9,
      "optimization_needed": false
    }}
  ]
}}
```

## Timing Analysis:
- Clock period = 1000 / frequency (MHz) ns
- Setup slack = Clock period - Path delay - Setup time
- Critical path: Any path with slack < 10% of clock period

## Pipeline Design Principles:
- Balance logic depth across stages
- Insert registers to break long combinational paths
- Consider area vs. throughput tradeoff
- Minimize pipeline bubbles

Now define timing constraints and pipeline structure.
""",

    "step6_summary": """
# Step 6: Architecture Summary and Validation

Synthesize all previous steps into a complete architecture specification.

## Inputs:
- Step 1: {step1_output}
- Step 2: {step2_output}
- Step 3: {step3_output}
- Step 4: {step4_output}
- Step 5: {step5_output}

## Your Task:
1. Validate consistency across all steps
2. Generate architecture summary document
3. List design constraints
4. Identify risks and mitigation strategies
5. Provide implementation recommendations

## Output Format (JSON):
```json
{{
  "architecture_summary": "High-level description of the complete architecture...",
  "design_constraints": [
    "Maximum BRAM usage: 128 blocks per FIFO",
    "All interfaces must support backpressure",
    "..."
  ],
  "validation_results": {{
    "consistency_checks": [
      {{"check": "All module connections valid", "status": "pass"}},
      {{"check": "Throughput requirements met", "status": "pass"}}
    ],
    "warnings": ["Potential timing issue in module X"],
    "errors": []
  }},
  "risk_analysis": [
    {{
      "risk": "Timing closure at 156.25 MHz",
      "severity": "medium",
      "mitigation": "Add pipeline stages in critical paths"
    }}
  ],
  "implementation_recommendations": [
    "Start with key_expander module (lowest complexity)",
    "Use vendor IP for FIFO primitives",
    "..."
  ],
  "estimated_resources": {{
    "LUTs": "~50K",
    "FFs": "~30K",
    "BRAMs": "~40",
    "DSPs": "0"
  }}
}}
```

## Validation Checklist:
- [ ] All modules have defined interfaces
- [ ] All connections are valid (matching widths/protocols)
- [ ] Throughput requirements can be met
- [ ] Timing constraints are achievable
- [ ] Resource estimates are within target device
- [ ] No circular dependencies
- [ ] All data flows have defined paths

Now generate the final architecture summary.
"""
}


def get_prompt_for_step(step: int, context: dict) -> str:
    """
    Get the prompt for a given step, with context injection.

    Args:
        step: Step number (1-6)
        context: Context dictionary containing previous step outputs and parameters

    Returns:
        Formatted prompt string
    """
    prompt_key = f"step{step}_" + [
        "requirements",
        "module_partition",
        "interface_define",
        "data_flow",
        "timing_constraints",
        "summary"
    ][step - 1]

    template = ARCH_PROMPTS.get(prompt_key, "")

    try:
        return template.format(**context)
    except KeyError as e:
        raise ValueError(f"Missing context key for step {step}: {e}")
