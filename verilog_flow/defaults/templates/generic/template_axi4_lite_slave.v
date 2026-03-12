// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: AXI4-Lite Slave Register Interface
 * Category: Standard Bus Interfaces
 *
 * Description:
 *   Complete AXI4-Lite slave with register read/write mapping table.
 *   Provides full AW/W/B (write) and AR/R (read) channel handshake.
 *   User only needs to fill in the register map (address-to-register binding).
 *
 * Key constraints enforced by this template:
 *   1. Correct AXI4-Lite handshake: awready/wready asserted for one cycle
 *   2. Write response (bresp) always OKAY
 *   3. Read response (rresp) always OKAY
 *   4. Single-cycle write: AW and W channels accepted simultaneously
 *   5. Registered outputs for timing closure
 *   6. Synchronous active-high reset
 */
module template_axi4_lite_slave #
(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 16,
    parameter STRB_WIDTH = (DATA_WIDTH / 8)
)
(
    input  wire                   clk,
    input  wire                   rst,

    // AXI4-Lite slave interface
    input  wire [ADDR_WIDTH-1:0]  s_axil_awaddr,
    input  wire [2:0]             s_axil_awprot,
    input  wire                   s_axil_awvalid,
    output wire                   s_axil_awready,
    input  wire [DATA_WIDTH-1:0]  s_axil_wdata,
    input  wire [STRB_WIDTH-1:0]  s_axil_wstrb,
    input  wire                   s_axil_wvalid,
    output wire                   s_axil_wready,
    output wire [1:0]             s_axil_bresp,
    output wire                   s_axil_bvalid,
    input  wire                   s_axil_bready,
    input  wire [ADDR_WIDTH-1:0]  s_axil_araddr,
    input  wire [2:0]             s_axil_arprot,
    input  wire                   s_axil_arvalid,
    output wire                   s_axil_arready,
    output wire [DATA_WIDTH-1:0]  s_axil_rdata,
    output wire [1:0]             s_axil_rresp,
    output wire                   s_axil_rvalid,
    input  wire                   s_axil_rready,

    // TODO: [User Ports] Add your register interface ports here
    // Example:
    // output wire [DATA_WIDTH-1:0] ctrl_reg,
    // input  wire [DATA_WIDTH-1:0] status_reg
    output wire                   placeholder_out
);

// ===========================================================================
// Register address map (TODO: customize these)
// ===========================================================================
localparam ADDR_CTRL_REG   = 16'h0000;  // TODO: [Register Map] Control register
localparam ADDR_STATUS_REG = 16'h0004;  // TODO: [Register Map] Status register
localparam ADDR_DATA_REG   = 16'h0008;  // TODO: [Register Map] Data register

