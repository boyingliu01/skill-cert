---
name: skill-cert
description: Skill evaluation engine for AI skills (SKILL.md files). Parses skill definitions, generates test cases, runs with/without-skill comparisons, and produces L1-L8 metrics with PASS/FAIL verdicts. Invoked via /skill-cert or explicit user request. Do NOT trigger for: code reviews, sprint progress checks, build verification, project management, or any context not explicitly requesting skill evaluation or certification.
---

# Skill-Cert: AI Skill Evaluation Engine

skill-cert 接收任意 SKILL.md 文件，自动解析技能结构、生成评测用例、执行交叉验证、计算 L1-L4 指标、检测跨模型漂移，并生成标准化的 PASS/FAIL 判定报告。

## Quick Start

```bash
skill-cert --skill path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/
```

## Reference Index

Core workflows and conventions are split across focused reference files:

| Reference | Content |
|-----------|---------|
| [references/setup.md](references/setup.md) | Configuration check logic, env vars, config file |
| [references/evaluation-flow.md](references/evaluation-flow.md) | Phase 0–6 pipeline details, core principles, modes |
| [references/metrics.md](references/metrics.md) | L1–L8 definitions, verdict logic, triggers |
| [references/output-format.md](references/output-format.md) | JSON output structure, scope |
| [references/anti-patterns.md](references/anti-patterns.md) | Anti-patterns table, Red Flags |
| [references/examples.md](references/examples.md) | Usage examples and command reference |
| [tools.md](tools.md) | Allowed tools and dangerous tool restrictions |

## Key Constraints

- **全自动评测**: 解析 → 生成 → 执行 → 评分 → 报告，无需人工介入
- **交叉验证**: with-skill vs without-skill 基线对比
- **多模型漂移**: 至少两个不同 provider 的模型
- **零容忍**: Schema 不合法、覆盖率不足、漂移 high → 阻断或 FAIL
- **Coverage ≥ 90%**: Phase 1 自审循环硬性指标
- **LLM-as-Judge temp=0**: 确保判定确定性
- **Public API**: `parse_skill_md(path, strict_schema=False)` unchanged
