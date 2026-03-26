# VeriFlow 项目状态备忘

> 每次打开项目时先读此文件，快速恢复上下文。

---

## 当前版本

**v8.5.0** — 2026-03-26

---

## 项目架构

控制权反转（Control Flow Inversion）：Python 主控状态机 + LLM Worker 节点。

```
veriflow_ctl.py          ← 唯一入口，主控所有阶段（~2300 行）
veriflow_gui.py          ← Gradio GUI 包装（~1500 行）
prompts/                 ← 每个 stage 的 LLM 工作指令
  stage1_architect.md    ← Stage 1 Q&A 架构分析
  stage2_timing.md       ← Stage 2 时序建模
  stage3_module.md       ← Stage 3 单模块 RTL 生成（主用）
  stage3_coder.md        ← Stage 3 全量生成（备用）
  stage35_skill_d.md     ← Stage 3.5 静态分析
  stage4_debugger.md     ← Stage 4 调试修复
  supervisor.md          ← Supervisor 路由决策（新增）
tools/                   ← EDA 工具封装（iverilog / Yosys）
verilog_flow/
  common/kpi.py          ← KPI 追踪（已接入 pipeline）
  common/experience_db.py← 经验数据库（已接入 Stage 3 + Supervisor）
  defaults/
    project_templates.json  ← 模式配置
    coding_style/generic/   ← 风格指南（注入 Stage 3）
    templates/generic/      ← Verilog 模板（注入 Stage 3）
  stage1/schemas/arch_spec_v2.json  ← spec.json schema 校验
```

---

## 阶段流程

| 模式 | 阶段序列（内部整数编码） |
|------|---------|
| quick | 1 → 15 → 3 → 35 |
| standard | 1 → 15 → 2 → 3 → 35 → 4 → 5 |
| enterprise | 1 → 15 → 2 → 3 → 35 → 4 → 5（与 standard 相同，保留扩展） |

阶段编号说明：
- **1** Architect（REPL 交互，生成 spec.json）
- **15** Micro-Architecture（微架构文档，生成 micro_arch.md）
- **2** Timing Model（生成 timing_model.yaml + testbench）
- **3** RTL Coder（并行逐模块生成 Verilog）
- **35** Skill D（Phase 1: Lint 循环 + Debugger 修复；Phase 2: LLM 静态质量分析）
- **4** Simulation Loop（纯仿真，Debugger 自动修复；quick 模式不执行）
- **5** Yosys Synthesis + KPI（standard/enterprise 专属）

float → int 转换规则：`1.5 → 15`，`3.5 → 35`，`3.6 → 36`（通过 `_normalize_stage_token()`）

---

## 关键机制

### Stage 1 自动启动（核心！）
Stage 1 打开 Claude REPL 时**自动开始任务**的机制：
1. `stage1_architect()` 把 kickoff 内容写入项目目录的 `CLAUDE.md`
2. Claude Code 启动时自动读取当前目录的 `CLAUDE.md` 作为系统 prompt
3. 初始消息通过**位置参数**传入：`claude --flags "初始消息"`，Claude 立刻执行
4. Stage 1 完成后自动恢复（或删除）项目目录的 `CLAUDE.md`

**实现**：`_launch_claude_repl(project_dir, initial_message="begin")`
在 PowerShell 脚本中生成：`& 'claude' --dangerously-skip-permissions --add-dir 'dir' 'begin'`

### Supervisor 架构（v8.4 新增）
Stage 失败时不再直接 abort，而是调用 Supervisor LLM 决策路由：
```
Stage 失败 → call_supervisor() → 返回 SupervisorDecision
  "retry_stage"    → 回跳到指定 stage 重试（写入 supervisor_hint.md）
  "escalate_stage" → 回跳到更早 stage 重新生成
  "continue"       → 忽略失败继续
  "abort"          → 终止流水线
最多 3 次 Supervisor 重试，超限直接 abort
```
Supervisor hint 存于 `.veriflow/supervisor_hint.md`，由 Stage 3 和 Stage 4 Debugger 读取注入。

### KPITracker
每次 `run_project()` 自动记录各 stage 耗时和成功率，写入 `.veriflow/kpi.json`。