// ===========================================================================
// Internal registers
// ===========================================================================
reg s_axil_awready_reg = 1'b0;
reg s_axil_wready_reg  = 1'b0;
reg s_axil_bvalid_reg  = 1'b0;
reg s_axil_arready_reg = 1'b0;
reg [DATA_WIDTH-1:0] s_axil_rdata_reg = {DATA_WIDTH{1'b0}};
reg s_axil_rvalid_reg  = 1'b0;

// TODO: [User Registers] Add your registers here
reg [DATA_WIDTH-1:0] ctrl_reg_r   = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] data_reg_r   = {DATA_WIDTH{1'b0}};

// ===========================================================================
// Output assignments
// ===========================================================================
assign s_axil_awready = s_axil_awready_reg;
assign s_axil_wready  = s_axil_wready_reg;
assign s_axil_bresp   = 2'b00;  // OKAY
assign s_axil_bvalid  = s_axil_bvalid_reg;
assign s_axil_arready = s_axil_arready_reg;
assign s_axil_rdata   = s_axil_rdata_reg;
assign s_axil_rresp   = 2'b00;  // OKAY
assign s_axil_rvalid  = s_axil_rvalid_reg;

assign placeholder_out = ctrl_reg_r[0];

// ===========================================================================
// Write channel: AW + W -> B
// Accept AW and W simultaneously, respond with B
// ===========================================================================
always @(posedge clk) begin
    // Default: deassert ready after one-cycle handshake
    s_axil_awready_reg <= 1'b0;
    s_axil_wready_reg  <= 1'b0;
    s_axil_bvalid_reg  <= s_axil_bvalid_reg && !s_axil_bready;

    // Accept write when both AW and W are valid, and B channel is free
    if (!s_axil_awready_reg && !s_axil_wready_reg &&
        s_axil_awvalid && s_axil_wvalid &&
        (!s_axil_bvalid_reg || s_axil_bready)) begin

        s_axil_awready_reg <= 1'b1;
        s_axil_wready_reg  <= 1'b1;
        s_axil_bvalid_reg  <= 1'b1;

        // TODO: [Write Logic] Register write with byte-enable
        case (s_axil_awaddr[ADDR_WIDTH-1:2])
            ADDR_CTRL_REG[ADDR_WIDTH-1:2]: begin
                // Control register (read-write)
                if (s_axil_wstrb[0]) ctrl_reg_r[ 7: 0] <= s_axil_wdata[ 7: 0];
                if (s_axil_wstrb[1]) ctrl_reg_r[15: 8] <= s_axil_wdata[15: 8];
                if (s_axil_wstrb[2]) ctrl_reg_r[23:16] <= s_axil_wdata[23:16];
                if (s_axil_wstrb[3]) ctrl_reg_r[31:24] <= s_axil_wdata[31:24];
            end
            ADDR_DATA_REG[ADDR_WIDTH-1:2]: begin
                // Data register (read-write)
                if (s_axil_wstrb[0]) data_reg_r[ 7: 0] <= s_axil_wdata[ 7: 0];
                if (s_axil_wstrb[1]) data_reg_r[15: 8] <= s_axil_wdata[15: 8];
                if (s_axil_wstrb[2]) data_reg_r[23:16] <= s_axil_wdata[23:16];
                if (s_axil_wstrb[3]) data_reg_r[31:24] <= s_axil_wdata[31:24];
            end
            default: begin
                // Unmapped address: ignore write
            end
        endcase
    end

    if (rst) begin
        s_axil_awready_reg <= 1'b0;
        s_axil_wready_reg  <= 1'b0;
        s_axil_bvalid_reg  <= 1'b0;
        ctrl_reg_r         <= {DATA_WIDTH{1'b0}};
        data_reg_r         <= {DATA_WIDTH{1'b0}};
    end
end

// ===========================================================================
// Read channel: AR -> R
// ===========================================================================
always @(posedge clk) begin
    s_axil_arready_reg <= 1'b0;
    s_axil_rvalid_reg  <= s_axil_rvalid_reg && !s_axil_rready;

    if (!s_axil_arready_reg && s_axil_arvalid &&
        (!s_axil_rvalid_reg || s_axil_rready)) begin

        s_axil_arready_reg <= 1'b1;
        s_axil_rvalid_reg  <= 1'b1;

        // TODO: [Read Logic] Register read mux
        case (s_axil_araddr[ADDR_WIDTH-1:2])
            ADDR_CTRL_REG[ADDR_WIDTH-1:2]: begin
                s_axil_rdata_reg <= ctrl_reg_r;
            end
            ADDR_STATUS_REG[ADDR_WIDTH-1:2]: begin
                // TODO: [Business Logic] Connect status signals
                s_axil_rdata_reg <= {DATA_WIDTH{1'b0}};
            end
            ADDR_DATA_REG[ADDR_WIDTH-1:2]: begin
                s_axil_rdata_reg <= data_reg_r;
            end
            default: begin
                s_axil_rdata_reg <= {DATA_WIDTH{1'b0}};
            end
        endcase
    end

    if (rst) begin
        s_axil_arready_reg <= 1'b0;
        s_axil_rvalid_reg  <= 1'b0;
        s_axil_rdata_reg   <= {DATA_WIDTH{1'b0}};
    end
end

endmodule

`resetall
