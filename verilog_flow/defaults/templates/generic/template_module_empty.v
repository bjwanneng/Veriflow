// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Empty Standard Module Shell
 * Category: Core Micro-Architecture
 *
 * Description:
 *   Blank module skeleton with standard file header, parameterized ports,
 *   anti-latch guidelines, and coding style conventions.
 *   Use this as the starting point for any new combinational or
 *   pipelined module.
 *
 * Coding conventions enforced:
 *   1. `resetall / `timescale / `default_nettype none at top
 *   2. Verilog-2001 ANSI port style
 *   3. Parameterized widths with derived localparams
 *   4. Synchronous active-high reset
 *   5. Anti-latch: default assignments in combinational blocks
 *   6. `resetall at bottom to restore default_nettype
 */
module template_module_empty #
(
    // TODO: [Parameters] Define module parameters
    parameter DATA_WIDTH = 8,
    parameter ADDR_WIDTH = 4
)
(
    input  wire                   clk,
    input  wire                   rst,

    // TODO: [Input Ports] Define input interface
    input  wire [DATA_WIDTH-1:0]  data_in,
    input  wire                   valid_in,
    output wire                   ready_out,

    // TODO: [Output Ports] Define output interface
    output wire [DATA_WIDTH-1:0]  data_out,
    output wire                   valid_out,
    input  wire                   ready_in
);

// ===========================================================================
// Derived parameters
// ===========================================================================
// TODO: [Derived Params] Add computed localparams
// localparam DEPTH = 2**ADDR_WIDTH;

// ===========================================================================
// Parameter assertions (simulation only)
// ===========================================================================
initial begin
    if (DATA_WIDTH < 1) begin
        $error("Error: DATA_WIDTH must be >= 1 (instance %m)");
        $finish;
    end
end

// ===========================================================================
// Internal signals and registers
// ===========================================================================
// TODO: [Registers] Declare internal registers
reg [DATA_WIDTH-1:0] data_reg = {DATA_WIDTH{1'b0}};
reg                  valid_reg = 1'b0;

// ===========================================================================
// Output assignments
// ===========================================================================
assign data_out  = data_reg;
assign valid_out = valid_reg;
assign ready_out = ready_in | ~valid_reg;  // TODO: Adjust backpressure logic

// ===========================================================================
// Combinational logic
// ===========================================================================
// IMPORTANT: In any always @* block, assign ALL outputs at the top
// as default values BEFORE the if/case logic. This prevents latches.
//
// Example:
// always @* begin
//     result = 0;              // <-- Default (anti-latch)
//     case (sel)
//         2'd0: result = a;
//         2'd1: result = b;
//         default: result = 0; // <-- Also good practice
//     endcase
// end

// ===========================================================================
// Sequential logic
// ===========================================================================
always @(posedge clk) begin
    // TODO: [Business Logic] Insert your pipeline / processing logic here
    if (ready_out && valid_in) begin
        data_reg  <= data_in;
        valid_reg <= 1'b1;
    end else if (ready_in) begin
        valid_reg <= 1'b0;
    end

    if (rst) begin
        data_reg  <= {DATA_WIDTH{1'b0}};
        valid_reg <= 1'b0;
    end
end

endmodule

`resetall
