// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: AXI-Stream Skid Buffer (Register Slice)
 * Category: Standard Bus Interfaces
 *
 * Description:
 *   Zero-bubble-cycle pipeline register for AXI-Stream interface.
 *   Breaks timing paths without losing throughput. Uses a "skid buffer"
 *   (temp register) to absorb back-pressure while the output register
 *   is being consumed.
 *
 * Source pattern: axi_register_rd.v (skid buffer variant)
 *
 * Key constraints enforced by this template:
 *   1. Zero bubble cycles: sustained throughput of 1 transfer/cycle
 *   2. Correct valid/ready handshake: no combinational path from
 *      s_axis_tready to m_axis_tvalid
 *   3. Two internal registers: output reg + temp (skid) reg
 *   4. Configurable: bypass (0), simple buffer (1), skid buffer (2)
 *   5. Synchronous active-high reset
 */
module template_axis_skid_buffer #
(
    parameter DATA_WIDTH = 8,
    parameter KEEP_ENABLE = (DATA_WIDTH > 8),
    parameter KEEP_WIDTH = (DATA_WIDTH / 8),
    parameter LAST_ENABLE = 1,
    parameter USER_ENABLE = 0,
    parameter USER_WIDTH = 1,
    // Register type: 0 = bypass, 1 = simple (has bubbles), 2 = skid (no bubbles)
    parameter REG_TYPE = 2
)
(
    input  wire                   clk,
    input  wire                   rst,

    // AXI-Stream slave (input)
    input  wire [DATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [KEEP_WIDTH-1:0]  s_axis_tkeep,
    input  wire                   s_axis_tvalid,
    output wire                   s_axis_tready,
    input  wire                   s_axis_tlast,
    input  wire [USER_WIDTH-1:0]  s_axis_tuser,

    // AXI-Stream master (output)
    output wire [DATA_WIDTH-1:0]  m_axis_tdata,
    output wire [KEEP_WIDTH-1:0]  m_axis_tkeep,
    output wire                   m_axis_tvalid,
    input  wire                   m_axis_tready,
    output wire                   m_axis_tlast,
    output wire [USER_WIDTH-1:0]  m_axis_tuser
);

generate

if (REG_TYPE > 1) begin : gen_skid_buffer
// ===========================================================================
// Skid buffer: zero bubble cycles
// ===========================================================================

// Output datapath registers
reg                   s_axis_tready_reg = 1'b0;

reg [DATA_WIDTH-1:0]  m_axis_tdata_reg  = {DATA_WIDTH{1'b0}};
reg [KEEP_WIDTH-1:0]  m_axis_tkeep_reg  = {KEEP_WIDTH{1'b0}};
reg                   m_axis_tvalid_reg = 1'b0, m_axis_tvalid_next;
reg                   m_axis_tlast_reg  = 1'b0;
reg [USER_WIDTH-1:0]  m_axis_tuser_reg  = {USER_WIDTH{1'b0}};

// Temp (skid) registers
reg [DATA_WIDTH-1:0]  temp_tdata_reg  = {DATA_WIDTH{1'b0}};
reg [KEEP_WIDTH-1:0]  temp_tkeep_reg  = {KEEP_WIDTH{1'b0}};
reg                   temp_tvalid_reg = 1'b0, temp_tvalid_next;
reg                   temp_tlast_reg  = 1'b0;
reg [USER_WIDTH-1:0]  temp_tuser_reg  = {USER_WIDTH{1'b0}};

// Datapath control
reg store_input_to_output;
reg store_input_to_temp;
reg store_temp_to_output;

assign s_axis_tready = s_axis_tready_reg;
assign m_axis_tdata  = m_axis_tdata_reg;
assign m_axis_tkeep  = KEEP_ENABLE ? m_axis_tkeep_reg : {KEEP_WIDTH{1'b1}};
assign m_axis_tvalid = m_axis_tvalid_reg;
assign m_axis_tlast  = LAST_ENABLE ? m_axis_tlast_reg : 1'b1;
assign m_axis_tuser  = USER_ENABLE ? m_axis_tuser_reg : {USER_WIDTH{1'b0}};

// Ready early: output is consumed OR temp is empty and output will be free
wire s_axis_tready_early = m_axis_tready | (~temp_tvalid_reg & (~m_axis_tvalid_reg | ~s_axis_tvalid));

// Combinational control logic
always @* begin
    m_axis_tvalid_next = m_axis_tvalid_reg;
    temp_tvalid_next   = temp_tvalid_reg;

    store_input_to_output = 1'b0;
    store_input_to_temp   = 1'b0;
    store_temp_to_output  = 1'b0;

    if (s_axis_tready_reg) begin
        if (m_axis_tready | ~m_axis_tvalid_reg) begin
            // Output free: input -> output
            m_axis_tvalid_next    = s_axis_tvalid;
            store_input_to_output = 1'b1;
        end else begin
            // Output busy: input -> temp (skid)
            temp_tvalid_next    = s_axis_tvalid;
            store_input_to_temp = 1'b1;
        end
    end else if (m_axis_tready) begin
        // Input not ready, output consumed: temp -> output
        m_axis_tvalid_next   = temp_tvalid_reg;
        temp_tvalid_next     = 1'b0;
        store_temp_to_output = 1'b1;
    end
end

// Sequential logic
always @(posedge clk) begin
    if (rst) begin
        s_axis_tready_reg <= 1'b0;
        m_axis_tvalid_reg <= 1'b0;
        temp_tvalid_reg   <= 1'b0;
    end else begin
        s_axis_tready_reg <= s_axis_tready_early;
        m_axis_tvalid_reg <= m_axis_tvalid_next;
        temp_tvalid_reg   <= temp_tvalid_next;
    end

    // Datapath: input -> output
    if (store_input_to_output) begin
        m_axis_tdata_reg <= s_axis_tdata;
        m_axis_tkeep_reg <= s_axis_tkeep;
        m_axis_tlast_reg <= s_axis_tlast;
        m_axis_tuser_reg <= s_axis_tuser;
    end else if (store_temp_to_output) begin
        m_axis_tdata_reg <= temp_tdata_reg;
        m_axis_tkeep_reg <= temp_tkeep_reg;
        m_axis_tlast_reg <= temp_tlast_reg;
        m_axis_tuser_reg <= temp_tuser_reg;
    end

    // Datapath: input -> temp
    if (store_input_to_temp) begin
        temp_tdata_reg <= s_axis_tdata;
        temp_tkeep_reg <= s_axis_tkeep;
        temp_tlast_reg <= s_axis_tlast;
        temp_tuser_reg <= s_axis_tuser;
    end
end

end else if (REG_TYPE == 1) begin : gen_simple_buffer
// ===========================================================================
// Simple buffer: inserts bubble cycles on back-pressure
// ===========================================================================

reg                   s_axis_tready_reg = 1'b0;

reg [DATA_WIDTH-1:0]  m_axis_tdata_reg  = {DATA_WIDTH{1'b0}};
reg [KEEP_WIDTH-1:0]  m_axis_tkeep_reg  = {KEEP_WIDTH{1'b0}};
reg                   m_axis_tvalid_reg = 1'b0, m_axis_tvalid_next;
reg                   m_axis_tlast_reg  = 1'b0;
reg [USER_WIDTH-1:0]  m_axis_tuser_reg  = {USER_WIDTH{1'b0}};

reg store_input_to_output;

assign s_axis_tready = s_axis_tready_reg;
assign m_axis_tdata  = m_axis_tdata_reg;
assign m_axis_tkeep  = KEEP_ENABLE ? m_axis_tkeep_reg : {KEEP_WIDTH{1'b1}};
assign m_axis_tvalid = m_axis_tvalid_reg;
assign m_axis_tlast  = LAST_ENABLE ? m_axis_tlast_reg : 1'b1;
assign m_axis_tuser  = USER_ENABLE ? m_axis_tuser_reg : {USER_WIDTH{1'b0}};

wire s_axis_tready_early = !m_axis_tvalid_next;

always @* begin
    m_axis_tvalid_next    = m_axis_tvalid_reg;
    store_input_to_output = 1'b0;

    if (s_axis_tready_reg) begin
        m_axis_tvalid_next    = s_axis_tvalid;
        store_input_to_output = 1'b1;
    end else if (m_axis_tready) begin
        m_axis_tvalid_next = 1'b0;
    end
end

always @(posedge clk) begin
    if (rst) begin
        s_axis_tready_reg <= 1'b0;
        m_axis_tvalid_reg <= 1'b0;
    end else begin
        s_axis_tready_reg <= s_axis_tready_early;
        m_axis_tvalid_reg <= m_axis_tvalid_next;
    end

    if (store_input_to_output) begin
        m_axis_tdata_reg <= s_axis_tdata;
        m_axis_tkeep_reg <= s_axis_tkeep;
        m_axis_tlast_reg <= s_axis_tlast;
        m_axis_tuser_reg <= s_axis_tuser;
    end
end

end else begin : gen_bypass
// ===========================================================================
// Bypass: wire-through, no register
// ===========================================================================

assign m_axis_tdata  = s_axis_tdata;
assign m_axis_tkeep  = KEEP_ENABLE ? s_axis_tkeep : {KEEP_WIDTH{1'b1}};
assign m_axis_tvalid = s_axis_tvalid;
assign m_axis_tlast  = LAST_ENABLE ? s_axis_tlast : 1'b1;
assign m_axis_tuser  = USER_ENABLE ? s_axis_tuser : {USER_WIDTH{1'b0}};
assign s_axis_tready = m_axis_tready;

end

endgenerate

endmodule

`resetall
