# VeriFlow-Agent v8.1

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

## 7-Stage 流水线

| Stage | 名称 | 关键产出 |
|-------|------|----------|
| 0 | Project Initialization | 目录结构, project_config.json |
| 1 | Micro-Architecture Spec | `stage_1_spec/specs/*_spec.json` |
| 2 | Virtual Timing Modeling | YAML 场景, golden trace, Cocotb 测试 |
| 3 | RTL Code Generation + Lint | `stage_3_codegen/rtl/*.v`, 自动 testbench |
| 4 | Simulation & Verification | 单元/集成测试, 仿真日志 (全 PASS) |
| 5 | Synthesis Analysis | Yosys 综合, synth_report.json |
| 6 | Closing | `reports/final_report.md` |

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
├── veriflow_ctl.py                   # 门禁控制器 v8.1（跨平台）
├── prompts/                          # 每个 stage 的任务 prompt
│   ├── stage0_init.md
│   ├── stage1_spec.md
│   ├── stage2_timing.md
│   ├── stage3_codegen.md
│   ├── stage4_sim.md
│   ├── stage5_synth.md
│   └── stage6_close.md
└── verilog_flow/
    ├── common/
    │   ├── kpi.py                    # KPI 追踪（Pass@1, 时序收敛率）
    │   └── experience_db.py          # 经验库（失败案例记录与检索）
    ├── defaults/
    │   ├── coding_style/             # generic / xilinx / intel 编码规范
    │   └── templates/                # 可复用 Verilog 模板
    └── stage1/schemas/
        └── arch_spec_v2.json         # 架构规格 JSON Schema
```

## 项目目录结构（运行后生成）

```
your-project/
├── requirement.md                    # 设计需求文档（用户提供）
├── .veriflow/
│   ├── project_config.json           # 项目配置（含 coding_style）
│   └── stage_completed/              # Stage 完成标记（门禁依据）
├── stage_1_spec/specs/               # JSON 架构规格
├── stage_2_timing/
│   ├── scenarios/                    # YAML 时序场景
│   ├── golden_traces/                # 期望值 trace
│   └── cocotb/                       # Cocotb 测试文件
├── stage_3_codegen/
│   ├── rtl/                          # 生成的 .v 文件
│   ├── tb_autogen/                   # 自动生成的 testbench
│   └── reports/                      # lint 报告
├── stage_4_sim/
│   ├── tb/                           # 单元/集成 testbench
│   ├── sim_output/                   # 仿真日志
│   └── coverage/                     # VCD 波形文件
├── stage_5_synth/                    # 综合脚本、网表、报告
└── reports/                          # 最终报告 + stage 摘要
```

## License

MIT
