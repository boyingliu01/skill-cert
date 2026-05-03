---
name: skill-cert
description: Evaluate and certify AI skills — auto-parse SKILL.md, generate tests, execute, and produce PASS/FAIL verdict with L1-L4 metrics and cross-model drift analysis
---

# Skill-Cert: AI Skill Evaluation Engine

skill-cert 接收任意 SKILL.md 文件，自动解析技能结构、生成评测用例、执行交叉验证、计算 L1-L4 指标、检测跨模型漂移，并生成标准化的 PASS/FAIL 判定报告。

## 核心原则

| 原则 | 说明 |
|------|------|
| **全自动评测** | 解析 → 生成 → 执行 → 评分 → 报告，无需人工介入 |
| **交叉验证** | with-skill vs without-skill 基线对比，量化技能的实际提升 |
| **多模型漂移** | 至少两个不同 provider 的模型，检测技能在不同模型下的一致性 |
| **零容忍** | Schema 不合法、覆盖率不足、漂移 high → 阻断或 FAIL |

## 评测模式

| 模式 | 触发 | 用途 |
|------|------|------|
| `single`（默认） | `skill-cert --skill <path>` | 单轮评测，验证基本功能 |
| `dialogue` | `skill-cert --skill <path> --mode dialogue --max-turns 10` | 多轮对话评测，模拟真实用户交互 |
| `replay` | `skill-cert --skill <path> --mode replay --session <file>` | 回归测试，使用历史会话数据 |

## 评测流程

### Phase 0: Skill 解析
- 读取 SKILL.md，提取语义结构（SkillSpec）：name、description、workflow_steps、anti_patterns、output_format、triggers
- 正则 + markdown-it-py AST 解析，fallback 到 LLM 辅助解析
- 8 维置信度评分：frontmatter(0.30) + workflow(0.25) + headings(0.15) + AP(0.10) + OF(0.08) + triggers(0.07) + examples(0.05) + bonus(0.05)
- Schema 验证：检查 Security Notes、Permissions（仅交互式技能）等必要章节

### Phase 1: 测试生成 + 自审循环
- 生成初始评测用例 → 审查质量 → 补充缺口 → 重新审查
- 循环直到覆盖率 >= 90%
- 保底：templates/minimum-evals.json

### Phase 2: 交叉验证执行
- with-skill 执行 vs without-skill 基线
- 确定性断言（contains、not_contains、regex、starts_with、json_valid）+ LLM-as-judge（温度=0）
- 安全扫描：19 种攻击模式，5 个类别（INJ/EXF/DCMD/CRD/OBF）
- 输出长度限制：100KB

### Phase 3: 渐进补充
- 分析薄弱区域，补充针对性测试
- 收敛条件：L2 delta >= 20% 或达到最大轮数

### Phase 4: L1-L4 指标计算
- L1 触发准确性：>= 90% 达标
- L2 输出增幅（with vs without skill）：>= 20% 达标
- L3 步骤遵循度：>= 85% 达标
- L4 执行稳定性（std <= 10%）：排除 LLM judge 的确定性断言

### Phase 5: 跨模型漂移检测
- 多模型执行同一 eval suite
- 方差阈值：none <= 0.10, low <= 0.20, moderate <= 0.35, high > 0.35
- none/low → 不影响判定，moderate → PASS_WITH_CAVEATS，high → FAIL

### Phase 6: 报告生成
- Markdown 报告 + JSON 结果 + 评测缓存
- 包含：执行摘要、L1-L4 指标、漂移分析、评测覆盖、改进建议、配置信息、基准信息

## Output Format

报告输出包含 Markdown 和 JSON 两种格式。

### JSON 输出结构

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

## Verdict 判定

| Verdict | 条件 |
|---------|------|
| PASS | L1>=90%, L2>=20%, L3>=85%, L4 std<=10%, drift none/low |
| PASS_WITH_CAVEATS | 核心指标通过，但 drift moderate |
| FAIL | 任一核心指标不达标，或 drift high，或覆盖率 < 70% |

## Triggers

- `skill-cert --skill`
- `run skill certification`
- `evaluate this skill`
- `certify SKILL.md`
- `/skill-cert`
- `评测这个技能`
- `验证 SKILL.md`

## Anti-Patterns

| 错误 | 正确 |
|------|------|
| 跳过 Phase 1 自审循环直接跑评测 | 必须完成 generate → review → gap-fill 循环，覆盖率 >= 90% |
| 只跑 with-skill 不跑 without-skill 基线 | 必须同时跑 with+without 才能计算 L2 delta |
| 忽略 L4 稳定性只关注 L2 delta | L4 std > 10% 需要排查，不能只看 L2 增幅 |
| 漂移检测 high 仍给 PASS | drift high → 直接 FAIL，不可降级 |
| 修改 Phase 2 执行后的 eval 用例 | eval 用例在执行前锁定，Phase 2 后不可修改（完整性规则） |
| SKILL.md 解析 confidence < 0.6 仍继续 | 低置信度时应该降级处理，标记为 PASS_WITH_CAVEATS |
| 覆盖率 < 70% 仍然执行评测 | 覆盖率不足应阻断，无法生成有效测试 |
| 单模型评测 | 至少需要两个不同 provider 的模型进行漂移检测 |
| temp > 0 用于 LLM-as-judge | LLM judge 必须使用 temp=0 确保确定性 |
| `as any`/`@ts-ignore` 压制类型错误 | 类型安全是 skill 质量的一部分，不可绕过 |

## Red Flags

- SKILL.md 解析 confidence < 0.6 → 结构模糊，评测结果不可信
- 覆盖率 < 70% → 阻断，无法生成有效测试
- 所有模型不可用 → 优雅终止，输出部分结果
- 漂移 high → 技能在不同模型下行为不一致，无法发布

## 配置

### 环境变量

| 变量 | 说明 |
|------|------|
| `SKILL_CERT_MODELS` | 模型配置：`name=url,key[,fallback]\|name2=url,key` |
| `SKILL_CERT_MAX_CONCURRENCY` | 最大并发数（默认 5） |
| `SKILL_CERT_RATE_LIMIT_RPM` | 速率限制 RPM（默认 60） |

### 配置文件

`~/.skill-cert/models.yaml`:
```yaml
models:
  - model_name: "qwen3.6-plus"
    base_url: "https://api.example.com/v1"
    api_key: "$API_KEY"
    fallback_model: "qwen3-coder-plus"
```

## 用法

```bash
# 单轮模式（默认）
skill-cert --skill /path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/

# 对话模式
skill-cert --skill /path/to/SKILL.md --mode dialogue --max-turns 10

# 重放模式
skill-cert --skill /path/to/SKILL.md --mode replay --session session.jsonl
```
