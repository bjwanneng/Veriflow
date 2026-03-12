// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Single-Bit Clock Domain Crossing Synchronizer
 * Category: CDC (Clock Domain Crossing)
 *
 * Description:
 *   2-stage (or 3-stage) flip-flop synchronizer for a single-bit signal
 *   crossing from clk_src domain to clk_dst domain.
 *   Includes Xilinx ASYNC_REG attribute to ensure proper placement.
 *
 * Usage:
 *   - For level signals (enable, flag) that change slowly relative to clk_dst.
 *   - NOT suitable for multi-bit buses or pulse signals (use handshake or
 *     async FIFO for those).
 *   - Set SYNC_STAGES = 3 for higher MTBF in high-speed designs.
 *
 * Key constraints enforced by this template:
 *   1. (* ASYNC_REG = "TRUE" *) on all synchronizer registers
 *   2. No combinational logic between synchronizer stages
 *   3. No reset on synchronizer registers (reset can cause metastability)
 *   4. Parameterized number of sync stages (default 2)
 *   5. Optional initial value for simulation
 */
module template_cdc_sync_bit #
(
    // Number of synchronizer stages (minimum 2, use 3 for higher MTBF)
    parameter SYNC_STAGES = 2,
    // Initial value of synchronizer registers (for simulation only)
    parameter INIT_VALUE  = 1'b0
)
(
    input  wire clk_dst,    // Destination clock domain
    input  wire data_in,    // Input from source clock domain (asynchronous)
    output wire data_out    // Synchronized output in clk_dst domain
);

// ---------------------------------------------------------------------------
// Synchronizer register chain
// ---------------------------------------------------------------------------
(* ASYNC_REG = "TRUE" *)
(* srl_style = "register" *)
reg [SYNC_STAGES-1:0] sync_reg = {SYNC_STAGES{INIT_VALUE}};

always @(posedge clk_dst) begin
    sync_reg <= {sync_reg[SYNC_STAGES-2:0], data_in};
end

assign data_out = sync_reg[SYNC_STAGES-1];

endmodule

`resetall
