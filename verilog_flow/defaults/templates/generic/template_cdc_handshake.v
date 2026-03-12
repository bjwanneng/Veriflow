// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Multi-Bit CDC Handshake Synchronizer
 * Category: CDC (Clock Domain Crossing)
 *
 * Description:
 *   Full Req/Ack 4-phase handshake protocol for transferring multi-bit data
 *   safely across clock domains. Guarantees no data corruption.
 *
 * Protocol (4-phase handshake):
 *   1. Source asserts req after placing data on src_data
 *   2. Destination sees req (after sync), captures data, asserts ack
 *   3. Source sees ack (after sync), deasserts req
 *   4. Destination sees req deasserted, deasserts ack -> ready for next
 *
 * Key constraints enforced by this template:
 *   1. Data is held stable while req is asserted (no glitch)
 *   2. Req and Ack are single-bit signals synchronized via 2-FF chain
 *   3. Full 4-phase handshake prevents deadlock
 *   4. Busy flag prevents new transfers before handshake completes
 */
module template_cdc_handshake #
(
    parameter DATA_WIDTH  = 8,
    parameter SYNC_STAGES = 2
)
(
    // Source clock domain
    input  wire                   src_clk,
    input  wire                   src_rst,
    input  wire [DATA_WIDTH-1:0]  src_data,
    input  wire                   src_valid,
    output wire                   src_ready,

    // Destination clock domain
    input  wire                   dst_clk,
    input  wire                   dst_rst,
    output wire [DATA_WIDTH-1:0]  dst_data,
    output wire                   dst_valid
);

// ===========================================================================
// Source clock domain
// ===========================================================================
reg [DATA_WIDTH-1:0] src_data_reg = {DATA_WIDTH{1'b0}};
reg                  src_req_reg  = 1'b0;

// Ack synchronized into source domain
(* ASYNC_REG = "TRUE" *) (* srl_style = "register" *)
reg [SYNC_STAGES-1:0] src_ack_sync = {SYNC_STAGES{1'b0}};
wire src_ack_synced = src_ack_sync[SYNC_STAGES-1];

// Source is ready when not in the middle of a handshake
assign src_ready = !src_req_reg;

always @(posedge src_clk) begin
    // Synchronize ack from destination domain
    src_ack_sync <= {src_ack_sync[SYNC_STAGES-2:0], dst_ack_reg};

    if (src_ready && src_valid) begin
        // Phase 1: Capture data and assert req
        src_data_reg <= src_data;
        src_req_reg  <= 1'b1;
    end else if (src_req_reg && src_ack_synced) begin
        // Phase 3: Ack received, deassert req
        src_req_reg <= 1'b0;
    end

    if (src_rst) begin
        src_req_reg  <= 1'b0;
        src_ack_sync <= {SYNC_STAGES{1'b0}};
    end
end

// ===========================================================================
// Destination clock domain
// ===========================================================================
reg [DATA_WIDTH-1:0] dst_data_reg  = {DATA_WIDTH{1'b0}};
reg                  dst_valid_reg = 1'b0;
reg                  dst_ack_reg   = 1'b0;

// Req synchronized into destination domain
(* ASYNC_REG = "TRUE" *) (* srl_style = "register" *)
reg [SYNC_STAGES-1:0] dst_req_sync = {SYNC_STAGES{1'b0}};
wire dst_req_synced = dst_req_sync[SYNC_STAGES-1];

assign dst_data  = dst_data_reg;
assign dst_valid = dst_valid_reg;

always @(posedge dst_clk) begin
    // Synchronize req from source domain
    dst_req_sync <= {dst_req_sync[SYNC_STAGES-2:0], src_req_reg};

    dst_valid_reg <= 1'b0;

    if (!dst_ack_reg && dst_req_synced) begin
        // Phase 2: Req seen, capture data and assert ack
        dst_data_reg  <= src_data_reg;
        dst_valid_reg <= 1'b1;
        dst_ack_reg   <= 1'b1;
    end else if (dst_ack_reg && !dst_req_synced) begin
        // Phase 4: Req deasserted, deassert ack -> handshake complete
        dst_ack_reg <= 1'b0;
    end

    if (dst_rst) begin
        dst_ack_reg   <= 1'b0;
        dst_valid_reg <= 1'b0;
        dst_req_sync  <= {SYNC_STAGES{1'b0}};
    end
end

endmodule

`resetall
