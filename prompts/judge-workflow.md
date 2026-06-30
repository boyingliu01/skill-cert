---
name: judge-workflow
version: 1.0.0
updated: 2026-06-30
---

# LLM Judge Prompt — Workflow Quality

评估 AI 技能是否严格遵循了定义的工作流程步骤。

## 评测场景

用户输入：
```
{input}
```

## 模型输出

```
{output}
```

## 工作流程步骤（from SKILL.md）

{workflow_steps}

## 评估维度

判断模型的输出是否：
1. 按照技能定义的工作流程步骤顺序执行
2. 每个步骤的执行质量是否充分（不是表面提及，而是实质性执行）
3. 是否跳过了关键步骤

## 输出格式（严格 JSON）

```json
{
  "passed": true,
  "confidence": 0.90,
  "reasoning": "模型完成了 Round 1 独立评审 → Round 2 交换意见 → 共识达成，所有步骤顺序正确",
  "failure_reasons": []
}
```
