## 1. Naming Conventions

*   **MUST** use all lowercase letters and underscores (`_`) for naming modules, ports, internal nets (`wire`), and logic variables (`reg`/`logic`).
*   **MUST** use all uppercase letters and underscores (`_`) for naming parameters (`parameter` / `localparam`).
*   **MUST** add standard suffixes for registers used in clock domain crossing, pipeline delay, or specific functions:
    *   Register output signals use the `_reg` suffix.
    *   Pipeline delay signals use `_dly`, e.g., `_dly1`, `_dly2`.
    *   Next state signals use the `_nxt` suffix.

**Code Example**:
```verilog
Bad Example:
parameter max_width = 32;
wire DataIn;
reg outReg;

Good Example:
parameter MAX_WIDTH = 32;
wire data_in;
reg out_reg;
```

## 2. Ports & Parameters

*   **MUST** enforce the use of Verilog-2001 (ANSI C style) to declare port directions and types uniformly in the module header.
*   **MUST NOT** declare only port names in the module header and then redeclare directions and types inside the module body.

**Code Example**:
```verilog
Bad Example:
module my_logic (clk, din, dout);
  input clk;
  input [7:0] din;
  output reg [7:0] dout;

Good Example:
module my_logic (
  input  wire       clk,
  input  wire [7:0] din,
  output reg  [7:0] dout
);
```

## 3. Formatting & Alignment

*   **MUST** use spaces for indentation; tabs are strictly prohibited. Standard indentation is 2 or 4 spaces.
*   **MUST** maintain vertical alignment in port declarations, parameter declarations, bit-width declarations, and at assignment operators (`=`, `<=`) to maximize readability for both machines and humans.

**Code Example**:
```verilog
Bad Example:
assign a = b & c;
assign out_data = in_data;

Good Example:
assign a        = b & c;
assign out_data = in_data;
```

## 4. Sequential vs Combinational Logic Separation

*   **MUST NOT** mix blocking assignments (`=`) and non-blocking assignments (`<=`) for the same signal. Sequential logic must use `<=`, and combinational logic must use `=`.
*   **MUST** use the implicit sensitivity list `always @(*)` or SystemVerilog's `always_comb` to describe combinational logic; explicitly listing all sensitive signals is strictly prohibited.
*   **MUST** explicitly assign values to variables in all branches of `if-else` or `case` statements in combinational logic, or assign default initial values at the beginning of the `always` block, to completely avoid generating unintended latches.

**Code Example**:
```verilog
Bad Example (generates Latch / incomplete sensitivity list / mixed assignments):
always @(en) begin
  if (en)
    dout <= din; // Mixed use of <= and missing else
end

Good Example (strictly avoiding Latches in combinational logic):
always @(*) begin
  dout_nxt = dout; // Assign default value
  if (en) begin
    dout_nxt = din_reg;
  end
end
```

## 5. Reset Strategy & Clocking

*   **MUST** prefer **synchronous reset**; asynchronous reset must not be used unless architecturally required. Synchronous reset maps more efficiently to dedicated underlying resources such as DSP and BRAM.
*   **MUST** design control signals such as clock enable (`ce`), set (`set`), and reset (`reset`) as **active-high**; active-low signals are strictly prohibited to avoid introducing additional inverter logic.
*   **MUST** give reset logic the highest priority in sequential blocks that contain both enable and reset (i.e., the reset check must be written before the enable check).

**Code Example**:
```verilog
Bad Example (asynchronous, active-low, incorrect priority):
always @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    dout <= 0;
  end else if (en) begin
    dout <= din;
  end
end

Good Example (synchronous, active-high, reset has highest priority):
always @(posedge clk) begin
  if (rst) begin
    dout <= 16'h0000;
  end else if (en) begin
    dout <= din;
  end
end
```

## 6. FSM Guidelines

*   **MUST** use `parameter` or `localparam` to explicitly define all state encodings.
*   **MUST** include a complete `case` statement when describing state machines.
*   **MUST** include a `default` branch at the end of the `case` statement, or use safe attribute constraints, to ensure the state machine can safely recover from illegal states.

**Code Example**:
```verilog
Bad Example (hard-coded states, no default protection):
always @(posedge clk) begin
  case (state)
    2'b00: state <= 2'b01;
    2'b01: state <= 2'b10;
  endcase
end

Good Example (parameterized states, complete default protection):
localparam S_IDLE  = 2'b00;
localparam S_WORK  = 2'b01;
localparam S_DONE  = 2'b10;

always @(posedge clk) begin
  if (rst) begin
    state <= S_IDLE;
  end else begin
    case (state)
      S_IDLE: if (start) state <= S_WORK;
      S_WORK: if (done)  state <= S_DONE;
      S_DONE: state <= S_IDLE;
      default: state <= S_IDLE;
    endcase
  end
end
```
```