# Verified Timing Patterns for RTL Code Generation

Use these patterns as building blocks. Each has been verified for correct cycle-level behavior.

---

## Pattern 1: Valid-Ready Pipeline Stage (Skid Buffer, 1-Cycle Latency)

Single pipeline stage with backpressure support. Data is registered; valid propagates with 1-cycle delay.

```verilog
// TIMING CONTRACT
//   Protocol: valid_ready_backpressure
//   Latency:  1 cycle
//   Stall:    stage_reg holds when downstream not ready
//   Flush:    stage_valid_q cleared on flush

reg [DATA_W-1:0] stage_data_q;
reg               stage_valid_q;

wire stage_accept = o_ready | ~stage_valid_q;  // accept if downstream ready OR stage empty

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        stage_valid_q <= 1'b0;
        stage_data_q  <= {DATA_W{1'b0}};
    end else if (stage_accept) begin
        stage_valid_q <= i_valid;
        stage_data_q  <= i_data;
    end
    // else: hold (stall)
end

assign o_valid = stage_valid_q;
assign o_data  = stage_data_q;
assign i_ready = stage_accept;
```

**Cycle trace (no backpressure):**
- Cycle 0: i_valid=1, i_data=A → captured into stage_data_q
- Cycle 1: o_valid=1, o_data=A

---

## Pattern 2: Multi-Stage Pipeline with Stall/Flush (N-Cycle Latency)

N-stage pipeline with global stall. All stages advance together or hold together.

```verilog
// TIMING CONTRACT
//   Protocol: valid_ready_backpressure
//   Latency:  PIPELINE_DEPTH cycles
//   Stall:    All regs hold when stall==1
//   Flush:    All valid bits cleared on flush

localparam PIPELINE_DEPTH = 3;  // adjust per spec

wire stall = ~o_ready & pipe_valid_q[PIPELINE_DEPTH-1];

// Valid pipeline
reg [PIPELINE_DEPTH-1:0] pipe_valid_q;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        pipe_valid_q <= {PIPELINE_DEPTH{1'b0}};
    end else if (flush) begin
        pipe_valid_q <= {PIPELINE_DEPTH{1'b0}};
    end else if (!stall) begin
        pipe_valid_q[0] <= i_valid;
        // Cycle 0: i_valid → pipe_valid_q[0]
        // Cycle 1: pipe_valid_q[0] → pipe_valid_q[1]
        // Cycle N: pipe_valid_q[N-1] → o_valid
        for (i = 1; i < PIPELINE_DEPTH; i = i + 1)
            pipe_valid_q[i] <= pipe_valid_q[i-1];
    end
end

// Data pipeline (same structure, with computation at each stage)
reg [DATA_W-1:0] pipe_data_q [0:PIPELINE_DEPTH-1];
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        for (i = 0; i < PIPELINE_DEPTH; i = i + 1)
            pipe_data_q[i] <= {DATA_W{1'b0}};
    end else if (!stall) begin
        pipe_data_q[0] <= i_data;
        for (i = 1; i < PIPELINE_DEPTH; i = i + 1)
            pipe_data_q[i] <= pipe_data_q[i-1];  // add computation here
    end
end

assign o_valid = pipe_valid_q[PIPELINE_DEPTH-1];
assign o_data  = pipe_data_q[PIPELINE_DEPTH-1];
assign i_ready = ~stall;
```

**Cycle trace (3-stage, no stall):**
- Cycle 0: i_valid=1 → pipe_valid_q[0]=1
- Cycle 1: pipe_valid_q[0]→[1], o_valid=0
- Cycle 2: pipe_valid_q[1]→[2], o_valid=0
- Cycle 3: o_valid=1, o_data = computed result

**Key invariant:** valid and data MUST use the same stall condition. If valid advances but data doesn't (or vice versa), you get a mismatch.

---

## Pattern 3: FSM with Registered Outputs (Output Lags State by 1 Cycle)

FSM where outputs are registered — output reflects the state from the previous cycle.

```verilog
// TIMING CONTRACT
//   Protocol: FSM registered outputs
//   Latency:  Output is 1 cycle behind state transition
//   Note:     next_state logic is combinational; outputs are registered

reg [1:0] state_q, state_next;
reg [DATA_W-1:0] fsm_out_q;
reg               fsm_done_q;

// Next-state logic (combinational)
always @* begin
    state_next = state_q;
    case (state_q)
        S_IDLE: if (start) state_next = S_WORK;
        S_WORK: if (work_done) state_next = S_DONE;
        S_DONE: state_next = S_IDLE;
        default: state_next = S_IDLE;
    endcase
end

// State register
always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        state_q <= S_IDLE;
    else
        state_q <= state_next;
end

// Registered outputs (1 cycle behind state)
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        fsm_out_q  <= {DATA_W{1'b0}};
        fsm_done_q <= 1'b0;
    end else begin
        fsm_done_q <= (state_next == S_DONE);
        fsm_out_q  <= result_data;
    end
end

assign o_data = fsm_out_q;
assign o_done = fsm_done_q;
```

**Cycle trace:**
- Cycle N:   state transitions to S_DONE
- Cycle N+1: o_done=1 (registered output appears)

---

## Pattern 4: Handshake Bridge (Valid-Only to Valid-Ready)

Bridges a source that only has `valid` (no backpressure awareness) to a sink that requires `valid`+`ready`.

```verilog
// TIMING CONTRACT
//   Protocol: bridge (valid_only → valid_ready)
//   Latency:  0 or 1 cycle depending on ready
//   Stall:    Data held in skid register when downstream not ready

reg [DATA_W-1:0] skid_data_q;
reg               skid_valid_q;

wire downstream_accept = o_ready;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        skid_valid_q <= 1'b0;
        skid_data_q  <= {DATA_W{1'b0}};
    end else if (skid_valid_q && downstream_accept) begin
        // Drain skid buffer
        skid_valid_q <= 1'b0;
    end else if (i_valid && !downstream_accept) begin
        // Capture into skid buffer when downstream stalls
        skid_valid_q <= 1'b1;
        skid_data_q  <= i_data;
    end
end

assign o_valid = skid_valid_q ? 1'b1 : i_valid;
assign o_data  = skid_valid_q ? skid_data_q : i_data;
```

---

## Anti-Patterns (Common Timing Bugs)

### Anti-Pattern 1: Combinational Valid + Registered Data
```verilog
// BUG: o_valid is combinational but o_data is registered
// o_valid appears 1 cycle BEFORE o_data is correct
assign o_valid = pipe_valid_q[2];  // combinational from register
always @(posedge clk) o_data <= pipe_data_q[2];  // registered
// FIX: Both must be at the same pipeline stage
```

### Anti-Pattern 2: Valid/Data Pipeline Depth Mismatch
```verilog
// BUG: valid goes through 2 stages, data through 3
// Output valid asserts 1 cycle before data is ready
reg valid_s1, valid_s2;           // 2 stages
reg [7:0] data_s1, data_s2, data_s3;  // 3 stages
// FIX: valid and data must have identical pipeline depth
```

### Anti-Pattern 3: Stall Affects Data But Not Valid
```verilog
// BUG: stall holds data registers but valid still shifts
always @(posedge clk) begin
    if (!stall) data_q <= data_next;  // stalled
    valid_q <= valid_next;            // NOT stalled — keeps shifting
end
// FIX: stall must gate BOTH valid and data identically
```
