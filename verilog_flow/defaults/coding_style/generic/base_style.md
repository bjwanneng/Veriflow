# base_style.md — Synthesizable Verilog-2001 Coding Style Guide

---

## 1. File Structure

**MUST** Each `.v` file must be organized strictly in the following order:

```
`resetall
`timescale 1ns / 1ps
`default_nettype none

module xxx #( ... )( ... );
// ... module body ...
endmodule

`resetall
```

- **MUST** Place `` `resetall ``, `` `timescale 1ns / 1ps ``, and `` `default_nettype none `` at the beginning of the file, in that order.
- **MUST** Place `` `resetall `` at the end of the file (after `endmodule`) to clear all compiler directive states.
- **MUST NOT** Use any `` `define `` macros inside the module body.

---

## 2. Naming Conventions

### 2.1 Module Names

**MUST** Use all lowercase with underscores (snake_case).

```verilog
// ✅
module priority_encoder #( ... )( ... );
module axi_fifo_rd #( ... )( ... );

// ❌
module PriorityEncoder #( ... )( ... );
module AXI_FIFO_RD #( ... )( ... );
```

### 2.2 Port Names and Internal Signal Names

**MUST** Use all lowercase with underscores (snake_case).

```verilog
// ✅
input  wire [7:0] s_axi_awlen,
output wire        grant_valid,
reg [7:0] read_count_reg;

// ❌
input  wire [7:0] S_AXI_AWLEN,
output wire        grantValid,
```
### 2.3 Register and Next-State Suffixes

**MUST** Register outputs use the `_reg` suffix, and their corresponding combinational next-state signals use the `_next` suffix.

```verilog
// ✅
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;

// ❌
reg [1:0] write_state;
reg [1:0] write_state_d;
reg       s_axi_awready_ff;
```

### 2.4 Temporary/Buffer Register Prefix

**MUST** Registers used for temporary storage such as skid buffers use the `temp_` prefix, while retaining the `_reg` suffix.

```verilog
// ✅
reg [7:0] temp_m_axi_arlen_reg = 8'd0;

