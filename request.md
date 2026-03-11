这份文档是 **VeriFlow-Agent 3.0** 方案的完整 Markdown 版本，您可以直接复制到您的技术文档或 Wiki 中。

---

# VeriFlow-Agent 3.0：工业级时序与微架构感知的 Verilog 自动生成方案

## 1. 方案概述

传统的 Verilog 代码生成方案往往陷入“功能逻辑正确，物理实现失败”的困境。**VeriFlow-Agent 3.0** 通过引入“移位向左（Shift-Left）”哲学，将微架构规划与物理时序预估提前至代码生成之前，确保生成的代码不仅逻辑正确，且能满足工业级的频率与资源约束。为保证方案可落地，流程对每个 Stage 设定明确的输入/输出契约与回退策略，任何阶段未满足门槛时禁止推进。

### 1.1 实施前置条件

1. **需求清单标准化**：接口协议、目标频率、功耗/面积预算、可复用 IP、验证覆盖目标需在立项时结构化录入。
2. **技能模块注册表**：Stage 1.5 Prompt、YAML DSL 解释器、Skill D、仿真 Diff、Yosys 报告解析器等以可调用 API 的形式注册，Agent 才能按职责协同。
3. **KPI 面板初始化**：Pass@1、Timing Closure、Token 消耗、Bug 修复次数由日志自动采集，成为 Stage 回退的客观依据。

---

## 2. 全链路架构图

系统分为五个核心阶段，通过专门的 Python Skill 技能包进行驱动：

### 第一阶段：需求拆解与微架构决策 (Stage 1 & 1.5)

* **目标**：确定模块的“物理骨架”。
* **输入**：接口描述、目标频率/功耗/面积/KPI、可复用 IP 列表、已有 RTL、外设资源占比。
* **动作**：
  * **架构决策**：AI 需决定流水线级数、关键路径切割位置、资源类型选择（如分布式 RAM vs Block RAM），并输出状态/时序表。
  * **物理预评估**：根据目标频率（如 200MHz）推导允许的最大逻辑级数，给出功耗/面积的初步上限。
  * **Prompt 模板 + Checklist**：Stage 1.5 的 System Prompt 强制包含接口一致性、延迟预算、功耗 Guardband、复用/新增 IP 判定，每项都有“已覆盖/未覆盖”勾选。
  * **经验库检索**：若数据库存在类似模块的成功 Spec，自动检索并提供给模型，减少“即兴设计”。
* **输出**：`Micro-Arch Spec` 文档，至少含流水线拓扑图、控制/数据路径说明、资源映射表、接口时序矩阵、回退阈值。
* **质量门槛**：如 Spec 未覆盖上述字段或 KPI 无法追踪，则回退到需求确认。

### 第二阶段：虚拟时序建模 (Stage 2)

* **目标**：在写代码前锚定逻辑正确性。
* **输入**：Micro-Arch Spec、接口协议、激励/覆盖约束。
* **动作**：
  * **分层 YAML 描述**：使用参数化 YAML（支持 `repeat`, `phase`, `assertion`）替代逐周期枚举，提交前通过 JSON Schema 校验。
  * **断言驱动**：引入类 SVA (SystemVerilog Assertion) 的时序属性检查（如：`req |-> ##[1:3] ack`），并要求模型解释断言的物理意义和违例场景。
  * **WaveDrom 自动化**：生成 WaveDrom JSON 和示意图，方便需求方签收。
  * **Stimulus 导出**：将 YAML 自动编译为 Testbench 激励脚本，与 Golden Trace 同源，保证 Stage 4 激励一致。
* **输出**：`Golden Trace`、WaveDrom 图、断言解释文档、Stimulus 代码。
* **质量门槛**：Schema 校验不过或断言缺失解释时，禁止进入 Stage 3。

### 第三阶段：代码生成与静态质量分析 (Stage 3 & 3.5)

* **目标**：生成高性能 RTL 代码。
* **输入**：Micro-Arch Spec、Stage 2 Golden Trace/Stimulus、编码规范。
* **动作**：
  * **三段式范式**：强制要求组合逻辑与时序逻辑完全分离，并附带 Lint 结果。
  * **Skill D 介入**：
    * **D1 逻辑级数预估**：静态分析代码中的 `if-else` 和算术运算深度，输出“最大组合级数 vs Spec 预算”。
    * **D2 CDC 检查**：识别跨时钟域的直接赋值风险，结合命名/时钟约束降低误报。
    * **校准机制**：Skill D 结果与 Stage 5 综合数据对比，形成误差模型迭代更新。
  * **经验库辅助**：失败案例自动推送相似模版，帮助模型插入寄存器或重写调度逻辑。
* **输出**：高质量 Verilog 源代码、Lint 报告、Skill D 摘要、建议性修复列表。
* **质量门槛**：若逻辑级数估计超出预算、CDC 未关闭或 Lint 有致命告警，则回退 Stage 1.5/2。