### ExperienceDB
- Stage 3 执行前查询历史成功模式（按 module_type + 频率），注入为 `EXPERIENCE_HINT`
- Supervisor 查询历史失败案例辅助决策
- 数据存于 `.veriflow/experience_db/`

### --resume 断点续跑
读取 `pipeline_state.json` 中的 `completed_stages`，跳过已完成的 stage。

---

## 关键文件位置索引

| 文件 | 关键区域 | 说明 |
|------|---------|------|
| `veriflow_ctl.py:46` | `MODE_STAGES` | 各模式的阶段序列（整数编码） |
| `veriflow_ctl.py:175` | `_launch_claude_repl()` | Stage 1 启动（写 CLAUDE.md → 自动触发） |
| `veriflow_ctl.py:964` | `stage1_architect()` | Stage 1 主体，CLAUDE.md 写/恢复逻辑 |
| `veriflow_ctl.py:1111` | `stage3_coder()` | 并行模块生成 + ExperienceDB 查询 |
| `veriflow_ctl.py:1800` | `_write_supervisor_hint()` | Supervisor hint 写入 |
| `veriflow_ctl.py:1815` | `call_supervisor()` | Supervisor LLM 调用 + JSON 解析 |
| `veriflow_ctl.py:1900` | `_dispatch_stage()` | Stage dispatch 封装 |
| `veriflow_ctl.py:1915` | `run_project()` | while 循环 + Supervisor 路由主体 |
| `veriflow_ctl.py:2190` | `main()` argparse | `--resume` / `--stages` / `--feedback` 等参数 |
| `veriflow_gui.py:1403` | `mode_stages_map` | GUI 阶段列表（与 Controller 保持同步） |
| `prompts/supervisor.md` | 全文 | Supervisor 决策 prompt（输出严格 JSON） |

---

## 已知 Bug / 局限

- Stage 5 KPI 超 20% 时仍用 `sys.exit(1)`——尚未接入 Supervisor 路由（待修）
- `jsonschema` 为可选依赖，未安装时 Stage 1 schema 校验静默跳过
- Stage 1 超时（3600s）不可配置

---

## 待办事项

- [ ] Stage 5 KPI 超限改为 raise RuntimeError，接入 Supervisor
- [ ] `experience_db.record_failure()` 在 Stage 4 失败时调用（目前只查询不记录）
- [ ] `jsonschema` 加入 requirements.txt（可选依赖注明）
- [ ] GUI `stage_progress` 字典中加入 stage 15、36 的进度映射

---

## 常用命令

```bash
# 运行流水线（标准模式）
python veriflow_ctl.py run --mode standard -d ./my_project

# 断点续跑
python veriflow_ctl.py run --mode standard -d ./my_project --resume

# 快速模式（仅 lint，无仿真）
python veriflow_ctl.py run --mode quick -d ./my_project

# 带反馈修订
python veriflow_ctl.py run --mode standard -d ./my_project --feedback feedback.md

# 只重新生成某个模块
python veriflow_ctl.py run --mode standard -d ./my_project --stages 3 --modules uart_tx

# 验证某阶段输出（由 Claude 在 REPL 中调用）
python veriflow_ctl.py validate --stage 1 -d ./my_project

# 标记阶段完成（由 Claude 在 REPL 中调用）
python veriflow_ctl.py complete --stage 1 -d ./my_project
```

---

## v8.4.0 改动记录（2026-03-25）

### Supervisor 架构（核心新增）
- 新增 `prompts/supervisor.md`：接受 pipeline context JSON，输出路由决策 JSON
- 新增 `SupervisorDecision` TypedDict
- 新增 `call_supervisor()`：调用 Supervisor LLM，从 output 中 regex 提取 JSON
- 新增 `_write_supervisor_hint()` / `_read_supervisor_hint()`
- `run_project()` 重构为 while 循环，失败时路由到 Supervisor（最多 3 次重试）
- `_dispatch_stage()` 抽取为独立函数

### Bug 修复
- **Stage 4 `[B]ack` 死代码**：移除无效交互输入，直接 return False 由 Supervisor 接管
- **`_check_skill_d_gates()` sys.exit**：改为 `raise RuntimeError("skill_d_gate_rejected")`
- **workspace 目录创建顺序**：mkdir 移到 `save_project_state()` 之前，避免 FileNotFoundError

