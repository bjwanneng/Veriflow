# VeriFlow 项目状态备忘

> 本文件用于跨会话记录项目当前状态和关键改动，方便快速恢复上下文。

## 项目概述

VeriFlow 是一个工业级 Verilog 设计流水线工具，采用"脚本做门控，LLM 做执行"的架构。核心控制器 `veriflow_ctl.py` 管理多阶段（Stage）的顺序执行、验证和完成标记。

### v8.2.0 重大更新：多模式架构

从 v8.2.0 开始，VeriFlow 支持三种执行模式，适应不同项目需求：

| 模式 | 阶段 | 适用场景 | 验证级别 |
|------|------|----------|----------|
| **Quick** | 0→1→3→4→6 (5阶段) | 简单模块、原型验证、快速迭代 | Minimal |
| **Standard** | 0→1→2→3→4→5→6 (7阶段) | 一般项目、推荐默认 | Standard |
| **Enterprise** | 7+阶段含子阶段 | 关键项目、工业级质量 | Strict |

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

### 核心文件

- `veriflow_ctl.py` — 主控制器，v8.2.0 重写支持多模式
- `verilog_flow/defaults/project_templates.json` — 三种模式的完整配置模板
- `SKILL.md` — Claude Code skill 入口，v8.2.0 简化 60%
- `prompts/` — 各阶段的 prompt 模板，新增 `stage1_spec_quick.md`

---

## 最近改动记录

### 2026-03-21: v8.2.0 多模式架构优化

**问题**: 原流程对简单项目过重，7个Stage全部走一遍不适合快速原型验证；Prompt过于冗长，token消耗大；SKILL.md执行协议过于繁琐。

**改动**:

1. **引入三种执行模式**
   - Quick模式：5个阶段（0→1→3→4→6），跳过Stage 2时序建模和Stage 5综合
   - Standard模式：7个阶段，推荐默认
   - Enterprise模式：含子阶段（1.5架构评审、3.5代码评审），严格验证

2. **重写 veriflow_ctl.py**
   - 新增 `MODE_CONFIG` 配置三种模式
   - 新增 `VALIDATION_RULES` 按级别定义验证规则（minimal/standard/strict）
   - 新增 `init` 命令用于项目初始化
   - 新增 `mode` 命令用于查看/切换模式
   - `validate` 和 `complete` 现在根据当前模式使用对应的验证规则

3. **新增 project_templates.json**
   - 定义三种模式的完整配置
   - 包括 stages、validation_level、features、prompt_style、testbench_depth

4. **简化 SKILL.md**
   - 执行协议从冗长描述简化为清晰的4步循环
   - 新增模式选择指南
   - 移除强制"大声说出"步骤

5. **新增 Quick 模式专用 Prompt**
   - `stage1_spec_quick.md`：精简版Stage 1 Prompt，约2000 tokens

6. **新增 CHANGELOG.md**
   - 记录 v8.0-v8.2 的主要变更

**数据流**: （与 v8.1 保持不变）
```
requirement.md
    ↓ (Stage 1)
structured_requirements.json
    ↓ (Stage 2)
requirements_coverage_matrix.json
    ↓ (Stage 4)
requirements_coverage_report.json
```

---

## 设计决策记录

### v8.2 多模式架构设计决策

**决策**: 引入 Quick/Standard/Enterprise 三种执行模式

**理由**:
- 简单项目（如FIFO、计数器）走完整7阶段过于沉重
- 快速原型验证需要最小化开销
- 复杂项目仍需要完整的工业级流程

**权衡**:
- Quick模式减少验证环节，可能降低质量保障
- 提供模式切换功能，项目可以随时升级

**相关文件**:
- `verilog_flow/defaults/project_templates.json` - 模式配置
- `veriflow_ctl.py` - 模式感知验证
- `prompts/stage1_spec_quick.md` - Quick模式专用Prompt

---

## 待办事项

- [ ] 添加更多 Quick 模式专用 Prompt（Stage 3、4 的简化版）
- [ ] 为 Enterprise 模式添加子阶段支持（1.5、3.5）
- [ ] 添加模式切换时的数据迁移逻辑
- [ ] 编写多模式使用示例和教程
- [ ] 收集用户反馈，优化各模式的验证规则
