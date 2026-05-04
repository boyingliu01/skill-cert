# Skill-Cert 评估维度审计报告

**日期**: 2026-05-04
**范围**: 全维度覆盖分析 — 已实现 / 半成品 / 缺失

---

## 一、当前已覆盖的评估维度

| 维度 | 状态 | 实现文件 | 说明 |
|------|------|---------|------|
| **L1 触发准确性** | ✅ 完整 | `engine/metrics.py` | eval_category='trigger' 通过率 |
| **L2 技能有效性** | ✅ 完整 | `engine/metrics.py` | with-skill vs without-skill delta |
| **L3 步骤遵循度** | ✅ 完整 | `engine/metrics.py` | workflow steps 被 passing evals 覆盖比例 |
| **L4 执行稳定性** | ✅ 完整 | `engine/metrics.py` | 确定性断言 pass rate 的 std dev |
| **L5 步骤效率** | ⚠️ 半成品 | `engine/metrics.py` | 需要 trace 数据才激活，否则返回 None |
| **L6 轨迹质量** | ⚠️ 半成品 | `engine/metrics.py` | 仅 dialogue 模式激活，其他模式返回 None |
| **安全性** | ✅ 完整 | `engine/security_probes.py` | 19 种攻击模式，5 大类 (INJ/EXF/DCMD/CRD/OBF) |
| **跨模型漂移** | ✅ 完整 | `engine/drift.py` | 4 级严重度 (none/low/moderate/high) |
| **运行包络线** | ✅ 存在 | `engine/envelope.py` | steps/tokens/timeout/tool_calls 上限检查 |
| **Token 追踪** | ✅ 存在 | `engine/runner.py` | 每次 eval 记录 tokens_used + token_breakdown |

---

## 二、缺失维度分析

### 🔴 2.1 成本评估（高优先级）

**现状**: runner 记录 token 数量，但无成本维度评估体系。

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **$/eval 成本计算** | 无 pricing 接入，纯 token 数无法换算成本 | 增加 `adapters/pricing.py`，维护各模型 per-M-token 价目表 |
| **with/without skill 成本对比** | 不知道 skill 带来多少额外开销 | L7 指标: `cost_delta = (with_cost - without_cost) / without_cost` |
| **成本效率 (ROI)** | 质量提升 vs 额外花费的比值 | `cost_efficiency = l2_delta / cost_delta`，阈值告警 |
| **跨模型成本漂移** | 同一 skill 在不同模型上的成本差异 | 报告中增加 `cost_drift` 分析章节 |
| **成本报告** | 报告无 cost breakdown 字段 | 报告增加 per-eval cost、total cost、avg cost per assertion |
| **成本阈值/告警** | 无 single-eval cap 或 per-skill budget | `EnvelopeChecker` 增加 `cost_budget` 参数 |

**建议新增 L7 指标**:
- `cost_per_eval`: 平均每次评测成本 ($)
- `cost_delta_pct`: with-skill 相对 without-skill 成本增幅 (%)
- `cost_efficiency`: 质量提升 / 成本增幅 (越高越好)
- `cost_verdict`: PASS / CAVEATS / FAIL 基于成本阈值

---

### 🔴 2.2 延迟 / 性能评估（高优先级）

**现状**: runner 记录 `execution_time`，但未作为评估指标。

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **P50/P95 延迟** | 只看 average 不够，需要分位数 | 新增 `LatencyTracker` 类，计算 P50/P95/P99 |
| **TTFT (首 Token 时间)** | 对流式请求重要，当前无此指标 | adapter 层添加 streaming 支持后追踪 TTFT |
| **with/without skill 延迟对比** | skill 可能显著增加处理时间 | L8 指标: `latency_overhead = with_latency / without_latency` |
| **慢请求告警** | 无超时前告警机制 | `EnvelopeChecker` 已有 timeout_s 但无分级 |
| **延迟稳定性** | 类似 L4 但针对时间 | `latency_std / latency_mean` (变异系数) |

---

### 🟡 2.3 可靠性评估（中优先级）

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **API error rate** | 知道有重试，但没有统计错误率 | runner 收集失败率 + 重试率 |
| **Graceful degradation 验证** | REQ-008 要求优雅降级，但无对应 eval | 增加测试 case: 模拟模型不可用场景 |
| **Fallback 有效性** | fallback 模型返回质量 vs 主模型 | 比较 fallback 与主模型的 pass rate 差异 |
| **部分结果可用性** | 当某模型不可用时，其他模型结果是否完整 | runner 中已有 partial results 但无评估 |

---

### 🟡 2.4 可扩展性评估（中优先级）

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **并发压力测试** | max_concurrency=5 时没问题，50 呢？ | 新增 `stress_test` 模块: 100 evals 并发 |
| **Rate limiter 公平性** | 多 eval 竞争时是否饥饿 | 验证所有 eval 在 timeout 内都获得执行机会 |
| **内存占用** | eval 缓存是否导致 OOM | 追踪峰值内存 + eval 缓存大小 |

---

### 🟡 2.5 技能组合冲突评估（中优先级）

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **Trigger 歧义** | 两个 skill 都被同一 input 触发 | 新增 `multi-skill` 模式: 注入多个 SKILL.md |
| **Prompt 干扰** | 多个 skill 的 instruction 互相影响 | 比较有/无其他 skill 时的 pass rate |
| **Token 预算叠加** | 多个 skill 累加是否超出 budget | 多 skill 模式的 envelope 聚合检查 |

---

### 🟢 2.6 SKILL.md 可维护性评估（低优先级）

| 缺失项 | 说明 | 建议方案 |
|--------|------|---------|
| **可读性评分** | 结构复杂度、层次深度、行长度 | analyzer 扩展: `readability_score` |
| **过时内容检测** | 引用的命令/依赖是否已过期 | testgen 扩展: 版本号校验 |
| **结构完整性** | 是否缺少必要章节 | 已有 schema validation，可增加评分 |

---

## 三、实现建议优先级路线图

### Phase 1 — 成本评估（当前迭代）
1. `adapters/pricing.py` — 模型价目表 + token→$ 转换
2. `engine/metrics.py` — L7 `cost_efficiency` 计算
3. `engine/runner.py` — 增强 cost 追踪
4. `engine/envelope.py` — 增加 `cost_budget` 参数
5. `engine/reporter.py` — 报告增加 Cost Analysis 章节
6. `specs/specification.yaml` — 新增 REQ-011 成本评估

### Phase 2 — 延迟 / 性能评估
1. `engine/latency.py` — P50/P95/P99 + TTFT 追踪
2. `engine/metrics.py` — L8 `latency_overhead` 计算
3. `engine/reporter.py` — 报告增加 Performance 章节

### Phase 3 — 可靠性 + 可扩展性
1. runner error rate + retry statistics
2. graceful degradation eval cases
3. stress test 模块

### Phase 4 — 技能组合 + 可维护性
1. multi-skill 模式
2. readability scoring
3. structure quality report
