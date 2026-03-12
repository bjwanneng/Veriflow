// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Synchronous FIFO
 * Category: Core Micro-Architecture
 *
 * Description:
 *   Single-clock synchronous FIFO with circular buffer.
 *   Provides full, empty, almost_full, almost_empty flags and data count.
 *
 * Key constraints enforced by this template:
 *   1. Power-of-2 depth for clean pointer wrap-around
 *   2. Correct full/empty detection using extra MSB bit
 *   3. Configurable almost_full / almost_empty thresholds
 *   4. No read when empty, no write when full (protected)
 *   5. Registered output option for timing closure
 *   6. ram_style attribute for BRAM inference on large FIFOs
 */
module template_sync_fifo #
(
    parameter DATA_WIDTH        = 8,
    parameter ADDR_WIDTH        = 4,    // Depth = 2**ADDR_WIDTH
    parameter ALMOST_FULL_THR   = 3,    // almost_full when free slots <= threshold
    parameter ALMOST_EMPTY_THR  = 3,    // almost_empty when used slots <= threshold
    // Output register: 0 = combinational read, 1 = registered (FWFT with 1-cycle latency)
    parameter OUTPUT_REG        = 0
)
(
    input  wire                   clk,
    input  wire                   rst,

    // Write interface
    input  wire [DATA_WIDTH-1:0]  wr_data,
    input  wire                   wr_en,
    output wire                   full,
    output wire                   almost_full,

    // Read interface
    output wire [DATA_WIDTH-1:0]  rd_data,
    input  wire                   rd_en,
    output wire                   empty,
    output wire                   almost_empty,

    // Status
    output wire [ADDR_WIDTH:0]    count
);

parameter DEPTH = 2**ADDR_WIDTH;

// ===========================================================================
// Memory array
// ===========================================================================
(* ram_style = "block" *)
reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

// ===========================================================================
// Pointers and count
// ===========================================================================
// Extra MSB bit for full/empty distinction
reg [ADDR_WIDTH:0] wr_ptr = {(ADDR_WIDTH+1){1'b0}};
reg [ADDR_WIDTH:0] rd_ptr = {(ADDR_WIDTH+1){1'b0}};

wire [ADDR_WIDTH:0] count_w = wr_ptr - rd_ptr;

// Effective write/read enable (protected)
wire wr_en_eff = wr_en & ~full;
wire rd_en_eff = rd_en & ~empty;

// ===========================================================================
// Status flags
// ===========================================================================
// Full:  pointers equal except MSB (buffer wrapped)
// Empty: pointers exactly equal
assign full         = (wr_ptr[ADDR_WIDTH] != rd_ptr[ADDR_WIDTH]) &&
                      (wr_ptr[ADDR_WIDTH-1:0] == rd_ptr[ADDR_WIDTH-1:0]);
assign empty        = (wr_ptr == rd_ptr);
assign almost_full  = (count_w >= (DEPTH - ALMOST_FULL_THR));
assign almost_empty = (count_w <= ALMOST_EMPTY_THR);
assign count        = count_w;

// ===========================================================================
// Read data output
// ===========================================================================
reg [DATA_WIDTH-1:0] rd_data_reg = {DATA_WIDTH{1'b0}};

generate
    if (OUTPUT_REG) begin : gen_reg_output
        assign rd_data = rd_data_reg;
    end else begin : gen_comb_output
        assign rd_data = mem[rd_ptr[ADDR_WIDTH-1:0]];
    end
endgenerate

// ===========================================================================
// Write and read logic
// ===========================================================================
always @(posedge clk) begin
    if (wr_en_eff) begin
        mem[wr_ptr[ADDR_WIDTH-1:0]] <= wr_data;
    end

    if (rd_en_eff) begin
        rd_data_reg <= mem[rd_ptr[ADDR_WIDTH-1:0]];
    end

    // Pointer update
    if (wr_en_eff) begin
        wr_ptr <= wr_ptr + 1;
    end

    if (rd_en_eff) begin
        rd_ptr <= rd_ptr + 1;
    end

    if (rst) begin
        wr_ptr      <= {(ADDR_WIDTH+1){1'b0}};
        rd_ptr      <= {(ADDR_WIDTH+1){1'b0}};
        rd_data_reg <= {DATA_WIDTH{1'b0}};
    end
end

endmodule

`resetall
