# base_style.md — 可综合 Verilog-2001 编码规范

---

## 1. 文件结构 (File Structure)

**MUST** 每个 `.v` 文件严格按照以下顺序组织：

```
`resetall
`timescale 1ns / 1ps
`default_nettype none

module xxx #( ... )( ... );
// ... 模块体 ...
endmodule

`resetall
```

- **MUST** 文件开头依次放置 `` `resetall ``、`` `timescale 1ns / 1ps ``、`` `default_nettype none ``。
- **MUST** 文件末尾（`endmodule` 之后）放置 `` `resetall ``，清除所有编译器指令状态。
- **MUST NOT** 在模块体内部使用任何 `` `define `` 宏。

---

## 2. 命名约定 (Naming Conventions)

### 2.1 模块名

**MUST** 使用全小写 + 下划线 (snake_case)。

```verilog
// ✅
module priority_encoder #( ... )( ... );
module axi_fifo_rd #( ... )( ... );

// ❌
module PriorityEncoder #( ... )( ... );
module AXI_FIFO_RD #( ... )( ... );
```

### 2.2 端口名与内部信号名

**MUST** 使用全小写 + 下划线 (snake_case)。

```verilog
// ✅
input  wire [7:0] s_axi_awlen,
output wire        grant_valid,
reg [7:0] read_count_reg;

// ❌
input  wire [7:0] S_AXI_AWLEN,
output wire        grantValid,
```

### 2.3 寄存器与次态后缀

**MUST** 寄存器输出使用 `_reg` 后缀，其对应的组合逻辑次态信号使用 `_next` 后缀。

```verilog
// ✅
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;

// ❌
reg [1:0] write_state;
reg [1:0] write_state_d;
reg       s_axi_awready_ff;
```

### 2.4 临时/缓冲寄存器前缀

**MUST** 用于 skid buffer 等临时存储的寄存器使用 `temp_` 前缀，并保留 `_reg` 后缀。

```verilog
// ✅
reg [7:0] temp_m_axi_arlen_reg = 8'd0;

