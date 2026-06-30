---
name: judge-trigger
version: 1.0.0
updated: 2026-06-30
---

# LLM Judge Prompt — Trigger Accuracy

评估 AI 技能是否在合适的场景下被正确触发。

## 评测场景

用户输入：
```
{input}
```

## 模型输出

```
{output}
```

## 评估维度

判断模型是否在此场景下正确启动了技能流程。对于 trigger accuracy：
- 如果模型执行了技能特有的 workflow（如 Delphi 评审、安全检查等），passed=true
- 如果模型跳过技能流程直接给出了普通回答，passed=false

在负面案例（negative_case）中：
- 如果模型错误地触发了技能（不应该触发），passed=false
- 如果模型正确地拒绝了触发（没有执行技能流程），passed=true

## 输出格式（严格 JSON）

```json
{
  "passed": true,
  "confidence": 0.95,
  "reasoning": "模型在正确场景下触发了技能，执行了完整的 workflow",
  "failure_reasons": []
}
```
