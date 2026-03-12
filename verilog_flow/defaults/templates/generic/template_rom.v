// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Read-Only Memory (ROM)
 * Category: Memory Inference
 *
 * Description:
 *   Synchronous ROM with registered output. Initialized from external
 *   .mem / .hex file via $readmemh. Infers BRAM or distributed ROM
 *   depending on depth and synthesis attributes.
 *
 * Key constraints enforced by this template:
 *   1. $readmemh with parameterized init file path
 *   2. Registered output for BRAM inference and timing closure
 *   3. No write port (read-only)
 *   4. Optional second output register stage for higher Fmax
 *   5. rom_style attribute for explicit inference control
 */
module template_rom #
(
    parameter DATA_WIDTH   = 32,
    parameter ADDR_WIDTH   = 10,
    // Initialization file (REQUIRED - must be a valid .mem or .hex file)
    parameter INIT_FILE    = "init_file.mem",
    // 1 = single output register, 2 = double output register
    parameter READ_LATENCY = 1
)
(
    input  wire                   clk,
    input  wire                   en,
    input  wire [ADDR_WIDTH-1:0]  addr,
    output wire [DATA_WIDTH-1:0]  dout
);

parameter DEPTH = 2**ADDR_WIDTH;

// ---------------------------------------------------------------------------
// ROM array
// ---------------------------------------------------------------------------
// Use "block" for BRAM, "distributed" for LUT-based ROM
(* rom_style = "block" *)
reg [DATA_WIDTH-1:0] rom [0:DEPTH-1];

// Output registers
reg [DATA_WIDTH-1:0] dout_reg  = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] dout_pipe = {DATA_WIDTH{1'b0}};

assign dout = (READ_LATENCY == 2) ? dout_pipe : dout_reg;

// ---------------------------------------------------------------------------
// ROM initialization from file
// ---------------------------------------------------------------------------
initial begin
    $readmemh(INIT_FILE, rom);
end

// ---------------------------------------------------------------------------
// Synchronous read with registered output
// NOTE: No async reset - preserves BRAM inference
// ---------------------------------------------------------------------------
always @(posedge clk) begin
    if (en) begin
        dout_reg <= rom[addr];
    end
    if (READ_LATENCY == 2) begin
        dout_pipe <= dout_reg;
    end
end

endmodule

`resetall
