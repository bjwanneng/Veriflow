# VeriFlow-Agent v8.2

工业级 Verilog RTL 设计流水线 — **脚本做门禁，LLM 做执行**。

跨平台支持：Linux / macOS / Windows (Git Bash, MSYS2, native CMD)

## 核心架构

```
Claude Code (LLM)          veriflow_ctl.py (脚本)
    │                            │
    │  1. 调用 next             │
    │ ─────────────────────────>│ 检查前置 stage → 输出 prompt
    │                            │
    │  2. 执行 stage 任务        │
    │  (生成代码/spec/TB...)     │
    │                            │
    │  3. 调用 validate          │
    │ ─────────────────────────>│ 确定性检查 → PASS/FAIL
    │                            │
    │  4. 调用 complete          │
    │ ─────────────────────────>│ 验证通过才标记完成
    │                            │
    │  回到 1                    │
```

LLM 负责创造性工作（写 Verilog、设计架构、调试），脚本负责"能不能过"的硬判断。LLM 无法跳过 stage、无法绕过验证。

## 三种执行模式 (v8.2 新特性)

| 模式 | 阶段 | 适用场景 | 验证级别 | 典型用时 |
|------|------|----------|----------|----------|
| **Quick** | 0→1→3→4→6 (5阶段) | 简单模块、原型验证、快速迭代 | Minimal | 30-60 分钟 |
| **Standard** | 0→1→2→3→4→5→6 (7阶段) | 一般项目、推荐默认 | Standard | 2-4 小时 |
| **Enterprise** | 7+阶段含子阶段 | 关键项目、工业级质量 | Strict | 1-2 天 |

### 阶段流程对比

| Stage | Quick | Standard | Enterprise | 说明 |
|-------|-------|----------|------------|------|
| 0 | ✅ | ✅ | ✅ | 项目初始化 |
| 1 | ✅(简化) | ✅ | ✅(含评审) | 架构规格 |
| 1.5 | ❌ | ❌ | ✅ | 架构评审 |
| 2 | ❌ | ✅ | ✅ | 虚拟时序建模 |
| 3 | ✅ | ✅ | ✅(含评审) | RTL代码生成 |
| 3.5 | ❌ | ❌ | ✅ | 代码评审与优化 |
| 4 | ✅(简化) | ✅ | ✅ | 仿真验证 |
| 5 | ❌ | ✅ | ✅ | 综合分析 |
| 6 | ✅ | ✅ | ✅ | 项目收尾 |

## 7-Stage 流水线

| Stage | 名称 | 关键产出 |
|-------|------|----------|
| 0 | Project Initialization | 目录结构, project_config.json |
| 1 | Micro-Architecture Spec | `*_spec.json`, `structured_requirements.json` |
| 2 | Virtual Timing Modeling | YAML 场景, golden trace, Cocotb 测试, `requirements_coverage_matrix.json` |
| 3 | RTL Code Generation + Lint | `stage_3_codegen/rtl/*.v`, 自动 testbench |
| 4 | Simulation & Verification | 单元/集成测试, 仿真日志, `requirements_coverage_report.json` |
| 5 | Synthesis Analysis | Yosys 综合, synth_report.json |
| 6 | Closing | `reports/final_report.md` |

## v8.2 更新内容

### 多模式架构 (v8.2.0)

**三种执行模式**：
- **Quick 模式**：5个阶段（0→1→3→4→6），跳过时序建模和综合，适合快速原型验证
- **Standard 模式**：7个完整阶段，推荐默认
- **Enterprise 模式**：含子阶段（1.5架构评审、3.5代码评审），严格验证

**模式感知验证**：
- Minimal：基本文件存在性和编译检查
- Standard：完整质量门控（spec有效性、lint、仿真）
- Strict：企业级门控（评审、形式检查、覆盖率）

**新增命令**：
- `veriflow_ctl.py init` - 交互式项目初始化，含模式选择
- `veriflow_ctl.py mode` - 查看或切换当前模式

### 需求驱动验证 — 需求追溯 + 覆盖率矩阵

v8.1 之前，requirement.md 只在 Stage 0/1 被读取，之后就丢失了。cocotb 测试用例是通用的（data_range、protocol_corner_cases），没有从需求中提取具体的功能点、性能指标、接口约束来生成针对性测试。v8.2 建立了从需求到验证的全链路追溯。

