# L1-L8 Metrics & Verdict

## Metrics Overview

| Level | Metric | Threshold |
|-------|--------|-----------|
| L1 | Trigger Accuracy | ≥ 90% |
| L2 | With/Without Skill Normalized Gain | ≥ 20% |
| L3 | Step Adherence (weighted: 0.5×step_coverage + 0.3×tool_call_accuracy + 0.2×turn_relevance) | ≥ 85% |
| L4 | Execution Stability (std dev) | ≤ 10% |
| L5 | Step Efficiency (EnvelopeChecker) | passed=1.0, 1violation=0.7, 2+=0.3 |
| L6 | Trajectory Quality | dialogue mode only |
| L7 | Cost Efficiency | token→$ via adapters/pricing.py |
| L8 | Latency (P50/P95/P99) | — |

## Verdict 判定

| Verdict | 条件 |
|---------|------|
| PASS | L1>=90%, L2>=20%, L3>=85%, L4 std<=10%, drift none/low |
| PASS_WITH_CAVEATS | 核心指标通过，但 drift moderate |
| FAIL | 任一核心指标不达标，或 drift high，或覆盖率 < 70% |

## Triggers

### 应该触发 (SHOULD trigger)

- `skill-cert setup`
- `skill-cert --skill`
- `run skill certification`
- `evaluate this skill`
- `/skill-cert`
- `评测这个技能`

### 不应触发 (MUST NOT trigger)

以下命令/输入**不应触发** skill-cert 技能，即使看起来相关。如果遇到这些输入，必须当作一般问题处理，不要加载/执行 skill-cert 流程：

- `skill-cert --help` — 仅查询帮助信息，不是评测请求
- `skill-cert --version` — 仅查询版本，不是评测请求
- `skill-cert-setup` — 非标准命令（不含空格、连字符差异）
- `certify SKILL.md` — 语义相似但不精确匹配；仅当用户明确使用上述"应该触发"列表中的短语时才触发
- `验证 SKILL.md` — 语义相似但过于宽泛；仅当用户明确使用上述"应该触发"列表中的短语时才触发
- 任何包含 `skill-cert` 但后缀为非评测子命令的输入（如 `skill-cert help`, `skill-cert version`, `skill-cert config`）

**触发匹配规则**：
1. 优先精确匹配"应该触发"列表中的短语（忽略大小写、引号、前后空格）
2. 如果输入包含 `skill-cert` 但不在"应该触发"列表中，**不要触发**
3. 中文触发短语（`评测这个技能`）必须精确匹配，不接受部分匹配或语义近似
4. 如果输入是纯咨询类问题（以 `?` 结尾、包含 `what`/`how`/`explain`/`为什么`/`怎么`/`是什么`），不要触发 skill-cert 评测流程，而是提供一般性解答
