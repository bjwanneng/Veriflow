# VeriFlow 项目状态备忘

> 本文件用于跨会话记录项目当前状态和关键改动，方便快速恢复上下文。

## 项目概述

VeriFlow 是一个工业级 Verilog 设计流水线工具，采用"脚本做门控，LLM 做执行"的架构。核心控制器 `veriflow_ctl.py` 管理 7 个阶段（Stage 0-6）的顺序执行、验证和完成标记。

### 阶段流程

| Stage | 名称 | Prompt 文件 |
|-------|------|-------------|
| 0 | Project Initialization | stage0_init.md |
| 1 | Micro-Architecture Specification | stage1_spec.md |
| 2 | Virtual Timing Modeling | stage2_timing.md |
| 3 | RTL Code Generation + Lint | stage3_codegen.md |
| 4 | Simulation & Verification | stage4_sim.md |
| 5 | Synthesis Analysis | stage5_synth.md |
| 6 | Closing | stage6_close.md |

### 关键文件

- `veriflow_ctl.py` — 主控制器，包含阶段验证、prompt 构建、摘要生成
- `prompts/` — 各阶段的 prompt 模板
- `SKILL.md` — Claude Code skill 入口定义

---

## 最近改动记录

### 2026-03-19: 需求驱动验证 — 需求追溯 + 覆盖率矩阵 (commit 43697fc)

**问题**: 仿真测试没有系统性追溯到需求文档。requirement.md 只在 Stage 0/1 被读取，之后丢失。cocotb 测试用例是通用的，没有从需求中提取具体功能点。

**改动**:

1. **stage1_spec.md** — 新增 Task 0（在原 Task 1 之前）
   - 0.1 需求清晰度检查：评估 requirement.md 完整性，模糊时用 AskUserQuestion 要求用户修订
   - 0.2 生成 `structured_requirements.json`：每条需求有 req_id（REQ-{FUNC|PERF|IF|CONS}-NNN）、category、description、testable、acceptance_criteria、derived_tests
   - 约束：requirements 非空、至少 1 个 functional、testable 需求必须有 acceptance_criteria

2. **stage2_timing.md** — 需求追溯覆盖矩阵
   - 顶部新增 `{{REQUIREMENT}}` 占位符，Stage 2 也能读到原始需求
   - 新增 Section 3.5：从 structured_requirements.json 生成 `requirements_coverage_matrix.json`
   - CoverageCollector 新增需求派生 coverpoint（功能→功能覆盖点，性能→性能指标覆盖点，接口→协议覆盖点）
   - test_integration.py 新增需求覆盖追踪，测试后更新 matrix 中各需求 status

3. **stage4_sim.md** — 需求覆盖率报告
   - 新增 Part E Step 16：生成 `requirements_coverage_report.json`
   - 汇总所有需求验证状态（verified/failed/not_run），按类别统计覆盖率

4. **veriflow_ctl.py** — 验证器和摘要增强
   - `build_prompt()`: `stage_id <= 1` → `stage_id <= 2`，requirement.md 注入到 Stage 2
   - `_validate_stage1()`: 检查 structured_requirements.json 存在、JSON 有效、requirements 非空、字段完整、至少 1 个 functional、testable 有 acceptance_criteria
   - `_validate_stage2()`: 检查 requirements_coverage_matrix.json 存在、JSON 有效、matrix 非空、每项有 req_id + cocotb_tests 非空、coverage_pct > 0
   - `_validate_stage4()`: 检查 requirements_coverage_report.json 存在、JSON 有效、requirements_coverage_pct > 0
   - `_generate_stage1_details`: 增加需求摘要（总数、各类别、可测试数）
   - `_generate_stage2_details`: 增加覆盖矩阵摘要（覆盖率%、已覆盖/未覆盖数）
   - `_generate_stage4_details`: 增加需求覆盖率报告摘要（各类别验证率）

### 之前: Timing Contract Chain (commit f0878c3)

引入全链路时序质量改进，Stage 1 spec 中增加 timing_contracts、cycle_behavior_tables、pipeline_stages_detail 等字段，Stage 3 RTL 要求 TIMING CONTRACT / TIMING SELF-CHECK 注释块和 per-cycle 注解。

---

## 设计决策记录

### Coding Style / Template 注入：全量注入，暂不做 RAG（2026-03-19）

**现状**: `build_prompt()` 按 vendor 分层加载 coding style（~1300 行）和 template（~1500 行），全量注入到 prompt 的 `{{CODING_STYLE}}` 和 `{{TEMPLATES}}` 占位符。优先级：generic base → vendor-specific → project_config overrides。

**结论**: 当前规模（4 个 style 文件 + 11 个模板，共 ~120KB）全量注入完全在 context window 承受范围内，不需要 RAG。

**何时重新评估**: 模板库膨胀到 50+ 个，或多厂商各自 20+ 条规则，或支持用户自定义规范上传时。届时优先考虑 tag-based metadata 过滤（给模板加 tags/protocol 字段，按 spec 关键词匹配），而非 embedding + vector DB。

---

## 数据流关系图

```
requirement.md
    ↓ (Stage 1)
structured_requirements.json    ←── 需求结构化
    ↓ (Stage 2)
requirements_coverage_matrix.json  ←── 需求→测试映射
    ↓ (Stage 4)
requirements_coverage_report.json  ←── 验证结果汇总
```
