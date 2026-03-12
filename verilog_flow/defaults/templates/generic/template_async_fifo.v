// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Asynchronous FIFO Controller
 * Category: CDC (Clock Domain Crossing)
 *
 * Description:
 *   Dual-clock asynchronous FIFO using Gray code pointer synchronization.
 *   Suitable for crossing data between two unrelated clock domains.
 *
 * Key constraints enforced by this template:
 *   1. Gray code conversion for read/write pointers before CDC
 *   2. 2-FF synchronizer with ASYNC_REG on pointer crossing
 *   3. Power-of-2 depth (required for Gray code correctness)
 *   4. Conservative full/empty detection (may report full/empty one cycle early)
 *   5. No async reset on synchronizer FFs
 *   6. Memory inferred as distributed RAM (or BRAM with attribute)
 */
module template_async_fifo #
(
    parameter DATA_WIDTH = 8,
    parameter ADDR_WIDTH = 4,   // FIFO depth = 2**ADDR_WIDTH
    parameter SYNC_STAGES = 2
)
(
    // Write clock domain
    input  wire                   wr_clk,
    input  wire                   wr_rst,
    input  wire [DATA_WIDTH-1:0]  wr_data,
    input  wire                   wr_en,
    output wire                   wr_full,
    output wire [ADDR_WIDTH:0]    wr_count,

    // Read clock domain
    input  wire                   rd_clk,
    input  wire                   rd_rst,
    output wire [DATA_WIDTH-1:0]  rd_data,
    input  wire                   rd_en,
    output wire                   rd_empty,
    output wire [ADDR_WIDTH:0]    rd_count
);

parameter DEPTH = 2**ADDR_WIDTH;

// ===========================================================================
// Memory array
// ===========================================================================
reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

// ===========================================================================
// Write clock domain
// ===========================================================================
reg [ADDR_WIDTH:0] wr_ptr_bin  = {(ADDR_WIDTH+1){1'b0}};
reg [ADDR_WIDTH:0] wr_ptr_gray = {(ADDR_WIDTH+1){1'b0}};

// Read pointer (Gray) synchronized into write domain
(* ASYNC_REG = "TRUE" *) (* srl_style = "register" *)
reg [ADDR_WIDTH:0] wr_rd_ptr_gray_sync [0:SYNC_STAGES-1];

wire [ADDR_WIDTH:0] wr_ptr_bin_next  = wr_ptr_bin + (wr_en & ~wr_full);
wire [ADDR_WIDTH:0] wr_ptr_gray_next = wr_ptr_bin_next ^ (wr_ptr_bin_next >> 1);

// Full: Gray code comparison (MSB and MSB-1 differ, rest equal)
assign wr_full = (wr_ptr_gray == {~wr_rd_ptr_gray_sync[SYNC_STAGES-1][ADDR_WIDTH:ADDR_WIDTH-1],
                                    wr_rd_ptr_gray_sync[SYNC_STAGES-1][ADDR_WIDTH-2:0]});

// Write count (approximate, in write domain)
// Convert synced read Gray pointer back to binary for count calculation
wire [ADDR_WIDTH:0] wr_rd_ptr_bin_synced;
assign wr_rd_ptr_bin_synced = gray2bin(wr_rd_ptr_gray_sync[SYNC_STAGES-1]);
assign wr_count = wr_ptr_bin - wr_rd_ptr_bin_synced;

integer i;

always @(posedge wr_clk) begin
    // Synchronize read pointer (Gray) into write domain
    wr_rd_ptr_gray_sync[0] <= rd_ptr_gray;
    for (i = 1; i < SYNC_STAGES; i = i + 1) begin
        wr_rd_ptr_gray_sync[i] <= wr_rd_ptr_gray_sync[i-1];
    end

    if (wr_en && !wr_full) begin
        mem[wr_ptr_bin[ADDR_WIDTH-1:0]] <= wr_data;
    end

    wr_ptr_bin  <= wr_ptr_bin_next;
    wr_ptr_gray <= wr_ptr_gray_next;

    if (wr_rst) begin
        wr_ptr_bin  <= {(ADDR_WIDTH+1){1'b0}};
        wr_ptr_gray <= {(ADDR_WIDTH+1){1'b0}};
    end
end

// ===========================================================================
// Read clock domain
// ===========================================================================
reg [ADDR_WIDTH:0] rd_ptr_bin  = {(ADDR_WIDTH+1){1'b0}};
reg [ADDR_WIDTH:0] rd_ptr_gray = {(ADDR_WIDTH+1){1'b0}};

// Write pointer (Gray) synchronized into read domain
(* ASYNC_REG = "TRUE" *) (* srl_style = "register" *)
reg [ADDR_WIDTH:0] rd_wr_ptr_gray_sync [0:SYNC_STAGES-1];

wire [ADDR_WIDTH:0] rd_ptr_bin_next  = rd_ptr_bin + (rd_en & ~rd_empty);
wire [ADDR_WIDTH:0] rd_ptr_gray_next = rd_ptr_bin_next ^ (rd_ptr_bin_next >> 1);

// Empty: Gray code comparison (pointers equal)
assign rd_empty = (rd_ptr_gray == rd_wr_ptr_gray_sync[SYNC_STAGES-1]);

// Read data (asynchronous read from distributed RAM)
assign rd_data = mem[rd_ptr_bin[ADDR_WIDTH-1:0]];

// Read count (approximate, in read domain)
wire [ADDR_WIDTH:0] rd_wr_ptr_bin_synced;
assign rd_wr_ptr_bin_synced = gray2bin(rd_wr_ptr_gray_sync[SYNC_STAGES-1]);
assign rd_count = rd_wr_ptr_bin_synced - rd_ptr_bin;

integer j;

always @(posedge rd_clk) begin
    // Synchronize write pointer (Gray) into read domain
    rd_wr_ptr_gray_sync[0] <= wr_ptr_gray;
    for (j = 1; j < SYNC_STAGES; j = j + 1) begin
        rd_wr_ptr_gray_sync[j] <= rd_wr_ptr_gray_sync[j-1];
    end

    rd_ptr_bin  <= rd_ptr_bin_next;
    rd_ptr_gray <= rd_ptr_gray_next;

    if (rd_rst) begin
        rd_ptr_bin  <= {(ADDR_WIDTH+1){1'b0}};
        rd_ptr_gray <= {(ADDR_WIDTH+1){1'b0}};
    end
end

// ===========================================================================
// Gray code to binary conversion function
// ===========================================================================
function [ADDR_WIDTH:0] gray2bin;
    input [ADDR_WIDTH:0] gray;
    integer k;
    begin
        gray2bin[ADDR_WIDTH] = gray[ADDR_WIDTH];
        for (k = ADDR_WIDTH - 1; k >= 0; k = k - 1) begin
            gray2bin[k] = gray2bin[k+1] ^ gray[k];
        end
    end
endfunction

endmodule

`resetall
