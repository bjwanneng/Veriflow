// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Standard Three-Segment / Two-Segment FSM
 * Category: Core Micro-Architecture
 *
 * Description:
 *   Clean three-segment state machine structure:
 *     Segment 1: Combinational next-state logic (always @*)
 *     Segment 2: Sequential state register update (always @(posedge clk))
 *     Segment 3: Registered output logic (always @(posedge clk))
 *   For two-segment FSM, merge Segment 2 and 3 into one sequential block.
 *
 * Key constraints enforced by this template:
 *   1. Default assignments at top of combinational block (anti-latch)
 *   2. Complete case with default branch
 *   3. localparam state encoding (one-hot or binary)
 *   4. Separate _reg / _next naming convention
 *   5. Synchronous active-high reset
 *   6. No combinational output (all outputs registered)
 */
module template_fsm #
(
    parameter DATA_WIDTH = 8
)
(
    input  wire                   clk,
    input  wire                   rst,

    // TODO: [User Ports] Define your interface
    input  wire                   start,
    input  wire [DATA_WIDTH-1:0]  data_in,
    output wire                   busy,
    output wire                   done,
    output wire [DATA_WIDTH-1:0]  data_out
);

// ===========================================================================
// State encoding
// ===========================================================================
// Binary encoding (compact, good for small FSMs)
localparam [1:0]
    STATE_IDLE = 2'd0,
    STATE_WORK = 2'd1,
    STATE_DONE = 2'd2;
    // TODO: [States] Add more states as needed

// For one-hot encoding (better timing for large FSMs), use:
// localparam [2:0]
//     STATE_IDLE = 3'b001,
//     STATE_WORK = 3'b010,
//     STATE_DONE = 3'b100;

// ===========================================================================
// Registers
// ===========================================================================
reg [1:0] state_reg = STATE_IDLE, state_next;

// Internal datapath registers
reg [DATA_WIDTH-1:0] data_reg = {DATA_WIDTH{1'b0}}, data_next;
// TODO: [Registers] Add your datapath registers here

// Output registers
reg busy_reg = 1'b0, busy_next;
reg done_reg = 1'b0, done_next;
reg [DATA_WIDTH-1:0] data_out_reg = {DATA_WIDTH{1'b0}}, data_out_next;

// ===========================================================================
// Output assignments
// ===========================================================================
assign busy     = busy_reg;
assign done     = done_reg;
assign data_out = data_out_reg;

// ===========================================================================
// Segment 1: Combinational next-state and next-output logic
// ===========================================================================
always @* begin
    // -----------------------------------------------------------------------
    // Default assignments (CRITICAL: prevents latches)
    // Every _next signal MUST have a default value here
    // -----------------------------------------------------------------------
    state_next    = state_reg;
    data_next     = data_reg;
    busy_next     = busy_reg;
    done_next     = 1'b0;       // Pulse signals default to 0
    data_out_next = data_out_reg;

    case (state_reg)
        STATE_IDLE: begin
            busy_next = 1'b0;
            if (start) begin
                // TODO: [Business Logic] Capture inputs, initialize
                data_next  = data_in;
                busy_next  = 1'b1;
                state_next = STATE_WORK;
            end
        end

        STATE_WORK: begin
            busy_next = 1'b1;
            // TODO: [Business Logic] Main processing logic
            // Example: data_next = data_reg + 1;

            /* <INSERT_YOUR_STATE_TRANSITION_CONDITIONS_HERE> */
            if (1'b1) begin  // TODO: Replace with actual completion condition
                data_out_next = data_reg;
                state_next    = STATE_DONE;
            end
        end

        STATE_DONE: begin
            busy_next  = 1'b0;
            done_next  = 1'b1;
            state_next = STATE_IDLE;
        end

        default: begin
            // Safe return to IDLE on illegal state
            state_next = STATE_IDLE;
        end
    endcase
end

// ===========================================================================
// Segment 2: Sequential state register update
// ===========================================================================
always @(posedge clk) begin
    if (rst) begin
        state_reg <= STATE_IDLE;
        data_reg  <= {DATA_WIDTH{1'b0}};
    end else begin
        state_reg <= state_next;
        data_reg  <= data_next;
    end
end

// ===========================================================================
// Segment 3: Sequential output register update
// ===========================================================================
always @(posedge clk) begin
    if (rst) begin
        busy_reg     <= 1'b0;
        done_reg     <= 1'b0;
        data_out_reg <= {DATA_WIDTH{1'b0}};
    end else begin
        busy_reg     <= busy_next;
        done_reg     <= done_next;
        data_out_reg <= data_out_next;
    end
end

endmodule

`resetall
