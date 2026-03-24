# VeriFlow 8.3

工业级 Verilog RTL 设计流水线 —— 控制权反转架构 (Control Flow Inversion)

## 核心架构

VeriFlow 8.3 采用**控制权反转**架构：Python 作为主控状态机，LLM 作为 Worker 节点。

```
┌──────────────────────────────────────────────────────────────────┐
│                      Python Controller                            │
│                   (veriflow_ctl.py — Master)                      │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│ Stage 1  │ Stage 2  │ Stage 36 │ Stage 3  │ Stage 35 │ Stage 4  │
│Architect │ Timing   │  Human   │  Coder   │ Skill D  │  Debug   │
│(REPL交互)│  Model   │   Gate   │  (RTL)   │ (静态分析)│ (仿真循环)│
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                                                    │
                                          ┌─────────▼─────────┐
                                          │    EDA Tools       │
                                          │  iverilog / Yosys  │
                                          └───────────────────┘
```

## 执行模式

| 模式 | 阶段序列 | 适用场景 |
|------|---------|---------|
| **Quick** | 1 → 3 → 4(lint-only) | 快速语法验证，几分钟出结果 |
| **Standard** | 1 → 2 → 36 → 3 → 35 → 4(sim) | 完整功能验证（推荐） |
| **Enterprise** | 1 → 2 → 36 → 3 → 35 → 4(sim) → 5 | 含综合 + KPI 比对 |

## 阶段说明

### Stage 1 — Architect（交互式架构分析）
- 以 **REPL 模式**启动 Claude，进行问答式架构拆解
- Claude 通过提问澄清需求，生成 `workspace/docs/spec.json`
- 完成后 Claude 调用 `validate --stage 1` + `complete --stage 1` 写入哨兵文件
- spec.json 必须包含 `target_kpis`（频率/面积/功耗）、`pipeline_stages`、`critical_path_budget`

### Stage 2 — Virtual Timing Model
- 读取 spec.json，生成 `workspace/docs/timing_model.yaml`（行为断言 + 激励序列）
- 同步生成 `workspace/tb/tb_<design>.v`（激励与 Golden Trace 同源）
- YAML 格式直观，便于人工审查

### Stage 36 — Human Gate（人工门控）
- 暂停流水线，展示 timing_model.yaml 供用户审查
- 用户确认行为规格正确后，才进入代码生成阶段
- 防止错误的行为规格传播到后续阶段

### Stage 3 — RTL Coder
- 逐模块生成 Verilog RTL，输出到 `workspace/rtl/`
- 不生成 TB（TB 来自 Stage 2，保持激励一致性）

### Stage 35 — Skill D（静态质量分析）
- 读取所有 RTL 文件，进行静态分析（无需 EDA 工具）
- 检测：逻辑深度估算、CDC 风险、Latch 推断风险
- 输出 `workspace/docs/static_report.json`
- 质量门控：逻辑深度超预算或 HIGH CDC 风险 → 询问用户是否继续

### Stage 4 — Simulation Loop
- Quick 模式：仅 lint（`iverilog -Wall`）
- Standard/Enterprise 模式：lint + 仿真（`iverilog + vvp`）
- 仿真失败时，Debugger 获得 timing_model.yaml 上下文，有依据地修复
- **TB 防篡改保护**：Debugger 调用前后对 `workspace/tb/` 做 MD5 快照，检测到修改自动还原

### Stage 5 — Yosys Synthesis（Enterprise 专属）
- 调用 Yosys 综合，解析 `stat -json` 输出
- 对比 spec.json 中的 `target_kpis`（频率/面积/功耗）
- 输出 `workspace/docs/synth_report.json` + 终端 KPI Dashboard
- Yosys 未安装 → 优雅跳过，不中止流水线

## 快速开始

### 前置条件

- Python 3.8+
- Icarus Verilog（`iverilog` 和 `vvp`）
- Claude CLI（`claude` 命令可用）
- （Enterprise 模式）Yosys

### 安装 EDA 工具

```bash
# 推荐：使用 oss-cad-suite（含 iverilog + Yosys）
# 下载：https://github.com/YosysHQ/oss-cad-suite-build/releases
export PATH="/path/to/oss-cad-suite/bin:$PATH"

# 或单独安装 iverilog
# macOS: brew install icarus-verilog
# Ubuntu: apt-get install iverilog
```

### 使用