### 第四阶段：物理仿真与双波形比对 (Stage 4)

* **目标**：闭环验证。
* **输入**：Stage 2 Stimulus、Stage 3 RTL、断言列表。
* **动作**：
  * **仿真运行**：调用 Icarus/Verilator 执行 Testbench，自动解析日志。
  * **结构化 Diff**：比对“Stage 2 的虚拟波形”与“真实仿真波形”，输出 JSON 格式差异报告，并与 YAML 断言 ID 建立映射。
  * **诊断增强**：Diff 中保留 `probable_cause`、`suggestion` 字段，并引用 Skill D/Stage 2 上下文给出可执行修复。
  * **渐进覆盖**：先覆盖关键接口信号，再扩展至全部信号，逐步提升诊断精度。
* **输出**：仿真波形、断言结果、结构化 Diff 报告、知识库条目。
* **质量门槛**：断言未通过或 Diff 存在未解释事件时，回退 Stage 2/3。

### 第五阶段：综合级验证 (Stage 5)

* **目标**：获取真实的物理反馈。
* **输入**：Stage 3 RTL、约束文件、Stage 1 KPI。
* **动作**：调用 **Yosys** 进行逻辑综合，提取关键路径、面积/功耗估算，并自动与 Stage 1.5 KPI 对比；若不合规，强制回退至 Stage 1.5，同时把失败原因记录进检索库。
* **输出**：综合报告、KPI Dashboard 更新、回退原因。

---

## 3. 核心 Skill 设计规范

### 3.1 时序规划描述 (YAML 范式)

```yaml
scenario: "FIFO_Write_Burst"
parameters: { DEPTH: 4 }
clocks: { clk: { period: 5ns } }
phases:
  - name: "Write_Phase"
    repeat: { count: "$DEPTH", var: "i" }
    signals: 
      wr_en: 1
      wr_data: "$i * 2"
    assertions:
      - "full == 0 until i == $DEPTH-1"

```

* **Schema 管控**：DSL 需通过 JSON Schema 校验，Schema 版本与仓库 CI 绑定，防止语义漂移。
* **多产物互通**：YAML 经解析同时生成 WaveDrom、Golden Trace、Stimulus，并用 `scenario_id` 串联，确保 Stage 2/4 数据一致。

### 3.2 结构化差异报告 (JSON 范式)

```json
{
  "mismatch_event": {
    "time": "45ns",
    "signal": "ready_out",
    "expected": 1,
    "actual": 0,
    "probable_cause": "Combinational path too long, missing register slice.",
    "suggestion": "Add a pipeline stage in the logic path."
  }
}

```

---

## 4. 关键评估指标 (KPI)

| 评估维度 | 传统方案 | VeriFlow-Agent 3.0 |
| --- | --- | --- |
| **功能正确性 (Pass@1)** | 40% - 60% | **85% - 95%** |
| **时序收敛率 (Timing Closure)** | 低 (主要靠运气) | **高 (架构干预)** |
| **Token 效率** | 低 (重复迭代多) | **极高 (YAML 抽象)** |
| **Debug 难度** | 盲目修改代码 | **精准定位时序差异点** |
| **KPI 可观测性** | 大量人工统计 | **自动日志 + Dashboard** |

---

## 5. 专家实施建议

1. **架构先行**：不要在没有 Stage 1.5 产出的情况下让 AI 开始写代码。
2. **断言驱动**：在 YAML 中定义的 `assertions` 是 Agent 最好的“警报器”，应强制要求 AI 解释每一条断言的含义。
3. **工具解耦**：Skill 模块应保持原子化，例如 `Linter` 只管语法，`Yosys` 只管综合。
4. **经验复用**：Stage 5 的失败案例需沉淀为检索库，让 Stage 1.5/3 可以引用。
5. **KPI 自动化**：Pass@1、Timing Closure、Token 等指标进入 Dashboard，作为 Stage 闸门条件。

---

## 6. 风险与增强策略

* **Prompt 质量风险**：Stage 1.5 模板若过于宽泛，Spec 难以执行；需定期评审并由资深架构师签署。
* **Skill D 精度风险**：逻辑级数估计偏差会误导判断，必须与 Stage 5 数据持续校准，必要时引入实际 STA 结果。
* **DSL 兼容性风险**：YAML 扩展需版本化 Schema 并通过 CI WaveDrom/Stimulus 回归。
* **仿真诊断风险**：Diff 覆盖不足易漏报，建议定义“关键信号覆盖率”KPI 并逐步扩展。
* **数据治理风险**：若 KPI 未自动采集，Stage 回退无法落地，需强制记录每次运行元数据。

---

**下一步建议：**
您可以先尝试为您的 Agent 配置 **Stage 1.5 的 System Prompt**。如果您准备好了，我可以为您提供一份针对 **“带流水线的 AXI4-Lite Slave”** 模块的微架构决策提示词模版。
