# Stage 3: RTL Code Generation + Lint

You are a Verilog RTL design agent. Your task is to generate all RTL modules AND auto-generated testbenches, and ensure they compile cleanly.

## Working Directory
{{PROJECT_DIR}}

## Spec JSON
{{SPEC_JSON}}

## Provided Architecture Design Specification (Spec JSON)
{{SPEC_JSON}}

## Vendor/Generic Coding Style Rules
{{CODING_STYLE}}

## Available Code Templates
{{TEMPLATES}}

## Mandatory Base Coding Style Constraints
- ANSI port style, 4-space indent
- Combinational: `always @*` with blocking `=`, default assignments at top
- Sequential: non-blocking `<=` only
- `output wire` + `assign`, never `output reg`
- Verilog-2005 ONLY: no `logic`, no `always_ff`, no `always_comb`, no `interface`
- No `reg` driven by `assign` — use `wire` for continuous assignments
- No forward references — declare before use
- Lookup tables MUST be fully expanded (no `// ...` truncation)
- Crypto modules: add byte order comment (e.g., `// Byte mapping: s[0]=[127:120], s[15]=[7:0]`)
- **Reset style**: Read `.veriflow/project_config.json` `coding_style.reset_type` and `coding_style.reset_signal`. Use the configured reset type (sync/async, active-high/low). Examples below use `rst_n` (async active-low) as default — adapt to match your project config.

## Tasks

### 1. Read Specification JSON

Read the specification JSON file from `stage_1_spec/specs/`.

### 2. Generate All RTL Modules

For EVERY module in spec `modules` array, generate complete .v file in `stage_3_codegen/rtl/`:
- No placeholder code, no TODO comments, no empty module bodies
- All lookup tables fully expanded
- All pipeline registers explicitly coded

#### Module Generation Checklist
For each module in spec JSON:
- [ ] Check if corresponding .v file exists
- [ ] Check module name matches
- [ ] Check port list matches spec
- [ ] Check port direction and width are consistent

#### RTL Module Template Structure
```verilog
`resetall
`timescale 1ns/1ps
`default_nettype none

module module_name #(
    parameter PARAM_NAME = 32
) (
    input  wire clk,
    input  wire rst_n,
    // Other ports...
    output wire [31:0] o_data
);

// Local parameter declarations
localparam LP_NAME = 8;

// Internal signal declarations
wire [7:0] sig_name;
reg [7:0] reg_name;

// Combinational logic
always @* begin
    // Default assignments
    sig_name = 8'h00;
    // Logic implementation
    case (...)
        // ...
    endcase
end

// Sequential logic
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        reg_name <= 8'h00;
    end else begin
        reg_name <= sig_name;
    end
end

// Continuous assignment outputs
assign o_data = {reg_name, ...};

endmodule
`resetall
```

### 3. Generate Automatic Testbench (NEW)

Generate testbench for each module in `stage_3_codegen/tb_autogen/`:

#### 3.1 Generate Unit Testbench for Each Non-Top Module

Create `tb_<module_name>.v` with the following structure:

```verilog
`resetall
`timescale 1ns/1ps
`default_nettype none

module tb_module_name;

    reg clk;
    reg rst_n;

    // DUT signal declarations
    reg [7:0] i_byte;
    wire [7:0] o_byte;
    // ... other signals

    // DUT instantiation
    module_name dut (
        .clk(clk),
        .rst_n(rst_n),
        .i_byte(i_byte),
        .o_byte(o_byte)
        // ... other ports
    );

    // Clock generation (300MHz = 3.33ns period)
    initial begin
        clk = 0;
        forever #1.665 clk = ~clk;
    end

    // VCD dump
    initial begin
        $dumpfile("tb_module_name.vcd");
        $dumpvars(0, tb_module_name);
    end

    // Test sequence
    initial begin
        $display("========================================");
        $display("  Testbench for module_name");
        $display("========================================");

        // Reset
        rst_n = 0;
        i_byte = 8'h00;
        // Initialize other inputs...

        repeat(10) @(posedge clk);
        rst_n = 1;
        repeat(5) @(posedge clk);

        $display("[INFO] Reset complete");

        // Run tests
        run_test_basic();
        run_test_cases();

        $display("========================================");
        $display("  ALL TESTS PASSED");
        $display("========================================");
        $finish;
    end

    // Watchdog timer
    initial begin
        #100000;
        $display("[TIMEOUT] Simulation timed out after 100us");
        $finish;
    end

    // Basic functionality test task
    task run_test_basic;
        begin
            $display("[TEST] Basic functionality");
            // Test code...
            $display("[PASS] Basic functionality");
        end
    endtask

    // Specific test case task
    task run_test_cases;
        begin
            $display("[TEST] Test cases");
            // Test code...
            $display("[PASS] Test cases");
        end
    endtask

endmodule
`resetall
```

#### 3.2 Generate Integration Testbench for Top Module

Create `tb_<design_name>_top.v` including:
- Standard test vectors from requirements
- Basic operation tests
- Continuous data tests
- Configuration mode tests (if applicable)

```verilog
`resetall
`timescale 1ns/1ps
`default_nettype none