```bash
# 1. 创建项目目录并写需求
mkdir my_project
cat > my_project/requirement.md << 'EOF'
# UART TX 发送器

设计一个 UART 发送器：
- 波特率：115200
- 数据位：8位，无校验，1停止位
- 接口：valid/ready 握手
- 目标频率：100 MHz
EOF

# 2. 运行流水线（Quick 模式，快速验证）
python veriflow_ctl.py run --mode quick -d ./my_project

# 3. 运行流水线（Standard 模式，完整验证）
python veriflow_ctl.py run --mode standard -d ./my_project

# 4. 运行流水线（Enterprise 模式，含综合）
python veriflow_ctl.py run --mode enterprise -d ./my_project
```

## 命令参考

```bash
# 运行流水线
python veriflow_ctl.py run --mode {quick,standard,enterprise} -d <项目目录>

# 验证指定阶段输出（由 Claude 在 REPL 中调用）
python veriflow_ctl.py validate --stage <N> -d <项目目录>

# 标记阶段完成（由 Claude 在 REPL 中调用，需先通过 validate）
python veriflow_ctl.py complete --stage <N> -d <项目目录>
```

### validate / complete 说明

这两个子命令主要供 **Claude 在 REPL 模式下自调用**，用于哨兵文件握手协议：

| 命令 | 作用 |
|------|------|
| `validate --stage 1` | 检查 spec.json 字段完整性（含 target_kpis） |
| `complete --stage 1` | 写入 `workspace/docs/stage1.done`（含 MD5 校验和） |
| `validate --stage 2` | 检查 timing_model.yaml + tb_*.v 存在性 |
| `complete --stage 2` | 写入 `workspace/docs/stage2.done` |

## 项目结构

```
my_project/
├── requirement.md              # 设计需求（输入）
├── .veriflow/
│   ├── project_config.json     # 项目配置
│   └── pipeline_state.json     # 流水线状态（含各阶段决策记录）
└── workspace/
    ├── docs/
    │   ├── spec.json           # 架构规格（Stage 1 输出）
    │   ├── timing_model.yaml   # 行为断言 + 激励（Stage 2 输出）
    │   ├── static_report.json  # 静态分析报告（Stage 35 输出）
    │   ├── synth_report.json   # 综合报告（Stage 5 输出）
    │   └── stage*.done         # 阶段完成哨兵文件
    ├── rtl/
    │   └── *.v                 # RTL 源文件（Stage 3 输出）
    └── tb/
        └── tb_*.v              # 测试台（Stage 2 输出，只读）
```

## 质量门控策略

检测到违规时，不自动回退，而是：

1. 打印详细违规原因
2. 询问用户：`[C]ontinue anyway / [B]ack to stage X / [Q]uit`
3. 记录决策到 `pipeline_state.json`（用于后续审计）

| 触发条件 | 门控位置 |
|---------|---------|
| spec.json 缺少 target_kpis | Stage 1 validate |
| timing_model.yaml 字段不完整 | Stage 2 validate |
| 逻辑深度超过 critical_path_budget | Stage 35 |
| CDC 风险等级为 HIGH | Stage 35 |
| 仿真失败超过 max_iterations | Stage 4 |
| KPI 缺口 > 20% | Stage 5 |

## 依赖要求

| 工具 | 用途 | 必需 |
|------|------|------|
| Python 3.8+ | 主控脚本 | 是 |
| Claude CLI | LLM Worker | 是 |
| iverilog / vvp | Lint + 仿真 | 是 |
| Yosys | 综合（Enterprise） | 否 |

## 更新日志

### v8.3.0 (2026-03-24)
- **新增 Stage 2**：虚拟时序建模（timing_model.yaml + TB 生成）
- **新增 Stage 35**：Skill D 静态质量分析（逻辑深度/CDC/Latch）
- **新增 Stage 36**：人工门控（Stage 2 后暂停等待用户确认）
- **新增 Stage 5**：Yosys 综合 + KPI 比对（Enterprise 模式）
- **Stage 1 交互化**：REPL 模式 + 哨兵文件握手，支持问答式架构分析
- **新增 validate/complete 子命令**：供 Claude 在 REPL 中自调用
- **TB 防篡改保护**：Debugger 调用前后 MD5 快照，自动还原被篡改的 TB
- **Stage 4 增强**：Debugger 获得 timing_model.yaml 上下文，修复更有依据
- 模式重定义：quick=[1,3,4], standard=[1,2,36,3,35,4], enterprise=[1,2,36,3,35,4,5]

### v8.2.0 (2026-03-23)
- 控制权反转架构（Python 主控 + LLM Worker）
- 简化 prompt 集（从 7 个精简到 3 个）
- 新的 `run` 命令替代旧的 `next/validate/complete`

## 许可证

MIT License — 详见 LICENSE 文件

---

**版本**: 8.3.0 | **更新日期**: 2026-03-24
