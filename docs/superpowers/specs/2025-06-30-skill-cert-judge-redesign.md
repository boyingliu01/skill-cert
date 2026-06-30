# skill-cert 断言系统重构设计 v2

> Round 1 Delphi 反馈已合并：规则引擎替代 LLM 分类、per-eval-case 路由、具体 judge 稳定性策略、修正成本估算、向后兼容方案

## 问题

skill-cert 当前用确定性断言（`contains`/`regex`/`json_valid`）评测所有技能，但对输出为自然语言 Markdown 的 review/creative 类技能（如 delphi-review）完全不适用。L1 Trigger Accuracy = 0%，但模型实际输出质量正常。

## 核心思路

**翻转评测优先级**：LLM-as-Judge 从「补充」提升为「主干」，确定性断言降为「快速筛选」。testgen 和 Grader 两端都需改造。

---

## 1. 两层评估体系（v1 先不做 Layer 3 batch）

```
Layer 1: 快速筛选（确定性断言）
  - trigger 类 eval：检查模型是否在正确场景触发技能
  - 格式约束类 eval：JSON 有效、结构匹配
  - 安全类 eval：包含/不包含特定内容（not_contains）
  → 轻量、快速、零成本、可回归

Layer 2: 语义评估（LLM-as-Judge per eval case）
  - workflow 步骤执行质量
  - output 质量（review 类、creative 类）
  - anti-pattern 遵守情况
  → 对 Layer 1 无法覆盖的 eval case 调用 LLM 评估
  → v1 不做 batch Layer 3，避免成本翻倍且触发条件模糊
```

## 2. 评估粒度：混合粒度（per-eval-case 路由）

路由策略是 **per-eval-case**，不是 per-skill。同一个 skill 可以同时有 trigger/确定性 eval 和 workflow/LLM-judge eval。

| Eval Category | 断言策略 | 理由 |
|---|---|---|
| trigger | deterministic | 触发判定是明确的二元问题 |
| workflow_step | llm_judge | 需要语义理解执行质量 |
| anti_pattern | mixed | 确定性过滤 + LLM judge 确认 |
| output_format | 看 format 类型 | JSON/结构化→deterministic，Markdown/文本→llm_judge |
| boundary | mixed | 边界场景既需要格式检查也需要语义判断 |

**负面案例（negative_case）**：anti_pattern 和 boundary 类的负面 eval 走 mixed 路径——先用确定性断言过滤不可触发的场景，再用 LLM judge 确认模型没有错误触发技能。

## 3. testgen 改造：基于规则的策略分配器

**不需要 LLM 调用**。根据 SkillSpec 的结构化字段做规则判断：

```python
# 规则引擎伪代码（在 EvalGenerator 内联实现，不需要独立 Classifier 类）
def _assign_strategy(category: str, output_format_fields: list[str]) -> str:
    if category == "trigger":
        return "deterministic"
    if category == "workflow_step":
        return "llm_judge"
    if category == "anti_pattern":
        return "mixed"
    if category == "output_format":
        # 分析 output_format_fields 判断输出类型
        has_json = any("json" in f.lower() or "code" in f.lower() for f in output_format_fields)
        return "deterministic" if has_json else "llm_judge"
    if category == "boundary":
        return "mixed"
    return "deterministic"  # 默认回退
```

默认 `deterministic` 确保旧 behavior 作为 safe fallback。

## 4. Grader 改造：翻转评估优先级

```
当前: grade_output() → 确定性断言 → 如失败 → LLM judge 补充

新: grade_output() →
  // Guard: 对 None/缺失的 assertion_strategy 回退到 deterministic
  strategy = getattr(eval_case, 'assertion_strategy', None) or 'deterministic'
  
  if strategy == "deterministic":
    → 确定性断言（现有 _evaluate_assertions 逻辑，完全不变）
  elif strategy == "llm_judge":
    → LLM judge 主干（复用现有 _execute_llm_judge，prompt 按 judge_dimensions 重构）
      + 可选确定性快速检查（仅做 not_contains 安全检查）
  elif strategy == "mixed":
    → 确定性断言（Layer 1）→ 如果 pass → LLM judge（Layer 2）
    → 如果确定性断言失败 → 标记为 FAIL，不调 LLM judge
```

修复 C2：`EvalCase` 新增 `assertion_strategy` 字段（不是 `EvalAssertion` 上），清除与 `assertion.type` 的语义冲突。`assertion_strategy` 是 eval case 级别的路由决策字段。