module tb_design_top;

    // Standard test vectors
    localparam [31:0] TEST_INPUT    = 32'h12345678;
    localparam [31:0] TEST_EXPECTED  = 32'h87654321;

    reg clk;
    reg rst_n;
    reg [31:0] i_data;
    reg i_valid;
    wire [31:0] o_data;
    wire o_valid;

    // DUT instantiation
    design_top dut (
        .clk(clk),
        .rst_n(rst_n),
        .i_data(i_data),
        .i_valid(i_valid),
        .o_data(o_data),
        .o_valid(o_valid)
    );

    // Clock generation (300MHz)
    initial begin
        clk = 0;
        forever #1.665 clk = ~clk;
    end

    // VCD dump
    initial begin
        $dumpfile("tb_design_top.vcd");
        $dumpvars(0, tb_design_top);
    end

    // Main test sequence
    initial begin
        $display("========================================");
        $display("  Design Testbench");
        $display("========================================");

        // Initialize
        rst_n = 0;
        i_data = 32'h0;
        i_valid = 0;

        repeat(10) @(posedge clk);
        rst_n = 1;
        repeat(5) @(posedge clk);

        $display("[INFO] Reset complete");

        // Run tests
        test_basic_operation();
        test_back_to_back();

        $display("========================================");
        $display("  ALL TESTS PASSED");
        $display("========================================");
        $finish;
    end

    // Watchdog
    initial begin
        #100000;
        $display("[TIMEOUT] Simulation timed out");
        $finish;
    end

    // Basic operation test
    task test_basic_operation;
        begin
            $display("[TEST] Basic Operation");
            i_data = TEST_INPUT;
            i_valid = 1;

            @(posedge clk);
            i_valid = 0;

            // Wait pipeline latency
            repeat(5) @(posedge clk);

            if (o_valid !== 1) begin
                $display("[FAIL] o_valid not high");
                $finish;
            end

            if (o_data !== TEST_EXPECTED) begin
                $display("[FAIL] Output mismatch");
                $display("  Expected: %h", TEST_EXPECTED);
                $display("  Got:      %h", o_data);
                $finish;
            end

            $display("[PASS] Basic Operation");
        end
    endtask

    // Back-to-back test
    task test_back_to_back;
        begin
            $display("[TEST] Back-to-back packets");
            // Test continuous input...
            $display("[PASS] Back-to-back");
        end
    endtask

endmodule
`resetall
```

### 4. Compile All RTL Files (Lint Step 1)

After generating all files, compile together (first lint step):

```bash
# Add EDA tools to PATH (adjust for your platform)
export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
mkdir -p stage_3_codegen/reports
iverilog -g2005 -Wall -o /dev/null stage_3_codegen/rtl/*.v > stage_3_codegen/reports/lint_step1.log 2>&1
# NOTE: On Windows, use NUL instead of /dev/null, or redirect output to a temp file.
# If `tee` is unavailable, use file redirection: > file.log 2>&1
```

### 5. Compile Automatic Testbench (Lint Step 2)

Second lint step - compile with testbenches:

```bash
iverilog -g2005 -Wall -o /dev/null stage_3_codegen/rtl/*.v stage_3_codegen/tb_autogen/*.v > stage_3_codegen/reports/lint_step2.log 2>&1
# NOTE: On Windows, use NUL instead of /dev/null, or redirect output to a temp file.
```

### 6. Generate Lint Report

Save lint results to `stage_3_codegen/reports/lint_report.json`:
```json
{
  "lint_step1_passed": true,
  "lint_step2_passed": true,
  "warnings": [],
  "errors": []
}
```

### 7. Testbench Requirements

Each testbench in `tb_autogen/` must include:
- **Adequate debug prints**: At least 3 `$display` or `$monitor` statements for debugging
- **Status prints**: Clear [PASS]/[FAIL] messages for each test
- **Clock generation**: `always` block with clock toggling
- **Reset sequence**: Full reset initialization
- **Watchdog timer**: Prevent simulation hang
- **$finish**: Proper simulation termination

### 8. Error Fixing

If compilation fails, read error messages, fix issues, then recompile. Repeat until 0 errors.

Common errors and fixes:
- `cannot be driven by continuous assignment` → Change `reg` to `wire`
- `Unable to bind wire/reg/memory` → Move declaration before use
- `Variable declaration in unnamed block` → Name the block or move to module level
- Width mismatch → Check if port widths match spec

## Stage 3 Output Directory Structure
```
stage_3_codegen/
├── rtl/
│   ├── module1.v
│   ├── module2.v
│   └── design_top.v
├── tb_autogen/
│   ├── tb_module1.v
│   ├── tb_module2.v
│   └── tb_design_top.v
└── reports/
    ├── lint_step1.log
    ├── lint_step2.log
    └── lint_report.json
```

## Constraints
- Generate ALL modules from spec — no missing files
- Each .v file must be complete and synthesizable
- Must compile with `iverilog -g2005 -Wall` with 0 errors
- Must generate testbench for each module
- Top testbench must include standard test vectors

## Output
Print: list of generated files (RTL and testbench), compilation results (PASS/FAIL), any warnings.

### After Validation: Confirm to Proceed

After running `validate` and validation passes, read and check the project config:

1. Read `.veriflow/project_config.json` and check the value of `confirm_after_validate`
2. If `confirm_after_validate` is true (or the field doesn't exist):
   - Print a summary of what was accomplished in this stage to the user
   - Use AskUserQuestion tool to ask for confirmation before proceeding to `complete`
   - Question: "Stage 3 validation passed! Do you want to proceed to mark this stage complete?"
   - Options: ["Proceed to complete this stage", "Wait, I want to review the outputs first"]
3. If `confirm_after_validate` is false:
   - Automatically proceed to `complete` without asking for user confirmation

{{EXTRA_CONTEXT}}