// ❌
reg [7:0] m_axi_arlen_buf = 8'd0;
```

### 2.5 流水线寄存器后缀

**MUST** 流水线附加级寄存器使用 `_pipe_reg` 后缀。

```verilog
// ✅
reg [DATA_WIDTH-1:0] s_axi_rdata_pipe_reg = {DATA_WIDTH{1'b0}};

// ❌
reg [DATA_WIDTH-1:0] s_axi_rdata_p1 = {DATA_WIDTH{1'b0}};
```

### 2.6 Parameter / Localparam

**MUST** 使用全大写 + 下划线 (UPPER_SNAKE_CASE)。

```verilog
// ✅
parameter DATA_WIDTH = 32,
parameter ADDR_WIDTH = 16,
localparam VALID_ADDR_WIDTH = ADDR_WIDTH - $clog2(STRB_WIDTH);

// ❌
parameter dataWidth = 32;
localparam valid_addr_width = 10;
```

### 2.7 状态机状态名

**MUST** 状态名使用全大写，并带有描述性前缀（与状态寄存器名对应）。

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

## 3. 端口与参数声明 (Ports & Parameters)

### 3.1 ANSI 风格声明

**MUST** 强制使用 Verilog-2001 ANSI 风格，在模块头部统一声明端口方向、类型和位宽。**MUST NOT** 使用 Verilog-1995 风格的端口列表 + 模块体内声明。

```verilog
// ✅ Verilog-2001 ANSI 风格
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

// ❌ Verilog-1995 风格
module axi_ram(clk, rst, s_axi_wdata, s_axi_wready);
    input clk;
    input rst;
    input [31:0] s_axi_wdata;
    output s_axi_wready;
```

### 3.2 端口类型显式声明

**MUST** 所有端口显式声明 `wire` 类型关键字。

```verilog
// ✅
input  wire [7:0] s_axi_awlen,
output wire        s_axi_awready,

// ❌
input  [7:0] s_axi_awlen,
output       s_axi_awready,
```

### 3.3 参数注释

**MUST** 每个 `parameter` 上方或行内附带简短注释说明其含义。

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

### 3.4 参数块与端口块分离

**MUST** 参数列表使用 `#( ... )` 独立括号块，端口列表使用 `( ... )` 独立括号块，两者分开书写。左括号 `(` 独占一行。

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

## 4. 排版与对齐 (Formatting & Alignment)

### 4.1 缩进

**MUST** 使用 4 个空格缩进。**MUST NOT** 使用 Tab。

### 4.2 端口声明对齐

**MUST** 端口声明中的方向关键字 (`input`/`output`)、类型 (`wire`)、位宽和信号名进行垂直列对齐。

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

### 4.3 寄存器声明对齐

**SHOULD** 同一组寄存器声明中，位宽和信号名进行垂直对齐。

```verilog
// ✅
reg [ID_WIDTH-1:0]   read_id_reg    = {ID_WIDTH{1'b0}}, read_id_next;
reg [ADDR_WIDTH-1:0] read_addr_reg  = {ADDR_WIDTH{1'b0}}, read_addr_next;
reg [7:0]            read_count_reg = 8'd0, read_count_next;
reg [2:0]            read_size_reg  = 3'd0, read_size_next;
```

### 4.4 assign 语句对齐

**SHOULD** 连续的 `assign` 语句中，等号 `=` 进行垂直对齐。

```verilog
// ✅
assign s_axi_awready = s_axi_awready_reg;
assign s_axi_wready  = s_axi_wready_reg;
assign s_axi_bid     = s_axi_bid_reg;
assign s_axi_bresp   = 2'b00;
assign s_axi_bvalid  = s_axi_bvalid_reg;
```

---

## 5. 时序与组合逻辑分离 (Sequential vs Combinational)

### 5.1 两段式分离

**MUST** 将组合逻辑（次态计算）和时序逻辑（寄存器更新）分别放在独立的 `always` 块中。

```verilog
// ✅ 组合逻辑块：计算所有 _next 信号
always @* begin
    state_next = state_reg;
    data_next  = data_reg;
    // ... 条件逻辑 ...
end

// ✅ 时序逻辑块：寄存器采样
always @(posedge clk) begin
    state_reg <= state_next;
    data_reg  <= data_next;
    if (rst) begin
        state_reg <= STATE_IDLE;
    end
end

// ❌ 混合在一个 always 块中
always @(posedge clk) begin
    if (condition)
        state_reg <= STATE_NEXT;  // 次态逻辑和寄存器更新混合
end
```

### 5.2 阻塞赋值与非阻塞赋值

**MUST** 组合逻辑块 (`always @*`) 中只使用阻塞赋值 (`=`)。
**MUST** 时序逻辑块 (`always @(posedge clk)`) 中只使用非阻塞赋值 (`<=`)。
**MUST NOT** 在同一个 `always` 块中混用 `=` 和 `<=`。

```verilog
// ✅
always @* begin
    data_next = data_reg;       // 阻塞赋值
end

always @(posedge clk) begin
    data_reg <= data_next;      // 非阻塞赋值
end

// ❌
always @(posedge clk) begin
    temp = a + b;               // 阻塞赋值出现在时序块中
    data_reg <= temp;
end
```

### 5.3 组合逻辑敏感列表

**MUST** 组合逻辑块使用 `always @*`（隐式完整敏感列表）。**MUST NOT** 使用显式敏感列表或 `always @(*)`。

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

### 5.4 Latch 消除 — 默认赋初值

**MUST** 在 `always @*` 块的最顶部，对所有输出信号赋予默认值（通常赋为对应 `_reg` 的当前值），然后再进入条件分支。这是消除 Latch 的核心手法。

```verilog
// ✅ 顶部赋默认值，消除 Latch
always @* begin
    write_state_next    = WRITE_STATE_IDLE;   // 默认值
    mem_wr_en           = 1'b0;               // 默认值
    write_id_next       = write_id_reg;       // 保持当前值
    write_addr_next     = write_addr_reg;     // 保持当前值
    s_axi_awready_next  = 1'b0;              // 默认值
    s_axi_bvalid_next   = s_axi_bvalid_reg && !s_axi_bready;

    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            // ... 仅覆盖需要改变的信号 ...
        end
        // ...
    endcase
end

// ❌ 没有默认值，某些分支遗漏赋值 → 产生 Latch
always @* begin
    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            write_state_next = WRITE_STATE_BURST;
            mem_wr_en = 1'b0;
        end
        WRITE_STATE_BURST: begin
            write_state_next = WRITE_STATE_IDLE;
            // mem_wr_en 未赋值 → Latch!
        end
    endcase
end
```

### 5.5 case 语句完整覆盖

**MUST** `case` 语句中每个分支都必须对 `state_next` 进行显式赋值（即使赋值为当前状态本身），或依赖顶部默认值覆盖。

```verilog
// ✅ 每个分支都显式赋值 state_next
case (read_state_reg)
    READ_STATE_IDLE: begin
        if (condition) begin
            read_state_next = READ_STATE_BURST;
        end else begin
            read_state_next = READ_STATE_IDLE;  // 显式保持
        end
    end
    READ_STATE_BURST: begin
        if (done) begin
            read_state_next = READ_STATE_IDLE;
        end else begin
            read_state_next = READ_STATE_BURST; // 显式保持
        end
    end
endcase
```

### 5.6 单一驱动原则 (Single Driver Rule)

**MUST** 任何一个 `_next` 信号只能在一个单一的 `always @*` 块中被赋值。
**MUST** 任何一个 `_reg` 信号只能在一个单一的 `always @(posedge clk)` 块中被赋值。
**MUST NOT** 在多个 `always` 块中对同一个变量进行驱动，综合工具会报 Multiple Drivers 错误。

```verilog
// ✅ 每个信号只有唯一的驱动源
always @* begin
    data_a_next = data_a_reg;
    // ... 仅在此块中驱动 data_a_next ...
end

always @* begin
    data_b_next = data_b_reg;
    // ... 仅在此块中驱动 data_b_next ...
end

// ❌ 同一个信号在两个 always 块中被驱动
always @* begin
    if (sel) data_next = a;
end

always @* begin
    if (!sel) data_next = b;  // Multiple Drivers!
end
```

---

## 6. 复位策略与时钟 (Reset & Clocking)

### 6.1 同步复位

**MUST** 使用同步复位。复位逻辑写在 `always @(posedge clk)` 块内部的 `if (rst)` 条件中。

```verilog
// ✅ 同步复位
always @(posedge clk) begin
    state_reg <= state_next;
    data_reg  <= data_next;

    if (rst) begin
        state_reg <= STATE_IDLE;
        valid_reg <= 1'b0;
    end
end

// ❌ 异步复位
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state_reg <= STATE_IDLE;
    end else begin
        state_reg <= state_next;
    end
end
```

### 6.2 复位信号极性

**MUST** 复位信号为高电平有效，命名为 `rst`。**MUST NOT** 使用低电平有效的 `rst_n`。

```verilog
// ✅
input wire rst,

if (rst) begin
    // 复位逻辑
end

// ❌
input wire rst_n,

if (!rst_n) begin
    // 复位逻辑
end
```

### 6.3 复位块位置

**MUST** 复位 `if (rst)` 块放在 `always @(posedge clk)` 块的末尾（在所有正常逻辑之后），利用后赋值覆盖的特性实现复位优先。

```verilog
// ✅ 复位块在末尾
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

// ❌ 复位块在开头（if-else 结构）
always @(posedge clk) begin
    if (rst) begin
        write_state_reg <= WRITE_STATE_IDLE;
    end else begin
        write_state_reg <= write_state_next;
    end
end
```

### 6.4 选择性复位

**SHOULD** 优先仅对控制路径信号（状态寄存器、valid、ready、握手信号）进行复位。纯粹的数据路径（如 payload data、addr）可以不复位，以减少复位扇出。**但如果无法确定某个寄存器属于控制路径还是数据路径，安全起见请对其进行复位。**

```verilog
// ✅ 仅复位控制信号（推荐）
if (rst) begin
    read_state_reg      <= READ_STATE_IDLE;
    s_axi_arready_reg   <= 1'b0;
    s_axi_rvalid_reg    <= 1'b0;
    // read_id_reg, read_addr_reg 等纯数据信号可不复位
end

// ✅ 不确定时全部复位（安全保守做法，也可接受）
if (rst) begin
    read_state_reg    <= READ_STATE_IDLE;
    s_axi_arready_reg <= 1'b0;
    s_axi_rvalid_reg  <= 1'b0;
    some_flag_reg     <= 1'b0;     // 内部 flag，不确定归属，复位更安全
end
```

---

## 7. 寄存器声明与初始化 (Register Declaration & Initialization)

### 7.1 声明时初始化

**MUST** 所有 `reg` 在声明时赋初始值。

```verilog
// ✅
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;
reg [7:0] read_count_reg = 8'd0, read_count_next;

// ❌
reg [1:0] write_state_reg;
reg       s_axi_awready_reg;
```

### 7.2 _reg 与 _next 同行声明

**SHOULD** 将 `_reg` 和对应的 `_next` 信号在同一行声明，用逗号分隔。

```verilog
// ✅
reg [0:0] read_state_reg = READ_STATE_IDLE, read_state_next;

// 可接受但非首选
reg [0:0] read_state_reg = READ_STATE_IDLE;
reg [0:0] read_state_next;
```

### 7.3 参数化位宽初始化

**MUST** 使用复制运算符 `{N{1'bx}}` 对参数化位宽的寄存器进行初始化，而非硬编码 `0`。

```verilog
// ✅
reg [ID_WIDTH-1:0] read_id_reg = {ID_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] s_axi_rdata_reg = {DATA_WIDTH{1'b0}};

// ❌
reg [ID_WIDTH-1:0] read_id_reg = 0;
```

### 7.4 存储器数组 (Memory Arrays) 声明

**MUST** 二维存储器数组的声明格式为 `reg [DATA_WIDTH-1:0] mem_name[(2**ADDR_WIDTH)-1:0];`。
**MUST NOT** 对存储器数组进行声明时初始化（如 `= '{default: '0}`）或在同步复位块中全局清零。存储器初始化应通过 `initial` 块中的循环赋值或 `$readmemh`/`$readmemb` 完成。
**SHOULD** 在存储器声明上方使用综合属性指定推断类型。

```verilog
// ✅
(* ramstyle = "no_rw_check" *)
reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0];

// ✅ 使用 initial 块初始化
initial begin
    for (i = 0; i < 2**ADDR_WIDTH; i = i + 1) begin
        mem[i] = 0;
    end
end

// ✅ 使用 $readmemh 初始化
initial begin
    $readmemh("init_data.hex", mem);
end

// ❌ 在 always @(posedge clk) 的 rst 块中清零存储器
if (rst) begin
    for (i = 0; i < DEPTH; i = i + 1)
        mem[i] <= 0;  // 不可综合或极度浪费资源
end
```

---

## 8. 状态机范式 (FSM Guidelines)

### 8.1 两段式状态机

**MUST** 使用两段式状态机：
- 第一段：`always @*` 组合逻辑块，计算 `state_next` 及所有 `_next` 信号。
- 第二段：`always @(posedge clk)` 时序逻辑块，将 `_next` 采样到 `_reg`。

### 8.2 状态编码

**MUST** 使用 `localparam` 定义状态编码，显式指定位宽和值。

```verilog
// ✅
localparam [1:0]
    WRITE_STATE_IDLE  = 2'd0,
    WRITE_STATE_BURST = 2'd1,
    WRITE_STATE_RESP  = 2'd2;

reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;

// ❌ 使用 parameter 而非 localparam
parameter IDLE = 0, BURST = 1;

// ❌ 未指定位宽
localparam IDLE = 0;
```

### 8.3 状态寄存器位宽

**MUST** 状态寄存器的位宽与 `localparam` 声明的位宽一致。

```verilog
// ✅
localparam [0:0]
    READ_STATE_IDLE  = 1'd0,
    READ_STATE_BURST = 1'd1;

reg [0:0] read_state_reg = READ_STATE_IDLE, read_state_next;

// ❌ 位宽不匹配
localparam [1:0] READ_STATE_IDLE = 2'd0;
reg [0:0] read_state_reg;
```

---

## 9. 模块例化 (Module Instantiation)

### 9.1 命名端口连接

**MUST** 使用命名端口连接 (`.port(signal)`)，每个连接独占一行。**MUST NOT** 使用位置端口连接。

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

// ❌ 位置连接
priority_encoder #(PORTS, ARB_LSB_HIGH_PRIORITY)
priority_encoder_inst (request, request_valid, request_index, request_mask);
```

### 9.2 实例命名

**SHOULD** 实例名使用 `_inst` 后缀或描述性后缀。

```verilog
// ✅
priority_encoder_inst
priority_encoder_masked

// ❌
u0
pe1
```

---

## 10. Generate 块 (Generate Blocks)

### 10.1 genvar 声明位置

**MUST** `genvar` 在 `generate` 块内部声明。

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

### 10.2 generate for 标签

**MUST** 所有 `generate for` 循环的 `begin` 块必须带有命名标签。

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

## 11. 输出端口驱动 (Output Port Driving)

**MUST** 所有 `output wire` 端口通过 `assign` 语句从内部 `_reg` 信号驱动。**MUST NOT** 将 `output reg` 直接在 `always` 块中赋值。

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

## 12. 参数验证 (Parameter Validation)

**SHOULD** 使用 `initial begin` 块对关键参数进行断言检查，使用 `$error` 和 `$finish`。

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

## 13. 算术与逻辑运算 (Arithmetic & Logic)

### 13.1 位宽匹配与显式扩展

**MUST** 在进行加法、减法或比较时，赋值目标的位宽必须能容纳运算结果。如果存在进位或位宽不匹配，必须进行显式的位拼接或截断。**MUST NOT** 依赖 Verilog 的隐式位宽扩展规则。

```verilog
// ✅ 显式拼接，处理进位
wire [8:0] sum_full = a[7:0] + b[7:0];
wire [7:0] sum      = sum_full[7:0];
wire       carry    = sum_full[8];

// ✅ 使用位拼接捕获进位
assign {carry_out, sum[7:0]} = a[7:0] + b[7:0];

// ❌ 进位被隐式截断，无任何警告
wire [7:0] sum = a[7:0] + b[7:0] + carry_in;
```

### 13.2 常量位宽显式标注

**MUST** 在赋值和比较中使用带位宽的常量。**MUST NOT** 使用裸整数常量（除了 `0` 和 `1` 用于固定位宽的简单场景）。

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

### 13.3 位选与部分选择

**SHOULD** 优先使用 `+:` / `-:` 运算符进行可变偏移的部分位选择，而非手动计算索引范围。

```verilog
// ✅ 使用 +: 运算符
mem[addr][WORD_SIZE*i +: WORD_SIZE] <= wdata[WORD_SIZE*i +: WORD_SIZE];

// ❌ 手动计算范围（容易出错）
mem[addr][WORD_SIZE*i + WORD_SIZE - 1 : WORD_SIZE*i] <= wdata[WORD_SIZE*i + WORD_SIZE - 1 : WORD_SIZE*i];
```