## 5. 数据模型变更

**EvalCase 新增字段**（eval case 级别，不是 per-assertion）：
```python
class EvalCase(BaseModel):
    # ... 现有字段保持不变 ...
    assertion_strategy: str = "deterministic"  # deterministic | llm_judge | mixed
    judge_prompt_template: str | None = None   # llm_judge 时的 prompt 模板变量
    judge_dimensions: list[str] | None = None  # trigger_accuracy|workflow_quality|output_quality
```

**向后兼容**：`assertion_strategy` 默认值 `"deterministic"`，旧 eval cache 反序列化时自动填充此默认值，所有旧 eval 走原来的确定性路径，行为不退化。

EvalAssertion 不变，仅 EvalCase 新增字段。

## 6. LLM Judge 稳定性策略

**策略**：majority voting with tie-break。

```
for each llm_judge eval case:
  run N=3 次 judge 调用 (temp=0)
  取多数投票结果作为最终分数
  如果 3 次结果全不一致 → 取中位数
  judge 标准差计入 L4 stability 指标
```

- N=3 作为默认，可通过 `--judge-samples N` 配置
- Position debias：3 次 judge 中第 2 次对调选项顺序
- 成本公式：`cost_per_eval = N × (judge_tokens_input × input_price + judge_tokens_output × output_price)`

**指标一致性**：LLM judge 给出的维度分数（trigger_accuracy/workflow_quality/output_quality）映射到 L1/L3/L2 指标时，直接替代原有计算值。Report 中同时展示两者值方便交叉验证，但 verdict 仅使用 LLM judge 分数。

## 7. LLM Judge 成本估算（按模型分档）

| 模型 | Input $/1M tokens | Output $/1M tokens | judge 调用成本 | 26-eval 评测总成本 |
|------|-------------------|--------------------|------------------|----------------------|
| GPT-4o-mini | $0.15 | $0.60 | ~$0.00005 | ~$0.02 |
| GPT-4o | $2.50 | $10.00 | ~$0.0009 | ~$0.31 |
| DeepSeek-v2 | $0.14 | $0.28 | ~$0.00003 | ~$0.01 |

> 按 500 input + 100 output tokens/judge_call × 3 judges × 2 phases(with/without) = 9 judge calls/eval_case

## 8. 实现路径（ralph-loop，修正 REQ 划分）

| REQ | 内容 | 文件 | 测试策略 |
|-----|------|------|---------|
| REQ-1 | EvalCase 数据模型扩展（新增 3 个字段，default=deterministic） | engine/grader.py | 新增 ~15 tests: 序列化/反序列化/default 值/旧 cache 兼容 |
| REQ-2 | testgen：基于规则引擎的策略分配（`_assign_strategy()`） | engine/testgen.py | 新增 ~20 tests: 各 category 的策略分配正确性 |
| REQ-3 | Grader 改造：翻转 grade_output 路由逻辑 | engine/grader.py | 修改 ~60 tests: 路由分支覆盖；新增 ~20 tests: llm_judge/mixed 新路径 |
| REQ-4 | LLM judge prompt 模板 + majority voting 稳定性 | engine/grader.py, prompts/ | 新增 ~15 tests: judge prompt 构建、voting 逻辑 |
| REQ-5 | metrics/reporter 适配新结构 | engine/metrics.py, engine/reporters/ | 修改 ~15 tests: 维度字段映射 |
| REQ-6 | CLI 参数 `--judge-samples` + `--no-llm-judge` | skill_cert/cli/ | 新增 ~5 tests: CLI arg 解析 |
| REQ-7 | 集成测试 + 回归验证 | tests/ | 新增 ~10 integration tests；所有 1400 tests 回归通过 |

**测试统计**：预计新增 ~85 个测试，修改 ~75 个现有测试，保持 1400 test baseline 不退化。

## 9. 风险评估（修正）

- **LLM judge 稳定性**：3-shot majority voting 降低单次随机性 → L4 stability 包含 judge 方差
- **API 成本**：按模型分档（见第 7 节），GPT-4o-mini 评测 ~$0.02，DeepSeek ~$0.01。用户可通过 `--no-llm-judge` 跳过
- **回归保护**：默认 `assertion_strategy=deterministic` → 旧 eval cache 行为完全不变；Grader 路由 guard clause 处理 None 策略
- **向后兼容**：EvalCase 新字段全部有默认值；旧 cache 反序列化自动走 deterministic 路径
