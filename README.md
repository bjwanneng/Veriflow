# VeriFlow 8.3.2

工业级 Verilog RTL 设计流水线 —— 控制权反转架构 (Control Flow Inversion)

## 核心架构

VeriFlow 采用**控制权反转**架构：Python 是唯一的主控状态机，Claude LLM 作为无状态 Worker 节点被 Python 按需调用，EDA 工具（iverilog、Yosys）由 Python 直接驱动。

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Python Controller (veriflow_ctl.py)                │
│                      Master State Machine                            │
│                                                                      │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐       │
│  │ S1   │  │ S1.5 │  │ S2   │  │ S3   │  │ S3.5 │  │ S4   │  ...  │
│  │Arch  │  │Micro │  │Timing│  │Coder │  │SkillD│  │ Sim  │       │
│  │(REPL)│  │Arch  │  │Model │  │(RTL) │  │(静态)│  │ Loop │       │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘       │
│                                                                      │
│           ↕ Stage 失败时调用                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Supervisor (prompts/supervisor.md)               │   │
│  │   分析失败原因 → 输出路由决策 JSON → 决定 retry / escalate      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
               ↕ Lint / Simulation
    ┌────────────────────────────┐
    │   EDA Tools                │
    │   iverilog + vvp / Yosys   │
    └────────────────────────────┘
