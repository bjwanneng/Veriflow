---
name: verilog-flow-skill
description: Industrial-grade Verilog design pipeline with script-controlled orchestration and LLM-executed stages. Use when working with Verilog/RTL design, FPGA/ASIC development, hardware verification, or when you mention Verilog code generation, testbench generation, or hardware design workflows.
license: MIT
metadata:
  author: VeriFlow Team
  version: "8.2.0"
  category: hardware-design
---

# VeriFlow-Agent 8.2 — 多模式设计流程

架构: **脚本做门控，LLM做执行**

---

## 快速开始

```bash
# 1. 确保项目目录有 requirement.md
# 2. 启动流程
python veriflow_ctl.py next -d ./my_project
```

---

## 三种执行模式

| 模式 | 阶段 | 适用场景 | 验证深度 |
|------|------|----------|----------|
| **Quick** | 0→1→3→4→6 | 简单模块、原型验证、快速迭代 | 最小验证 |
| **Standard** | 0→1→2→3→4→5→6 | 一般项目、推荐默认 | 完整验证 |
| **Enterprise** | 0→1→1.5→2→3→3.5→4→5→6 | 关键项目、工业级 | 严格验证 |

### 模式选择指南

- **Quick 模式**: 计数器、简单状态机、小FIFO、学习/原型
- **Standard 模式**: 接口控制器、算法模块、一般IP核
- **Enterprise 模式**: 复杂SoC、关键路径、需要严格质量门控

---

## 执行协议 (简化版)

```
循环执行直到所有阶段完成:

  步骤1: 获取Prompt
    └─▶ python veriflow_ctl.py next -d $PROJECT_DIR

  步骤2: 执行任务
    └─▶ 读取Prompt，完成所有子任务

  步骤3: 验证
    └─▶ python veriflow_ctl.py validate -d $PROJECT_DIR $STAGE

  步骤4: 标记完成
    └─▶ python veriflow_ctl.py complete -d $PROJECT_DIR $STAGE
```

### 重要规则

1. **不要跳过验证** - 必须通过 validate 才能 complete
2. **不要手动创建标记文件** - 只使用 complete 命令
3. **一次一个阶段** - 完成当前阶段才能开始下一个

---

## 各阶段说明

| 阶段 | 名称 | 输出 | Quick | Standard | Enterprise |
|------|------|------|-------|----------|------------|
| 0 | 项目初始化 | 目录结构、配置 | ✅ | ✅ | ✅ |
| 1 | 微架构规格 | spec.json | ✅(简化) | ✅ | ✅(含评审) |
| 1.5 | 架构评审 | 评审报告 | ❌ | ❌ | ✅ |
| 2 | 虚拟时序建模 | YAML、Golden Trace | ❌ | ✅ | ✅ |
| 3 | RTL代码生成 | .v 文件、testbench | ✅ | ✅ | ✅(含评审) |
| 3.5 | 代码评审 | 评审报告 | ❌ | ❌ | ✅ |
| 4 | 仿真验证 | 仿真日志、波形 | ✅(简化) | ✅ | ✅ |
| 5 | 综合分析 | 综合报告 | ❌ | ✅ | ✅ |
| 6 | 项目收尾 | 最终报告 | ✅ | ✅ | ✅ |

---

## Prompt 设计

### 分层 Prompt 架构

```
┌─────────────────────────────────────┐
│  Core Prompt (核心, 200 tokens)     │
│  - 任务一句话描述                     │
│  - 输入/输出格式                      │
│  - 3-5条关键约束                      │
├─────────────────────────────────────┤
│  Context (上下文, 按需加载)          │
│  - 编码风格 (Quick模式可不加载)       │
│  - 设计规格                           │
├─────────────────────────────────────┤
│  Examples (示例, 可选)               │
│  - 复杂任务提供示例                   │
└─────────────────────────────────────┘
```

### 模式对应的 Prompt 长度

| 模式 | 目标长度 | 示例数量 | 模板数量 |
|------|----------|----------|----------|
| Quick | < 2000 tokens | 0 | 0 |
| Standard | 2000-4000 tokens | 1-2 | 核心模板 |
| Enterprise | 4000-8000 tokens | 2-3 | 完整模板+最佳实践 |

---

## 工具命令参考

```bash
# 查看项目状态
python veriflow_ctl.py status -d ./my_project

# 获取下一阶段Prompt
python veriflow_ctl.py next -d ./my_project

# 验证阶段输出
python veriflow_ctl.py validate -d ./my_project 3

# 标记阶段完成
python veriflow_ctl.py complete -d ./my_project 3

# 回滚到指定阶段
python veriflow_ctl.py rollback -d ./my_project 1

# 查看阶段详情
python veriflow_ctl.py info -d ./my_project 2
```

---

## 项目配置示例

```json
{
  "project": "my_design",
  "mode": "quick",
  "target_frequency_mhz": 300,
  "testbench_depth": "minimal",
  "features": {
    "cocotb": false,
    "timing_contracts": false,
    "requirements_matrix": false
  },
  "validation_level": "minimal",
  "confirm_after_validate": false,
  "coding_style": {
    "reset_type": "async_active_low",
    "reset_signal": "rst_n"
  }
}
```

---

## 更新日志

### v8.2.0 (2026-03-21)
- 引入三种执行模式：Quick / Standard / Enterprise
- 简化执行协议，减少强制步骤
- 分层Prompt设计，按模式动态加载
- 按需验证级别，避免过度验证
- 优化项目配置结构

---

**文档版本**: 8.2.0
**兼容控制器版本**: >= 8.2.0
