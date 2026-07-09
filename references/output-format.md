# Output Format

报告输出包含 Markdown 和 JSON 两种格式。

## JSON 输出结构

```json
{
  "verdict": "PASS",
  "overall_score": 0.82,
  "metrics": {
    "l1_trigger_accuracy": 0.90,
    "l2_with_without_skill_delta": 0.25,
    "l3_step_adherence": 0.88,
    "l4_execution_stability": 0.93
  },
  "drift_analysis": {
    "drift_detected": false,
    "highest_severity": "none",
    "average_variance": 0.0,
    "model_pairs_compared": 1,
    "overall_verdict": "PASS"
  },
  "evaluation_coverage": {
    "total_evaluations": 207,
    "avg_pass_rate": 1.0,
    "assertion_breakdown": {
      "critical": {"passed": 40, "total": 40},
      "important": {"passed": 54, "total": 58},
      "normal": {"passed": 113, "total": 113}
    }
  },
  "improvement_suggestions": ["增加输出格式声明以提高 L3 得分"],
  "config_summary": {
    "models": "model-list",
    "max_concurrency": 5,
    "rate_limit_rpm": 60
  },
  "benchmark": {
    "timestamp": "ISO 8601 UTC",
    "total_requirements": 10,
    "total_acceptance_criteria": 66,
    "test_coverage": "描述"
  }
}
```

**Eval 断言检查**: `verdict`, `overall_score`, `metrics.l1_trigger_accuracy`, `metrics.l2_with_without_skill_delta`, `metrics.l3_step_adherence`, `metrics.l4_execution_stability`, `drift_analysis.highest_severity`, `evaluation_coverage.total_evaluations`, `config_summary.models`

## Scope

- **IN**: AI agent skill definitions (SKILL.md files) used by Claude Code, Codex, OpenCode, and compatible agents
- **IN**: Evaluation of skill effectiveness, reliability, security, and cost efficiency
- **Does NOT**: Execute arbitrary code from skills — all execution is sandboxed
- **Does NOT**: Modify or deploy skills — read-only evaluation only
- **Does NOT**: Require write access to skill files — works on copies
