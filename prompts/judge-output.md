---
name: judge-output
version: 1.0.0
updated: 2026-06-30
---

# LLM Judge Prompt — Output Quality

评估 AI 技能输出内容的质量。

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

判断模型的输出是否：
1. 内容完整：覆盖了用户请求的所有方面
2. 结构清晰：使用了适当的标题、列表、代码块等 Markdown 格式
3. 建议可行：提出的建议具体、可操作，不是泛泛而谈
4. 理由充分：结论有明确的推理链支持

## 输出格式（严格 JSON）

```json
{
  "passed": true,
  "confidence": 0.85,
  "reasoning": "输出结构完整，建议具体可行，推理链清晰。但可以在安全性方面提供更多细节。",
  "failure_reasons": []
}
```
