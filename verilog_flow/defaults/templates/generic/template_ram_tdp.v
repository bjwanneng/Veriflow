// Language: Verilog 2001

`resetall
`timescale 1ns / 1ps
`default_nettype none

/*
 * Template: True Dual-Port Block RAM
 * Category: Memory Inference
 *
 * Description:
 *   True dual-port RAM with independent read/write on both ports.
 *   Infers BRAM (Xilinx) or M20K (Intel).
 *
 * Key constraints enforced by this template:
 *   1. NO asynchronous reset on memory output
 *   2. Registered output on both ports
 *   3. Independent clocks supported (set same clock for synchronous TDP)
 *   4. ram_style = "block" attribute
 *   5. Byte-enable write support
 *   6. Write-first behavior on each port
 *
 * Note on simultaneous write collision:
 *   If both ports write to the same address simultaneously, the result is
 *   undefined in hardware. This template does NOT add collision detection.
 *   The user must ensure no write-write collision at the system level.
 */
module template_ram_tdp #
(
    parameter DATA_WIDTH   = 32,
    parameter ADDR_WIDTH   = 10,
    parameter STRB_WIDTH   = (DATA_WIDTH / 8),
    parameter INIT_FILE    = ""
)
(
    // Port A
    input  wire                   clk_a,
    input  wire                   en_a,
    input  wire [STRB_WIDTH-1:0]  we_a,
    input  wire [ADDR_WIDTH-1:0]  addr_a,
    input  wire [DATA_WIDTH-1:0]  din_a,
    output reg  [DATA_WIDTH-1:0]  dout_a = {DATA_WIDTH{1'b0}},

    // Port B
    input  wire                   clk_b,
    input  wire                   en_b,
    input  wire [STRB_WIDTH-1:0]  we_b,
    input  wire [ADDR_WIDTH-1:0]  addr_b,
    input  wire [DATA_WIDTH-1:0]  din_b,
    output reg  [DATA_WIDTH-1:0]  dout_b = {DATA_WIDTH{1'b0}}
);

parameter DEPTH     = 2**ADDR_WIDTH;
parameter WORD_SIZE = DATA_WIDTH / STRB_WIDTH;

// ---------------------------------------------------------------------------
// Memory array - BRAM inference
// ---------------------------------------------------------------------------
(* ram_style = "block" *)
reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

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
// Port A: Read / Write (write-first)
// NOTE: No async reset - preserves BRAM inference
// ---------------------------------------------------------------------------
integer ka;

always @(posedge clk_a) begin
    if (en_a) begin
        for (ka = 0; ka < STRB_WIDTH; ka = ka + 1) begin
            if (we_a[ka]) begin
                mem[addr_a][ka*WORD_SIZE +: WORD_SIZE] <= din_a[ka*WORD_SIZE +: WORD_SIZE];
            end
        end
        dout_a <= mem[addr_a];
        for (ka = 0; ka < STRB_WIDTH; ka = ka + 1) begin
            if (we_a[ka]) begin
                dout_a[ka*WORD_SIZE +: WORD_SIZE] <= din_a[ka*WORD_SIZE +: WORD_SIZE];
            end
        end
    end
end

// ---------------------------------------------------------------------------
// Port B: Read / Write (write-first)
// ---------------------------------------------------------------------------
integer kb;

always @(posedge clk_b) begin
    if (en_b) begin
        for (kb = 0; kb < STRB_WIDTH; kb = kb + 1) begin
            if (we_b[kb]) begin
                mem[addr_b][kb*WORD_SIZE +: WORD_SIZE] <= din_b[kb*WORD_SIZE +: WORD_SIZE];
            end
        end
        dout_b <= mem[addr_b];
        for (kb = 0; kb < STRB_WIDTH; kb = kb + 1) begin
            if (we_b[kb]) begin
                dout_b[kb*WORD_SIZE +: WORD_SIZE] <= din_b[kb*WORD_SIZE +: WORD_SIZE];
            end
        end
    end
end

endmodule

`resetall