**Stage 1: 需求结构化**
- 新增 Task 0（在架构分析之前）：解析 requirement.md → `structured_requirements.json`
- 需求清晰度检查：评估功能/性能/接口/边界条件的完整性，模糊时要求用户修订
- 每条需求有 `req_id`（REQ-{FUNC|PERF|IF|CONS}-NNN）、`category`、`testable`、`acceptance_criteria`
- 验证器检查：JSON 有效、requirements 非空、至少 1 个 functional、testable 需求有 acceptance_criteria

**Stage 2: 需求覆盖矩阵**
- requirement.md 通过 `{{REQUIREMENT}}` 占位符注入到 Stage 2 prompt
- 新增 Section 3.5：生成 `requirements_coverage_matrix.json`，将每个 testable 需求映射到 cocotb 测试、coverpoint、YAML scenario
- CoverageCollector 新增需求派生 coverpoint（功能→功能覆盖点，性能→性能指标覆盖点，接口→协议覆盖点）
- test_integration.py 测试后更新 matrix 中各需求的 status
- 验证器检查：matrix 非空、每项有 cocotb_tests、coverage_pct > 0

**Stage 4: 需求覆盖率报告**
- 新增 Part E Step 16：生成 `requirements_coverage_report.json`
- 汇总所有需求验证状态（verified/failed/not_run），按类别统计覆盖率
- 验证器检查：requirements_coverage_pct > 0

**数据流**:
```
requirement.md
    ↓ (Stage 1)
structured_requirements.json    ←── 需求结构化
    ↓ (Stage 2)
requirements_coverage_matrix.json  ←── 需求→测试映射
    ↓ (Stage 4)
requirements_coverage_report.json  ←── 验证结果汇总
```

## v8.1 更新内容

### 跨平台兼容
- 控制器脚本启动时强制 UTF-8 stdout/stderr，解决 Windows GBK 终端的 `UnicodeEncodeError`
- 工具链检测 (`_get_toolchain_env`) 自动搜索 Windows / macOS (Homebrew) / Linux 常见安装路径
- `iverilog` 编译检查使用 `tempfile` 替代 `/dev/null` vs `NUL` 的平台判断
- `requirement.md` 读取支持编码自动检测（utf-8 → utf-8-sig → gbk → gb2312 → latin-1）
- 所有 prompt 模板中的 shell 命令改用文件重定向 (`> file.log 2>&1`)，不再依赖 `tee`/`head`/`timeout`

### 编码风格配置化
- Reset 信号类型和名称从 `project_config.json` 的 `coding_style` 字段读取，不再硬编码 `rst_n`
- 支持 4 种 reset 风格：`async_active_low`, `async_active_high`, `sync_active_low`, `sync_active_high`
- `build_prompt()` 自动将 `coding_style` 配置注入到 prompt 的 `{{CODING_STYLE}}` 占位符
- 所有 prompt 模板（stage1~stage4）添加了"从 project config 读取 reset 配置"的说明

### 验证增强
- Stage 3 验证：testbench reset 信号检查支持多种 reset 名称（`rst`, `rst_n`, `reset`）
- Stage 4 验证：仿真日志增加正向完成指标检查（`ALL TESTS PASSED`, `PASSED` 等）
- `glob()` 结果使用 `list()` 包装，修复 Python 3.12+ 的 `TypeError`

### 输出安全
- 摘要生成器中的 emoji（✅✓⚠️）全部替换为 ASCII 等价物（[DONE][OK][WARN]）

## 使用方式

### 前置条件

- Claude Code CLI 已安装
- Python 3.10+
- iverilog + yosys（推荐 [oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)）

### 工具链安装路径

控制器会自动搜索以下路径：

| 平台 | 搜索路径 |
|------|----------|
| Windows | `C:/oss-cad-suite/bin`, `C:/oss-cad-suite/lib` |
| macOS | `/opt/homebrew/bin`, `/usr/local/bin` |
| Linux | `/opt/oss-cad-suite/bin`, `/usr/bin` |
| 通用 | `~/oss-cad-suite/bin`, `~/oss-cad-suite/lib` |

如果工具不在上述路径，手动添加：
```bash
# Windows (Git Bash / MSYS2)
export PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
# macOS
export PATH="/opt/homebrew/bin:$PATH"
# Linux
export PATH="/opt/oss-cad-suite/bin:$PATH"
```

### 作为 Claude Code Skill 使用（推荐）