// ❌
reg [7:0] m_axi_arlen_buf = 8'd0;
```

### 2.5 Pipeline Register Suffix

**MUST** Additional pipeline stage registers use the `_pipe_reg` suffix.

```verilog
// ✅
reg [DATA_WIDTH-1:0] s_axi_rdata_pipe_reg = {DATA_WIDTH{1'b0}};

// ❌
reg [DATA_WIDTH-1:0] s_axi_rdata_p1 = {DATA_WIDTH{1'b0}};
```

### 2.6 Parameter / Localparam

**MUST** Use all uppercase with underscores (UPPER_SNAKE_CASE).

```verilog
// ✅
parameter DATA_WIDTH = 32,
parameter ADDR_WIDTH = 16,
localparam VALID_ADDR_WIDTH = ADDR_WIDTH - $clog2(STRB_WIDTH);

// ❌
parameter dataWidth = 32;
localparam valid_addr_width = 10;
```

### 2.7 State Machine State Names

**MUST** State names use all uppercase with a descriptive prefix (corresponding to the state register name).

```verilog
// ✅
localparam [1:0]
    WRITE_STATE_IDLE  = 2'd0,
    WRITE_STATE_BURST = 2'd1,
    WRITE_STATE_RESP  = 2'd2;

// ❌
localparam IDLE  = 0;
localparam BURST = 1;
localparam S0 = 0, S1 = 1;
```
---

## 3. Ports and Parameters

### 3.1 ANSI-Style Declaration

**MUST** Use Verilog-2001 ANSI style, declaring port direction, type, and width uniformly in the module header. **MUST NOT** Use Verilog-1995 style port lists with declarations inside the module body.

```verilog
// ✅ Verilog-2001 ANSI style
module axi_ram #
(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 16
)
(
    input  wire                   clk,
    input  wire                   rst,
    input  wire [DATA_WIDTH-1:0]  s_axi_wdata,
    output wire                   s_axi_wready
);

// ❌ Verilog-1995 style
module axi_ram(clk, rst, s_axi_wdata, s_axi_wready);
    input clk;
    input rst;
    input [31:0] s_axi_wdata;
    output s_axi_wready;
```

### 3.2 Explicit Port Type Declaration

**MUST** All ports must explicitly declare the `wire` type keyword.

```verilog
// ✅
input  wire [7:0] s_axi_awlen,
output wire        s_axi_awready,

// ❌
input  [7:0] s_axi_awlen,
output       s_axi_awready,
```

### 3.3 Parameter Comments

**MUST** Each `parameter` must have a brief comment above or inline explaining its meaning.

```verilog
// ✅
// Width of data bus in bits
parameter DATA_WIDTH = 32,
// Width of address bus in bits
parameter ADDR_WIDTH = 16,

// ❌
parameter DATA_WIDTH = 32,
parameter ADDR_WIDTH = 16,
```

### 3.4 Separate Parameter and Port Blocks

**MUST** The parameter list uses a separate `#( ... )` parenthesized block, and the port list uses a separate `( ... )` parenthesized block. The two must be written separately. The opening parenthesis `(` occupies its own line.

```verilog
// ✅
module axi_ram #
(
    parameter DATA_WIDTH = 32
)
(
    input  wire clk,
    input  wire rst
);

// ❌
module axi_ram #(parameter DATA_WIDTH = 32)(
    input  wire clk,
    input  wire rst
);
```
---

## 4. Formatting and Alignment

### 4.1 Indentation

**MUST** Use 4-space indentation. **MUST NOT** Use tabs.

### 4.2 Port Declaration Alignment

**MUST** In port declarations, vertically align the direction keywords (`input`/`output`), type (`wire`), width, and signal names.

```verilog
// ✅
input  wire [ID_WIDTH-1:0]    s_axi_awid,
input  wire [ADDR_WIDTH-1:0]  s_axi_awaddr,
input  wire [7:0]             s_axi_awlen,
input  wire                   s_axi_awvalid,
output wire                   s_axi_awready,

// ❌
input wire [ID_WIDTH-1:0] s_axi_awid,
input wire [ADDR_WIDTH-1:0] s_axi_awaddr,
input wire [7:0] s_axi_awlen,
input wire s_axi_awvalid,
output wire s_axi_awready,
```

### 4.3 Register Declaration Alignment

**SHOULD** Within the same group of register declarations, vertically align the widths and signal names.

```verilog
// ✅
reg [ID_WIDTH-1:0]   read_id_reg    = {ID_WIDTH{1'b0}}, read_id_next;
reg [ADDR_WIDTH-1:0] read_addr_reg  = {ADDR_WIDTH{1'b0}}, read_addr_next;
reg [7:0]            read_count_reg = 8'd0, read_count_next;
reg [2:0]            read_size_reg  = 3'd0, read_size_next;
```

### 4.4 Assign Statement Alignment

**SHOULD** In consecutive `assign` statements, vertically align the equals sign `=`.

```verilog
// ✅
assign s_axi_awready = s_axi_awready_reg;
assign s_axi_wready  = s_axi_wready_reg;
assign s_axi_bid     = s_axi_bid_reg;
assign s_axi_bresp   = 2'b00;
assign s_axi_bvalid  = s_axi_bvalid_reg;
```
---

## 5. Sequential vs. Combinational Logic Separation

### 5.1 Two-Block Separation

**MUST** Place combinational logic (next-state computation) and sequential logic (register updates) in separate `always` blocks.

```verilog
// ✅ Combinational logic block: compute all _next signals
always @* begin
    state_next = state_reg;
    data_next  = data_reg;
    // ... conditional logic ...
end

// ✅ Sequential logic block: register sampling
always @(posedge clk) begin
    state_reg <= state_next;
    data_reg  <= data_next;
    if (rst) begin
        state_reg <= STATE_IDLE;
    end
end

// ❌ Mixed in a single always block
always @(posedge clk) begin
    if (condition)
        state_reg <= STATE_NEXT;  // Next-state logic and register update mixed
end
```

### 5.2 Blocking vs. Non-Blocking Assignments

**MUST** Use only blocking assignments (`=`) in combinational logic blocks (`always @*`).
**MUST** Use only non-blocking assignments (`<=`) in sequential logic blocks (`always @(posedge clk)`).
**MUST NOT** Mix `=` and `<=` in the same `always` block.

```verilog
// ✅
always @* begin
    data_next = data_reg;       // Blocking assignment
end

always @(posedge clk) begin
    data_reg <= data_next;      // Non-blocking assignment
end

// ❌
always @(posedge clk) begin
    temp = a + b;               // Blocking assignment in a sequential block
    data_reg <= temp;
end
```

### 5.3 Combinational Logic Sensitivity List

**MUST** Combinational logic blocks use `always @*` (implicit complete sensitivity list). **MUST NOT** Use explicit sensitivity lists or `always @(*)`.

```verilog
// ✅
always @* begin
    // ...
end

// ❌
always @(a or b or c) begin
    // ...
end

// ❌
always @(*) begin
    // ...
end
```
### 5.4 Latch Elimination — Default Initial Values

**MUST** At the very top of an `always @*` block, assign default values to all output signals (typically the current value of the corresponding `_reg`), before entering any conditional branches. This is the core technique for eliminating latches.

```verilog
// ✅ Assign default values at the top to eliminate latches
always @* begin
    write_state_next    = WRITE_STATE_IDLE;   // Default value
    mem_wr_en           = 1'b0;               // Default value
    write_id_next       = write_id_reg;       // Hold current value
    write_addr_next     = write_addr_reg;     // Hold current value
    s_axi_awready_next  = 1'b0;              // Default value
    s_axi_bvalid_next   = s_axi_bvalid_reg && !s_axi_bready;

    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            // ... only override signals that need to change ...
        end
        // ...
    endcase
end

// ❌ No default values, some branches miss assignments → latches inferred
always @* begin
    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            write_state_next = WRITE_STATE_BURST;
            mem_wr_en = 1'b0;
        end
        WRITE_STATE_BURST: begin
            write_state_next = WRITE_STATE_IDLE;
            // mem_wr_en not assigned → Latch!
        end
    endcase
end
```

### 5.5 Complete Case Coverage

**MUST** Every branch in a `case` statement must explicitly assign `state_next` (even if assigning the current state), or rely on the default values assigned at the top.

```verilog
// ✅ Every branch explicitly assigns state_next
case (read_state_reg)
    READ_STATE_IDLE: begin
        if (condition) begin
            read_state_next = READ_STATE_BURST;
        end else begin
            read_state_next = READ_STATE_IDLE;  // Explicit hold
        end
    end
    READ_STATE_BURST: begin
        if (done) begin
            read_state_next = READ_STATE_IDLE;
        end else begin
            read_state_next = READ_STATE_BURST; // Explicit hold
        end
    end
endcase
```
### 5.6 Single Driver Rule

**MUST** Any `_next` signal may only be assigned in a single `always @*` block.
**MUST** Any `_reg` signal may only be assigned in a single `always @(posedge clk)` block.
**MUST NOT** Drive the same variable from multiple `always` blocks; the synthesis tool will report a Multiple Drivers error.

```verilog
// ✅ Each signal has a single driver
always @* begin
    data_a_next = data_a_reg;
    // ... only drive data_a_next in this block ...
end

always @* begin
    data_b_next = data_b_reg;
    // ... only drive data_b_next in this block ...
end

// ❌ Same signal driven in two always blocks
always @* begin
    if (sel) data_next = a;
end

always @* begin
    if (!sel) data_next = b;  // Multiple Drivers!
end
```

---

## 6. Reset Strategy and Clocking

### 6.1 Synchronous Reset

**MUST** Use synchronous reset. Reset logic is written inside an `if (rst)` condition within the `always @(posedge clk)` block.

```verilog
// ✅ Synchronous reset
always @(posedge clk) begin
    state_reg <= state_next;
    data_reg  <= data_next;

    if (rst) begin
        state_reg <= STATE_IDLE;
        valid_reg <= 1'b0;
    end
end

// ❌ Asynchronous reset
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state_reg <= STATE_IDLE;
    end else begin
        state_reg <= state_next;
    end
end
```
### 6.2 Reset Signal Polarity

**MUST** The reset signal is active-high, named `rst`. **MUST NOT** Use active-low `rst_n`.

```verilog
// ✅
input wire rst,

if (rst) begin
    // Reset logic
end

// ❌
input wire rst_n,

if (!rst_n) begin
    // Reset logic
end
```

### 6.3 Reset Block Placement

**MUST** The `if (rst)` reset block is placed at the end of the `always @(posedge clk)` block (after all normal logic), leveraging the last-assignment-wins behavior to achieve reset priority.

```verilog
// ✅ Reset block at the end
always @(posedge clk) begin
    write_state_reg    <= write_state_next;
    s_axi_awready_reg  <= s_axi_awready_next;
    s_axi_wready_reg   <= s_axi_wready_next;
    s_axi_bvalid_reg   <= s_axi_bvalid_next;

    if (rst) begin
        write_state_reg   <= WRITE_STATE_IDLE;
        s_axi_awready_reg <= 1'b0;
        s_axi_wready_reg  <= 1'b0;
        s_axi_bvalid_reg  <= 1'b0;
    end
end

// ❌ Reset block at the beginning (if-else structure)
always @(posedge clk) begin
    if (rst) begin
        write_state_reg <= WRITE_STATE_IDLE;
    end else begin
        write_state_reg <= write_state_next;
    end
end
```

### 6.4 Selective Reset

**SHOULD** Prefer resetting only control-path signals (state registers, valid, ready, handshake signals). Pure data-path signals (such as payload data, addr) may be left without reset to reduce reset fanout. **However, if it is uncertain whether a register belongs to the control path or data path, reset it to be safe.**

```verilog
// ✅ Reset only control signals (recommended)
if (rst) begin
    read_state_reg      <= READ_STATE_IDLE;
    s_axi_arready_reg   <= 1'b0;
    s_axi_rvalid_reg    <= 1'b0;
    // read_id_reg, read_addr_reg and other pure data signals may be left without reset
end

// ✅ Reset everything when uncertain (safe conservative approach, also acceptable)
if (rst) begin
    read_state_reg    <= READ_STATE_IDLE;
    s_axi_arready_reg <= 1'b0;
    s_axi_rvalid_reg  <= 1'b0;
    some_flag_reg     <= 1'b0;     // Internal flag, uncertain classification, safer to reset
end
```
---

## 7. Register Declaration and Initialization

### 7.1 Initialization at Declaration

**MUST** All `reg` variables must be assigned initial values at declaration.

```verilog
// ✅
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;
reg [7:0] read_count_reg = 8'd0, read_count_next;

// ❌
reg [1:0] write_state_reg;
reg       s_axi_awready_reg;
```

### 7.2 Same-Line Declaration of _reg and _next

**SHOULD** Declare `_reg` and its corresponding `_next` signal on the same line, separated by a comma.

```verilog
// ✅
reg [0:0] read_state_reg = READ_STATE_IDLE, read_state_next;

// Acceptable but not preferred
reg [0:0] read_state_reg = READ_STATE_IDLE;
reg [0:0] read_state_next;
```

### 7.3 Parameterized Width Initialization

**MUST** Use the replication operator `{N{1'bx}}` to initialize registers with parameterized widths, rather than hard-coding `0`.

```verilog
// ✅
reg [ID_WIDTH-1:0] read_id_reg = {ID_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] s_axi_rdata_reg = {DATA_WIDTH{1'b0}};

// ❌
reg [ID_WIDTH-1:0] read_id_reg = 0;
```

### 7.4 Memory Array Declaration

**MUST** Two-dimensional memory arrays are declared in the format `reg [DATA_WIDTH-1:0] mem_name[(2**ADDR_WIDTH)-1:0];`.
**MUST NOT** Initialize memory arrays at declaration (e.g., `= '{default: '0}`) or globally clear them in a synchronous reset block. Memory initialization should be done via loop assignment in an `initial` block or using `$readmemh`/`$readmemb`.
**SHOULD** Use synthesis attributes above the memory declaration to specify the inferred type.

```verilog
// ✅
(* ramstyle = "no_rw_check" *)
reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0];

// ✅ Initialize using an initial block
initial begin
    for (i = 0; i < 2**ADDR_WIDTH; i = i + 1) begin
        mem[i] = 0;
    end
end

// ✅ Initialize using $readmemh
initial begin
    $readmemh("init_data.hex", mem);
end

// ❌ Clearing memory in the rst block of always @(posedge clk)
if (rst) begin
    for (i = 0; i < DEPTH; i = i + 1)
        mem[i] <= 0;  // Not synthesizable or extremely resource-wasteful
end
```
---

## 8. FSM Guidelines

### 8.1 Two-Block State Machine

**MUST** Use a two-block state machine:
- First block: `always @*` combinational logic block, computing `state_next` and all `_next` signals.
- Second block: `always @(posedge clk)` sequential logic block, sampling `_next` into `_reg`.

### 8.2 State Encoding

**MUST** Use `localparam` to define state encodings with explicitly specified widths and values.

```verilog
// ✅
localparam [1:0]
    WRITE_STATE_IDLE  = 2'd0,
    WRITE_STATE_BURST = 2'd1,
    WRITE_STATE_RESP  = 2'd2;

reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;

// ❌ Using parameter instead of localparam
parameter IDLE = 0, BURST = 1;

// ❌ Width not specified
localparam IDLE = 0;
```

### 8.3 State Register Width

**MUST** The width of the state register must match the width declared in the `localparam`.

```verilog
// ✅
localparam [0:0]
    READ_STATE_IDLE  = 1'd0,
    READ_STATE_BURST = 1'd1;

reg [0:0] read_state_reg = READ_STATE_IDLE, read_state_next;

// ❌ Width mismatch
localparam [1:0] READ_STATE_IDLE = 2'd0;
reg [0:0] read_state_reg;
```
---

## 9. Module Instantiation

### 9.1 Named Port Connections

**MUST** Use named port connections (`.port(signal)`), with each connection on its own line. **MUST NOT** Use positional port connections.

```verilog
// ✅
priority_encoder #(
    .WIDTH(PORTS),
    .LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)
)
priority_encoder_inst (
    .input_unencoded(request),
    .output_valid(request_valid),
    .output_encoded(request_index),
    .output_unencoded(request_mask)
);

// ❌ Positional connections
priority_encoder #(PORTS, ARB_LSB_HIGH_PRIORITY)
priority_encoder_inst (request, request_valid, request_index, request_mask);
```

### 9.2 Instance Naming

**SHOULD** Instance names use the `_inst` suffix or a descriptive suffix.

```verilog
// ✅
priority_encoder_inst
priority_encoder_masked

// ❌
u0
pe1
```

---

## 10. Generate Blocks

### 10.1 genvar Declaration Location

**MUST** `genvar` must be declared inside the `generate` block.

```verilog
// ✅
generate
    genvar l, n;
    for (n = 0; n < W/2; n = n + 1) begin : loop_in
        // ...
    end
endgenerate

// ❌
genvar n;
generate
    for (n = 0; n < W/2; n = n + 1) begin : loop_in
        // ...
    end
endgenerate
```

### 10.2 Generate For Labels

**MUST** All `generate for` loop `begin` blocks must have a named label.

```verilog
// ✅
for (n = 0; n < W/2; n = n + 1) begin : loop_in
    // ...
end

// ❌
for (n = 0; n < W/2; n = n + 1) begin
    // ...
end
```
---

## 11. Output Port Driving

**MUST** All `output wire` ports are driven via `assign` statements from internal `_reg` signals. **MUST NOT** Assign `output reg` directly in `always` blocks.

```verilog
// ✅
output wire s_axi_awready,
// ...
reg s_axi_awready_reg = 1'b0, s_axi_awready_next;
assign s_axi_awready = s_axi_awready_reg;

// ❌
output reg s_axi_awready,
// ...
always @(posedge clk) begin
    s_axi_awready <= ...;
end
```

---

## 12. Parameter Validation

**SHOULD** Use an `initial begin` block to perform assertion checks on critical parameters, using `$error` and `$finish`.

```verilog
// ✅
initial begin
    if (WORD_SIZE * STRB_WIDTH != DATA_WIDTH) begin
        $error("Error: data width not evenly divisible (instance %m)");
        $finish;
    end
end
```

---

## 13. Arithmetic and Logic Operations

### 13.1 Width Matching and Explicit Extension

**MUST** When performing addition, subtraction, or comparison, the width of the assignment target must be able to accommodate the result. If there is a carry or width mismatch, explicit bit concatenation or truncation must be performed. **MUST NOT** Rely on Verilog's implicit width extension rules.

```verilog
// ✅ Explicit concatenation, handling carry
wire [8:0] sum_full = a[7:0] + b[7:0];
wire [7:0] sum      = sum_full[7:0];
wire       carry    = sum_full[8];

// ✅ Using bit concatenation to capture carry
assign {carry_out, sum[7:0]} = a[7:0] + b[7:0];

// ❌ Carry is implicitly truncated without any warning
wire [7:0] sum = a[7:0] + b[7:0] + carry_in;
```

### 13.2 Explicit Width Annotation for Constants

**MUST** Use width-annotated constants in assignments and comparisons. **MUST NOT** Use bare integer constants (except `0` and `1` in simple fixed-width scenarios).

```verilog
// ✅
reg [7:0] count_reg = 8'd0;
if (count_reg == 8'd255) begin
    count_reg <= 8'd0;
end

// ❌
reg [7:0] count_reg = 0;
if (count_reg == 255) begin
    count_reg <= 0;
end
```

### 13.3 Bit Selection and Part Selection

**SHOULD** Prefer using the `+:` / `-:` operators for variable-offset part selection, rather than manually computing index ranges.

```verilog
// ✅ Using the +: operator
mem[addr][WORD_SIZE*i +: WORD_SIZE] <= wdata[WORD_SIZE*i +: WORD_SIZE];

// ❌ Manually computing ranges (error-prone)
mem[addr][WORD_SIZE*i + WORD_SIZE - 1 : WORD_SIZE*i] <= wdata[WORD_SIZE*i + WORD_SIZE - 1 : WORD_SIZE*i];
```