```

### Supervisor 机制

每当某个 Stage 返回失败，Python 不直接 abort，而是调用 **Supervisor**：

1. Python 将失败上下文（失败 stage、错误摘要、spec 摘要、历史失败案例）注入 `prompts/supervisor.md`
2. Supervisor LLM 分析根因，输出严格 JSON 路由决策：

```json
{
  "action": "retry_stage",
  "target_stage": 3,
  "modules": ["uart_rx"],
  "hint": "Replace always @* array read with wire continuous assign",
  "root_cause": "Combinational loop due to array read in always @* block",
  "severity": "high"
}
```

3. Python 按决策路由：

| `action` | 行为 |
|----------|------|
| `retry_stage` | 跳回指定 stage 重试，携带 hint |
| `escalate_stage` | 跳回更早 stage 重新生成 |
| `continue` | 忽略失败，继续下一 stage |
| `abort` | 终止流水线 |

- 每个 stage 最多触发 **3 次** Supervisor 重试，超限自动 abort
- Supervisor 的 hint 写入 `.veriflow/supervisor_hint.md`，由 Stage 3 和 Stage 4 Debugger 读取注入
- **全局模式扫描**（v8.3.2 新增）：修复 RTL 代码模式时，Supervisor 必须扫描 `workspace/rtl/` 下所有文件的同类问题并全部修复

---

## 执行模式与阶段流程

### 模式对应阶段

| 模式 | 阶段序列 | 适用场景 |
|------|---------|---------|
| **Quick** | 1 → 1.5 → 3 → 3.5 | 快速语法验证，无仿真，分钟级出结果 |
| **Standard** | 1 → 1.5 → 2 → 3 → 3.5 → 4 → 5 | 完整功能验证 + 综合（推荐） |
| **Enterprise** | 1 → 1.5 → 2 → 3 → 3.5 → 4 → 5 | 同 Standard，保留未来扩展 |

> 内部整数编码：`1.5 → 15`，`3.5 → 35`，`3.6 → 36`

### 各阶段说明

| 阶段 | 名称 | 模式 | 类型 | 输出 |
|------|------|------|------|------|
| **Stage 1** | Architect | 所有 | 交互式 REPL | `workspace/docs/spec.json` |
| **Stage 1.5** | Micro-Architecture | 所有 | 无头 LLM | `workspace/docs/micro_arch.md` |
| **Stage 2** | Timing Model | standard/enterprise | 无头 LLM | `workspace/docs/timing_model.yaml` + `workspace/tb/tb_*.v` |
| **Stage 3** | RTL Coder | 所有 | 并行无头 LLM | `workspace/rtl/*.v` |
| **Stage 3.5** | Skill D | 所有 | Lint 循环 + LLM | `workspace/docs/static_report.json` |
| **Stage 4** | Simulation Loop | standard/enterprise | iverilog + vvp + Debugger | 仿真通过 |
| **Stage 5** | Synthesis + KPI | standard/enterprise | Yosys | `workspace/docs/synth_report.json` |

#### Stage 1 — Architect（交互式 REPL）

- Python 将完整任务指令写入项目目录的 `CLAUDE.md`，Claude Code 启动时自动读取并开始执行
- Claude 通过多轮问答澄清需求，生成 `workspace/docs/spec.json`
- 完成后 Claude 调用 `validate --stage 1` → `complete --stage 1` 写入哨兵文件 `stage1.done`
- Python 轮询 `stage1.done`，验证 MD5 校验和后继续
- v8.3.2 新增：kickoff 自动注入 `project_config.json` 中的目标频率，并在 validate 时校验频率一致性

#### Stage 1.5 — Micro-Architecture

- 无头调用，读取 `spec.json`，生成 `workspace/docs/micro_arch.md`
- 为 Stage 3 RTL 生成提供模块级微架构指导

#### Stage 2 — Virtual Timing Model

- 读取 `spec.json`（内容直接注入 prompt，无需 Claude 自行读取文件）
- 生成行为断言 YAML（`timing_model.yaml`）和配套测试台（`tb_*.v`）
- 测试台必须：至少 3 个场景（reset + basic + edge case），每个场景均有 `fail_count` 断言
- 串行/波特率设计：必须按公式计算等待周期，禁止硬编码小常数

#### Stage 3 — RTL Coder

- 并行生成：Phase 1 并发生成所有非 top 模块（最多 4 个 worker），Phase 2 串行生成 top 模块
- 遵循 7 条强制 Verilog 规则（Verilog-2005，ANSI 端口，snake_case，完整实现无 placeholder）
- 可通过 `--modules uart_tx` 只重新生成指定模块
- 从 ExperienceDB 查询历史成功模式，注入为 `EXPERIENCE_HINT`

#### Stage 3.5 — Skill D（静态质量分析）

- Phase 1：iverilog lint 循环（最多 5 轮），失败时 Debugger 自动修复
- Phase 2：无头 LLM 分析，检测逻辑深度、CDC 风险、Latch 推断
- v8.3.2 新增：`analyzed_files` 必须列出所有已分析文件；FIFO/RAM cell 估算（depth×width cells）

#### Stage 4 — Simulation Loop

- iverilog 编译 + vvp 仿真，最多 5 轮自动修复
- **TB 防篡改保护**：Debugger 运行前后对 `workspace/tb/` 做 MD5 快照，自动还原被篡改的测试台
- 无测试台时返回 False，Supervisor 路由回 Stage 2 重新生成

#### Stage 5 — Yosys Synthesis

- Yosys 综合，解析 `stat -json` 输出，与 `spec.json::target_kpis` 比对
- KPI 缺口 >20% 时打印警告门控
- Yosys 未安装时优雅跳过

---

## 快速开始

### 前置条件

| 工具 | 用途 | 必需 |
|------|------|------|
| Python 3.8+ | 主控脚本 | 是 |
| Claude CLI（`claude` 命令） | LLM Worker | 是 |
| iverilog + vvp | Lint + 仿真 | 是（未安装自动 mock） |
| Yosys | 综合（Stage 5） | 否（未安装自动跳过） |

```bash
# 推荐：oss-cad-suite（含 iverilog + Yosys）
# 下载：https://github.com/YosysHQ/oss-cad-suite-build/releases
export PATH="/path/to/oss-cad-suite/bin:$PATH"

# 或单独安装 iverilog
# macOS: brew install icarus-verilog
# Ubuntu: apt-get install iverilog
```

### 启动方式

#### 方式 1 — GUI 启动（推荐）

**Windows（双击即可）：**
```
run_veriflow.bat
```
脚本内容：进入项目目录 → 启动 `run_veriflow.py` → 出错时暂停等待查看

**跨平台 Python 启动器：**
```bash
python run_veriflow.py
```
- 自动在 7860–7900 范围内寻找空闲端口
- 等待 Gradio 服务就绪后自动打开浏览器
- Ctrl+C 优雅退出

**macOS / Linux：**
```bash
chmod +x run_veriflow.sh
./run_veriflow.sh
```

**不自动打开浏览器：**
```bash
python veriflow_gui.py
```

#### 方式 2 — 命令行直接运行

```bash
# 标准模式（完整验证，推荐）
python veriflow_ctl.py run --mode standard -d ./my_project

# Quick 模式（仅 lint，无仿真，快速验证）
python veriflow_ctl.py run --mode quick -d ./my_project

# Enterprise 模式（含综合 + KPI 比对）
python veriflow_ctl.py run --mode enterprise -d ./my_project

# 断点续跑（跳过已完成的 stage）
python veriflow_ctl.py run --mode standard -d ./my_project --resume

# 带反馈修订
python veriflow_ctl.py run --mode standard -d ./my_project --feedback feedback.md

# 只重新生成某个模块
python veriflow_ctl.py run --mode standard -d ./my_project --stages 3 --modules uart_tx

# 验证阶段输出（由 Claude 在 REPL 中自调用）
python veriflow_ctl.py validate --stage 1 -d ./my_project

# 标记阶段完成（由 Claude 在 REPL 中自调用，需先通过 validate）
python veriflow_ctl.py complete --stage 1 -d ./my_project
```

### 第一个项目

```bash
# 1. 创建项目目录，写入需求文件
mkdir my_uart
cat > my_uart/requirement.md << 'EOF'
# UART 收发器

设计一个 UART 收发器：
- 波特率：115200（可配置）
- 数据位：8位，无校验，1停止位
- 接口：valid/ready 握手
- 目标频率：100 MHz
EOF

# 2. 用 GUI 启动（推荐）
python run_veriflow.py

# 或命令行运行
python veriflow_ctl.py run --mode standard -d ./my_uart
```

---

## GUI 说明

Gradio Web UI，访问地址默认为 `http://127.0.0.1:7860`（端口自动分配）。

### 页面结构

| 页面 | 功能 |
|------|------|
| Project Management | 创建项目、设置模式和目标频率、切换工作目录 |
| Design Requirements | 编辑 `requirement.md`，支持文本输入、文件上传、模板库 |
| Environment Config | 配置 iverilog/vvp/Yosys 路径，工具可用性检测 |
| Agent Config | Claude CLI 路径、Mock 模式开关、OpenAI 兼容端点配置 |
| Run Pipeline | Stage 状态指示器、逐 stage 运行按钮、实时彩色日志、Review Gate |
| Generated Files | RTL / Testbench / 文档文件预览 |

### Run Pipeline 页关键功能

- **Stage 状态指示器**：绿圈 = 已完成，灰圈 = 待运行，实时更新
- **逐 stage 按钮**：前级未完成时后级按钮不可点击；已完成的 stage 按钮变绿
- **Review Gate**：Stage 1 和 Stage 3 完成后自动暂停，展示 spec.json / RTL 供审查；点"拒绝"可填写反馈，重跑该 stage
- **日志过滤**：支持按级别过滤（info / warning / error / stage），深色终端风格彩色显示
- **配置持久化**：模式、已完成 stages、日志状态在重新打开项目时自动恢复

---

## 项目目录结构

```
my_project/
├── requirement.md              # 设计需求（用户输入）
├── .veriflow/
│   ├── project_config.json     # 项目配置（mode、target_frequency_mhz 等）
│   ├── pipeline_state.json     # 流水线状态（completed_stages、决策记录）
│   ├── pipeline_events.jsonl   # Stage 生命周期事件流（start/complete/fail）
│   ├── supervisor_hint.md      # Supervisor 路由 hint（Stage 失败时写入，下次 Stage 读取后删除）
│   ├── kpi.json                # KPI 指标（每次运行记录）
│   ├── experience_db/          # 历史成功模式 + 失败案例（ExperienceDB）
│   └── logs/
│       ├── stage1_YYYYMMDDHHMMSS.jsonl   # Stage 1 结构化日志
│       ├── stage3_YYYYMMDDHHMMSS.jsonl   # Stage 3 结构化日志
│       ├── linter_stage3.log             # Stage 3 validate lint 输出
│       ├── linter_stage35_iter1.log      # Stage 3.5 第 1 轮 lint 输出
│       ├── linter_stage4.log             # Stage 4 validate lint 输出
│       └── run_<ts>.log                  # 全量纯文本日志（最近 10 个，自动清理）
└── workspace/
    ├── docs/
    │   ├── spec.json               # 架构规格（Stage 1 输出）
    │   ├── micro_arch.md           # 微架构文档（Stage 1.5 输出）
    │   ├── timing_model.yaml       # 行为断言 + 激励序列（Stage 2 输出）
    │   ├── static_report.json      # 静态分析报告（Stage 3.5 输出）
    │   ├── synth_report.json       # 综合报告（Stage 5 输出）
    │   └── stage*.done             # 阶段完成哨兵文件（含 MD5 校验和）
    ├── rtl/
    │   └── *.v                     # RTL 源文件（Stage 3 输出）
    ├── tb/
    │   └── tb_*.v                  # 测试台（Stage 2 输出，防篡改保护）
    ├── sim/
    │   └── *                       # 仿真输出（VCD、日志）
    └── stages/
        └── <stage_name>/           # 每个 stage 的扁平归档（只保存新增/修改文件）
```

---

## 质量门控策略

VeriFlow 有两类门控机制，行为不同：

- **硬校验（validate）**：由 Claude 在 REPL 中自调用，输出 `VALIDATE: FAIL` 则 Claude 必须修正后重新 validate，Stage 不会完成
- **软门控（用户确认）**：流水线暂停，终端询问用户如何处置，选择 B/Q 则触发 Supervisor 重新路由

### Stage 1 — 架构规格硬校验

由 `validate --stage 1` 执行，**全部通过才能写哨兵文件**：

| 检查项 | 错误代码 | 说明 |
|--------|---------|------|
| `spec.json` 存在 | `MISSING` | 文件不存在则直接失败 |
| `modules` 数组非空 | `INVALID` | 必须定义至少一个模块 |
| 存在 `module_type: top` 的模块 | `INVALID` | 必须有顶层模块 |
| `target_kpis` 包含 `frequency_mhz`、`max_cells`、`power_mw` | `INVALID` | 三个 KPI 字段缺一不可 |
| `spec.json` 频率与 `project_config.json` 一致 | `FREQ_MISMATCH` | 防止目标频率前后矛盾 |
| JSON Schema 校验（需安装 `jsonschema`） | `SCHEMA` | 可选，未安装时静默跳过 |

输出格式：
```
VALIDATE: PASS          ← 全部通过，Claude 继续执行 complete
VALIDATE: FAIL
  ERROR: FREQ_MISMATCH: spec.json target_frequency_mhz=100 != project_config.json target_frequency_mhz=300
  ERROR: INVALID: target_kpis missing 'power_mw'
```

### Stage 2 — 时序模型硬校验

由 `validate --stage 2` 执行：

| 检查项 | 说明 |
|--------|------|
| `workspace/docs/timing_model.yaml` 存在 | 必须生成 |
| YAML 包含 `design` 和 `scenarios` 字段 | 结构完整性 |
| `workspace/tb/tb_*.v` 存在 | 至少一个测试台文件 |

此外 `stage2_timing_model()` 在 Claude 返回后**再次直接验证文件是否真实存在**，任一缺失即返回 False 交 Supervisor 路由。

### Stage 3.5 — Skill D 双阶段门控

**Phase 1 — Lint 循环（自动）：**
- 最多 5 轮 iverilog lint，每轮失败调用 Debugger 修复
- 第 N 轮 lint 输出写入 `linter_stage35_iterN.log`
- 5 轮后仍失败 → 返回 False 交 Supervisor

**Phase 2 — 静态分析门控（用户确认）：**
当 LLM 分析发现以下问题时，终端弹出交互提示：

| 触发条件 | 严重程度 |
|---------|---------|
| 逻辑深度 `max_levels > critical_path_budget` | 时序风险，可能无法满足目标频率 |
| CDC 风险等级为 `HIGH` | 跨时钟域亚稳态风险 |

提示格式：
```
⚠️  WARNING: Skill D detected quality violations:
    - Logic depth 18 exceeds budget 10
    - CDC risk HIGH: rx_data used in clk_sys domain

  Recommendation: Add synchronizer FFs for rx_data crossing

  Choose: [C]ontinue  [B]ack to Stage 1  [Q]uit
```

| 选择 | 行为 |
|------|------|
| `C`（回车） | 忽略违规，继续执行 Stage 4 |
| `B` 或 `Q` | 抛出 `RuntimeError("skill_d_gate_rejected")` → Supervisor 路由 |

### Stage 4 — 仿真自动修复循环

**自动阶段（无需用户干预）：**
- 最多 **5 轮** iverilog 编译 + vvp 仿真
- 每轮失败时调用 Debugger，Debugger 获得 `timing_model.yaml` 上下文有依据地修复 RTL
- TB 防篡改：每次 Debugger 调用前后对 `workspace/tb/` 做 MD5 快照，若测试台被修改则**自动还原**并打印警告
- 无测试台（`tb_*.v` 不存在）：跳过循环直接返回 False

**超限后（Supervisor 接管）：**
- 5 轮后仍失败 → 返回 False，流水线调用 Supervisor 决策路由

### Stage 5 — KPI Dashboard 门控

综合完成后打印 KPI 对比看板，当面积超出 `target_kpis.max_cells` 超过 **20%** 时弹出提示：

```
──────────────────────────────────────────────────────────
  KPI Dashboard
──────────────────────────────────────────────────────────
  Cells: 6200
  Target Freq:  300 MHz  (STA requires dedicated tool)
  Area:  6200 / 5000 cells (124%) ✗ OVER

  ⚠️  Area exceeds target by 24% — consider revising Stage 1

  Choose: [C]ontinue  [B]ack to Stage 1  [Q]uit
──────────────────────────────────────────────────────────
```

| 选择 | 行为 |
|------|------|
| `C`（回车） | 接受结果，流水线正常结束 |
| `B` 或 `Q` | `sys.exit(1)`（已知问题：尚未接入 Supervisor 路由） |

> **注意**：频率 KPI 需要 STA 工具（如 OpenSTA）才能精确验证，Yosys 仅输出门级网表，VeriFlow 当前不做频率达成判定。

### validate / complete 子命令说明

这两个子命令主要供 **Claude 在 REPL 模式下自调用**，用于哨兵文件握手协议：

| 命令 | 输出 | 作用 |
|------|------|------|
| `validate --stage 1` | `VALIDATE: PASS / FAIL` | 检查 spec.json 字段完整性、target_kpis、频率一致性 |
| `complete --stage 1` | `COMPLETE: OK` | 写入 `workspace/docs/stage1.done`（含 MD5 校验和） |
| `validate --stage 2` | `VALIDATE: PASS / FAIL` | 检查 timing_model.yaml + tb_*.v 存在性 |
| `complete --stage 2` | `COMPLETE: OK` | 写入 `workspace/docs/stage2.done` |

---

## 支持库

```
verilog_flow/
├── common/
│   ├── kpi.py              # KPITracker：记录每 stage 耗时和成功率，写入 kpi.json
│   └── experience_db.py    # ExperienceDB：历史成功模式查询（Stage 3）+ 失败案例（Supervisor）
└── defaults/
    ├── project_templates.json          # 三种模式的完整配置
    ├── coding_style/generic/           # Verilog 风格指南（注入 Stage 3）
    ├── templates/generic/              # Verilog 模块模板（FIFO、CDC、FSM 等）
    └── stage1/schemas/arch_spec_v2.json  # spec.json JSON Schema 校验
```

---

## 更新日志

### v8.3.2 (2026-03-27) — 工具层质量加固

基于 `test-uart-16558` 项目分析，修复 5 项系统性缺陷：

- **Supervisor 全局扫描**：修复 RTL 模式问题时，必须扫描所有文件的同类模式并全部修复
- **目标频率注入**：Stage 1 kickoff 从 `project_config.json` 读取频率并注入 prompt
- **频率一致性校验**：`validate --stage 1` 新增 `FREQ_MISMATCH` 检查
- **Skill D 分析完整性**：`analyzed_files` 强制列出所有文件；新增 FIFO/RAM cell 估算规则
- **测试台质量**：波特率等待周期必须按公式计算；写数据场景必须有读回断言

### v8.3.1 (2026-03-24) — 代码质量优化

- 接入 `verilog_flow/` 支持库（kpi.py、experience_db.py、project_templates.json、coding_style/）
- 新增 `--resume` 断点续跑标志
- `cmd_validate` 补全：Stage 2 YAML 内容校验，Stage 2.5/5 支持
- Bug 修复：`sys.exit()` 绕过状态保存、文件句柄泄漏

### v8.3.0 (2026-03-24) — 完整 5 阶段架构

- 新增 Stage 2（Timing Model）、Stage 3.5（Skill D）、Stage 2.5（Human Gate）、Stage 5（Synthesis）
- Stage 1 交互化：REPL 模式 + 哨兵文件握手协议
- TB 防篡改保护：Debugger 前后 MD5 快照，自动还原

### v8.4.0 (2026-03-25) — Supervisor 架构

- 新增 Supervisor LLM 路由机制，Stage 失败不再直接 abort
- `run_project()` 重构为 while 循环 + Supervisor 决策驱动
- Stage 4 无 testbench 时 return False，Supervisor 路由回 Stage 2

### v8.4.1 (2026-03-26) — 日志系统优化

- 每 stage 独立 JSONL 日志文件，lint 日志按迭代编号
- `pipeline_events.jsonl` 全局 stage 事件流
- deque 环形缓冲优化 GUI 日志性能，日志轮转保留最近 10 个

### v8.5.0–v8.6.0 (2026-03-26~27) — GUI 与 Stage 质量提升

- GUI 日志升级为 HTML 深色终端风格，Rich 彩色显示
- Stage 按钮状态联动（绿圈/灰圈指示器）
- Stage 2：spec.json 内容直接注入 prompt，验证输出文件真实存在
- Stage 3：内嵌 verilog-generator 7 条强制规则 + 4 步 workflow

---

## 已知限制

- Stage 5 KPI 超 20% 时仍用 `sys.exit(1)`，尚未接入 Supervisor 路由
- `jsonschema` 为可选依赖，未安装时 Stage 1 schema 校验静默跳过
- Stage 1 等待超时（3600s）不可配置

---

**版本**: 8.3.2 | **更新日期**: 2026-03-27