1. 将本目录放在 `~/.claude/skills/verilog-flow-skill/`
2. 在项目目录下创建 `requirement.md` 描述设计需求
3. 在 Claude Code 中提及 Verilog/RTL 设计，skill 自动触发
4. Claude Code 按照 SKILL.md 中的循环协议自动执行全流程

### 手动使用 veriflow_ctl.py

```bash
CTL="~/.claude/skills/verilog-flow-skill/veriflow_ctl.py"

# 初始化新项目（交互式向导，含模式选择）
python "$CTL" init -d ./my_project

# 查看/切换执行模式
python "$CTL" mode -d ./my_project              # 查看当前模式
python "$CTL" mode -d ./my_project quick        # 切换到 Quick 模式
python "$CTL" mode -d ./my_project standard     # 切换到 Standard 模式
python "$CTL" mode -d ./my_project enterprise   # 切换到 Enterprise 模式

# 查看进度
python "$CTL" status -d ./my_project

# 获取下一个 stage 的任务 prompt
python "$CTL" next -d ./my_project

# 验证 stage 产出
python "$CTL" validate -d ./my_project 3

# 标记 stage 完成（验证不过会拒绝）
python "$CTL" complete -d ./my_project 3

# 回退到某个 stage
python "$CTL" rollback -d ./my_project 1

# 查看 stage 详情
python "$CTL" info -d ./my_project 3
```

## 编码风格配置

Stage 0 初始化时会在 `.veriflow/project_config.json` 中写入 `coding_style` 字段：

```json
{
  "coding_style": {
    "reset_type": "sync_active_high",
    "reset_signal": "rst",
    "clock_edge": "posedge",
    "naming": "snake_case",
    "port_style": "ANSI",
    "indent": 4
  }
}
```

支持的 `reset_type` 值：
- `async_active_low` — 异步低有效 (`rst_n`)，默认值
- `async_active_high` — 异步高有效 (`rst`)
- `sync_active_low` — 同步低有效 (`rst_n`)
- `sync_active_high` — 同步高有效 (`rst`)

后续所有 stage（spec 生成、RTL 编码、testbench、验证）都会从此配置读取 reset 风格，确保全流程一致。

## 目录结构

```
verilog-flow-skill/
├── SKILL.md                          # Claude Code skill 入口定义
├── README.md                         # 中文说明文档
├── README_EN.md                      # English documentation
├── CHANGELOG.md                      # 更新日志
├── readme_first.md                   # 项目状态备忘
├── veriflow_ctl.py                   # 门禁控制器 v8.2（跨平台）
├── prompts/                          # 每个 stage 的任务 prompt
│   ├── stage0_init.md
│   ├── stage1_spec.md
│   ├── stage1_spec_quick.md         # Quick 模式专用精简版
│   ├── stage2_timing.md
│   ├── stage3_codegen.md
│   ├── stage4_sim.md
│   ├── stage5_synth.md
│   └── stage6_close.md
└── verilog_flow/
    ├── common/
    │   ├── kpi.py                    # KPI 追踪（Pass@1, 时序收敛率）
    │   └── experience_db.py          # 经验库（失败案例记录与检索）
    └── defaults/
        ├── coding_style/             # generic / xilinx / intel 编码规范
        ├── templates/                # 可复用 Verilog 模板
        └── project_templates.json    # 三种模式的配置模板
```

## 项目目录结构（运行后生成）

```
your-project/
├── requirement.md                    # 设计需求文档（用户提供）
├── .veriflow/
│   ├── project_config.json           # 项目配置（含 coding_style）
│   └── stage_completed/              # Stage 完成标记（门禁依据）
├── stage_1_spec/specs/               # JSON 架构规格 + structured_requirements.json
├── stage_2_timing/
│   ├── scenarios/                    # YAML 时序场景
│   ├── golden_traces/                # 期望值 trace
│   └── cocotb/                       # Cocotb 测试 + requirements_coverage_matrix.json
├── stage_3_codegen/
│   ├── rtl/                          # 生成的 .v 文件
│   ├── tb_autogen/                   # 自动生成的 testbench
│   └── reports/                      # lint 报告
├── stage_4_sim/
│   ├── tb/                           # 单元/集成 testbench
│   ├── sim_output/                   # 仿真日志
│   ├── cocotb_regression/            # Cocotb 回归测试
│   ├── coverage/                     # VCD 波形文件
│   └── requirements_coverage_report.json  # 需求覆盖率报告
├── stage_5_synth/                    # 综合脚本、网表、报告
└── reports/                          # 最终报告 + stage 摘要
```

## License

MIT
