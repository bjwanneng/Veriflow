## 1. 命名约定 (Naming Conventions)

*   **必须 (MUST)** 使用全小写字母和下划线 (`_`) 命名模块名 (Module)、端口名 (Port)、内部线网 (`wire`) 和逻辑变量 (`reg`/`logic`)。
*   **必须 (MUST)** 使用全大写字母和下划线 (`_`) 命名参数 (`parameter` / `localparam`)。
*   **必须 (MUST)** 为跨时钟域、打拍延迟或特定功能的寄存器添加标准后缀：
    *   寄存器输出信号使用 `_reg` 后缀。
    *   打拍延迟信号使用 `_dly`，如 `_dly1`, `_dly2`。
    *   次态信号 (Next state) 使用 `_nxt` 后缀。

**代码示例**：
```verilog
❌ 错误示例：
parameter max_width = 32;
wire DataIn;
reg outReg;

✅ 正确示例：
parameter MAX_WIDTH = 32;
wire data_in;
reg out_reg;
```

## 2. 端口与参数声明 (Ports & Parameters)

*   **必须 (MUST)** 强制使用 Verilog-2001 (ANSI C 风格) 在模块头部统一声明端口方向和类型。
*   **严禁 (MUST NOT)** 在模块头部仅声明端口名称，而在模块体内部再次声明方向和类型。

**代码示例**：
```verilog
❌ 错误示例：
module my_logic (clk, din, dout);
  input clk;
  input [7:0] din;
  output reg [7:0] dout;

✅ 正确示例：
module my_logic (
  input  wire       clk,
  input  wire [7:0] din,
  output reg  [7:0] dout
);
```

## 3. 排版与对齐 (Formatting & Alignment)

*   **必须 (MUST)** 使用空格 (Space) 进行缩进，严禁使用 Tab。标准缩进为 2 或 4 个空格。
*   **必须 (MUST)** 在端口声明、参数声明、位宽声明以及赋值语句中的等号 (`=`, `<=`) 处保持垂直对齐，以最大化机器和人类的可读性。

**代码示例**：
```verilog
❌ 错误示例：
assign a = b & c;
assign out_data = in_data;

✅ 正确示例：
assign a        = b & c;
assign out_data = in_data;
```

## 4. 时序与组合逻辑分离 (Sequential vs Combinational)

*   **严禁 (MUST NOT)** 在同一个信号的赋值中混合使用阻塞赋值 (`=`) 和非阻塞赋值 (`<=`)。时序逻辑必须使用 `<= `，组合逻辑必须使用 `=`。
*   **必须 (MUST)** 使用隐式敏感列表 `always @(*)` 或 SystemVerilog 的 `always_comb` 来描述组合逻辑，严禁显式列出所有敏感信号。
*   **必须 (MUST)** 在组合逻辑的 `if-else` 或 `case` 语句的所有分支中对变量进行明确赋值，或在 `always` 块起始处赋予默认初值，以彻底避免产生意外的 Latch (锁存器)。

**代码示例**：
```verilog
❌ 错误示例 (产生 Latch / 敏感列表不全 / 混用赋值)：
always @(en) begin
  if (en) 
    dout <= din; // 混用 <= 且缺少 else
end

✅ 正确示例 (严格避免 Latch 的组合逻辑)：
always @(*) begin
  dout_nxt = dout; // 赋初值
  if (en) begin
    dout_nxt = din_reg;
  end
end
```

## 5. 复位策略与时钟 (Reset & Clocking)

*   **必须 (MUST)** 优先使用**同步复位 (Synchronous Reset)**，严禁滥用异步复位 (除非架构强制要求)。同步复位能更高效地映射到 DSP、BRAM 等专用底层资源。
*   **必须 (MUST)** 将时钟使能 (`ce`)、置位 (`set`) 和复位 (`reset`) 等控制信号设计为**高电平有效 (Active-High)**，严禁使用低电平有效信号，以避免引入额外的反相器逻辑。
*   **必须 (MUST)** 在包含使能和复位的时序块中，将复位逻辑的优先级置于最高（即复位判断必须写在使能判断之前）。

**代码示例**：
```verilog
❌ 错误示例 (异步、低电平有效、优先级错误)：
always @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    dout <= 0;
  end else if (en) begin
    dout <= din;
  end
end

✅ 正确示例 (同步、高电平有效、复位优先级最高)：
always @(posedge clk) begin
  if (rst) begin
    dout <= 16'h0000;
  end else if (en) begin
    dout <= din;
  end
end
```

## 6. 状态机范式 (FSM Guidelines)

*   **必须 (MUST)** 使用 `parameter` 或 `localparam` 明确定义所有状态编码。
*   **必须 (MUST)** 在描述状态机时，包含完整的 `case` 语句。
*   **必须 (MUST)** 在 `case` 语句的末尾包含 `default` 分支，或者使用安全的属性约束，确保状态机处于非法状态时能安全恢复。

**代码示例**：
```verilog
❌ 错误示例 (硬编码状态、无 default 保护)：
always @(posedge clk) begin
  case (state)
    2'b00: state <= 2'b01;
    2'b01: state <= 2'b10;
  endcase
end

✅ 正确示例 (参数化状态、完整 default 保护)：
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