# Stage 2: Virtual Timing Modeling

You are a Verilog RTL design agent. Your task is to create timing scenarios and golden traces.

## Working Directory
{{PROJECT_DIR}}

## Spec JSON
{{SPEC_JSON}}

## Tasks

1. Read the spec JSON from `stage_1_spec/specs/`.

2. Create YAML timing scenarios in `stage_2_timing/scenarios/`. Create at least these scenarios:
   - `reset_sequence.yaml` — reset behavior, S-Box initialization
   - `single_encrypt.yaml` — one block encryption with NIST test vector
   - `single_decrypt.yaml` — one block decryption with NIST test vector
   - `back_to_back.yaml` — consecutive blocks with different keys
   - `config_mode.yaml` — S-Box configuration sequence (if applicable)

   Each YAML file should follow this structure:
   ```yaml
   scenario: <name>
   description: <what this tests>
   clocks:
     clk: {period_ns: 3.33}
   phases:
     - name: reset
       duration_cycles: 5
       signals:
         rst_n: 0
         i_valid: 0
       assertions:
         o_valid: 0
     - name: drive_input
       duration_cycles: 1
       signals:
         rst_n: 1
         i_valid: 1
         i_data: "128'h3243f6a8885a308d313198a2e0370734"
         i_key: "128'h2b7e151628aed2a6abf7158809cf4f3c"
         enc_dec_sel: 1
     - name: wait_pipeline
       duration_cycles: 11
       signals:
         i_valid: 0
       assertions:
         o_valid: {at_cycle: 11, value: 1}
         o_data: {at_cycle: 11, value: "128'h3925841d02dc09fbdc118597196a0b32"}
   ```

3. Generate golden trace JSON files in `stage_2_timing/golden_traces/`:
   - For each scenario, create a `<scenario_name>_trace.json` with expected signal values per cycle.
   - Include NIST FIPS-197 Appendix B test vectors:
     ```
     Key:        2b7e151628aed2a6abf7158809cf4f3c
     Plaintext:  3243f6a8885a308d313198a2e0370734
     Ciphertext: 3925841d02dc09fbdc118597196a0b32
     ```

## Constraints
- Do NOT create any .v files
- YAML must be valid (parseable by PyYAML)
- All hex values must use Verilog notation: `128'hXXXX`
- Include assertions for expected output values
- Every scenario must have a reset phase first

## Output
Print: number of scenarios created, golden traces generated, test vectors included.

{{EXTRA_CONTEXT}}