### Stage 1 自动启动修复（三次迭代）
- 最终方案：写入项目目录 `CLAUDE.md`，Claude 启动时自动读取并执行
- 放弃方案：①命令行位置参数（Claude 交互模式不支持）②剪贴板注入（需用户手动操作）
- `_launch_claude_repl()` 精简为 PowerShell 脚本启动，无需传初始消息

### 功能激活
- **KPITracker**：`run_project()` 全程记录 stage metrics，写入 `.veriflow/kpi.json`
- **ExperienceDB**：Stage 3 查历史 pattern，Supervisor 查历史失败案例
- **Schema 验证**：`cmd_validate()` Stage 1 分支接入 `arch_spec_v2.json`（jsonschema 可选）
- **mock 补全**：`mock_claude_execution()` 新增 stage15 和 supervisor 分支

### GUI 对齐
- `veriflow_gui.py:1403` `mode_stages_map` 补全 stage 1.5 和 3.6

### --resume 标志
- argparse 新增 `--resume`，`run_project()` 新增 `resume: bool` 参数
- 读 `completed_stages` 跳过已完成 stage，打印提示信息

---

---

## v8.4.1 改动记录（2026-03-26）

### 日志系统全面优化

**veriflow_ctl.py**
- 新增 `LOG_ICONS` 模块级常量，消除 `_log()` 内的重复 icon dict
- 新增 `_current_jsonl_path` + `_set_log_file()`：每次 `run_project()` 写 `run_<ts>.jsonl`
- `_log()` 在持锁块内追加 JSONL 结构化条目
- `run_lint()` 新增 `log_name` 参数（默认 `"linter_error"`，向后兼容）
- `stage35_skill_d()` 传 `log_name=f"linter_iter_{iteration}"`，每轮独立文件
- 新增 `_emit_stage_event()`，写 `.veriflow/pipeline_events.jsonl`
- `run_project()` 开头调用 `clear_error_logs()` + `_set_log_file()`（修复跨 run 污染）
- `run_project()` while 循环内在 `_dispatch_stage()` 前后各调用 `_emit_stage_event()`

**veriflow_gui.py**
- 新增 `from collections import deque`
- 新增模块级 `LOG_ICONS`，`add_log()` 改用它（消除重复）
- `GlobalState` 新增 `current_log_path`、`current_logs` 字段，`reset()` 同步清零
- 新增 `_clean_old_run_logs(keep_n=10)`，在 `get_run_log_path()` 中调用
- `emit()` 重写：单行缓冲文件句柄 + `deque(maxlen=2000)`，O(1) append，O(2000) join
- 新增 `_close_log_file()`，在所有退出路径上调用（3 处）
- `stop_pipeline()` 将终止行追加写入磁盘日志
- 激活 `log_filter` Dropdown：绑定 `_filter_logs()` 到 `log_filter.change()`

---

## v8.5.0 改动记录（2026-03-26）

### 日志显示优化
- **Rich 终端风格显示**：集成 Rich 库，实现类似终端的彩色日志显示
- **HTML 日志组件**：将 log_output 从 gr.TextArea 升级为 gr.HTML，支持富文本显示
- **自动配色**：根据日志类型自动配色（info: 青色，success: 绿色，warning: 黄色，error: 红色，stage: 蓝色，command: 洋红色）
- **响应式设计**：深色主题背景，等宽字体，自动适应容器宽度
- **容错设计**：当 Rich 库不可用时，自动降级为简单 HTML 彩色文本

### 功能增强
- **启动改进**：添加详细的启动过程输出，包括 Python 版本和系统信息
- **错误处理**：增强了异常处理和错误报告，提供详细的堆栈跟踪信息
- **自动端口分配**：移除硬编码的 server_port，让 Gradio 自动分配可用端口
- **启动信息优化**：改进了启动信息的显示，包括访问 URL 提示

### 稳定性提升
- **编码修复**：进一步优化了 Windows 下的编码问题
- **状态管理**：在 GlobalState 中添加了 current_logs_html 字段来管理 HTML 格式的日志
- **过滤器兼容**：更新了日志过滤器，支持 HTML 格式的日志过滤
- **停止功能优化**：改进了 stop_pipeline 函数，确保停止操作能正确记录到日志

---

**版本**: 8.5.0 | **更新日期**: 2026-03-26
