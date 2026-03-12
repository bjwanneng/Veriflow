// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: Single-Port Block RAM
 * Category: Memory Inference
 *
 * Description:
 *   Single-port RAM that infers BRAM (Xilinx) or M20K (Intel).
 *
 * Key constraints enforced by this template:
 *   1. NO asynchronous reset on memory output (kills BRAM inference)
 *   2. Registered output for timing closure (READ_LATENCY = 1 or 2)
 *   3. Write-first / Read-first / No-change mode selectable
 *   4. RAM_STYLE attribute for explicit BRAM inference
 *   5. Optional output register for higher Fmax (READ_LATENCY = 2)
 *   6. Byte-enable write support via STRB_WIDTH
 */
module template_ram_sp #
(
    parameter DATA_WIDTH    = 32,
    parameter ADDR_WIDTH    = 10,
    parameter STRB_WIDTH    = (DATA_WIDTH / 8),
    // "write_first", "read_first", or "no_change"
    parameter RAM_MODE      = "write_first",
    // 1 = single output register, 2 = double output register
    parameter READ_LATENCY  = 1,
    // Optional initialization file (set "" to skip)
    parameter INIT_FILE     = ""
)
(
    input  wire                   clk,
    input  wire                   en,
    input  wire [STRB_WIDTH-1:0]  we,
    input  wire [ADDR_WIDTH-1:0]  addr,
    input  wire [DATA_WIDTH-1:0]  din,
    output wire [DATA_WIDTH-1:0]  dout
);

parameter DEPTH     = 2**ADDR_WIDTH;
parameter WORD_SIZE = DATA_WIDTH / STRB_WIDTH;

// ---------------------------------------------------------------------------
// Memory array - BRAM inference
// ---------------------------------------------------------------------------
(* ram_style = "block" *)
reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

// Output registers
reg [DATA_WIDTH-1:0] dout_reg  = {DATA_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] dout_pipe = {DATA_WIDTH{1'b0}};

assign dout = (READ_LATENCY == 2) ? dout_pipe : dout_reg;

// ---------------------------------------------------------------------------
// Memory initialization
// ---------------------------------------------------------------------------
generate
    if (INIT_FILE != "") begin : gen_init_file
        initial begin
            $readmemh(INIT_FILE, mem);
        end
    end else begin : gen_init_zero
        integer i;
        initial begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                mem[i] = {DATA_WIDTH{1'b0}};
            end
        end
    end
endgenerate

// ---------------------------------------------------------------------------
// Read / Write logic
// NOTE: No async reset here - async reset prevents BRAM inference!
// ---------------------------------------------------------------------------
integer k;

generate
    if (RAM_MODE == "write_first") begin : gen_write_first
        always @(posedge clk) begin
            if (en) begin
                for (k = 0; k < STRB_WIDTH; k = k + 1) begin
                    if (we[k]) begin
                        mem[addr][k*WORD_SIZE +: WORD_SIZE] <= din[k*WORD_SIZE +: WORD_SIZE];
                    end
                end
                dout_reg <= mem[addr];
                // Write-first: reflect written data immediately
                for (k = 0; k < STRB_WIDTH; k = k + 1) begin
                    if (we[k]) begin
                        dout_reg[k*WORD_SIZE +: WORD_SIZE] <= din[k*WORD_SIZE +: WORD_SIZE];
                    end
                end
            end
            if (READ_LATENCY == 2) begin
                dout_pipe <= dout_reg;
            end
        end
    end else if (RAM_MODE == "read_first") begin : gen_read_first
        always @(posedge clk) begin
            if (en) begin
                dout_reg <= mem[addr];
                for (k = 0; k < STRB_WIDTH; k = k + 1) begin
                    if (we[k]) begin
                        mem[addr][k*WORD_SIZE +: WORD_SIZE] <= din[k*WORD_SIZE +: WORD_SIZE];
                    end
                end
            end
            if (READ_LATENCY == 2) begin
                dout_pipe <= dout_reg;
            end
        end
    end else begin : gen_no_change
        // no_change: output holds when writing
        always @(posedge clk) begin
            if (en) begin
                for (k = 0; k < STRB_WIDTH; k = k + 1) begin
                    if (we[k]) begin
                        mem[addr][k*WORD_SIZE +: WORD_SIZE] <= din[k*WORD_SIZE +: WORD_SIZE];
                    end
                end
                if (we == {STRB_WIDTH{1'b0}}) begin
                    dout_reg <= mem[addr];
                end
            end
            if (READ_LATENCY == 2) begin
                dout_pipe <= dout_reg;
            end
        end
    end
endgenerate

endmodule

`resetall
