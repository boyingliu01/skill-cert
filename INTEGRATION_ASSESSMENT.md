# skill-cert 集成评估：精简 vs 保留 vs 集成

> 基于行业调研 + 技术评估，对每个模块进行"保留自建 / 替换为集成 / 删除"决策分析

---

## 一、评估框架

### 决策原则

| 决策 | 适用场景 |
|------|---------|
| **保留自建** | 有独特差异化价值、不可替代、或集成成本远超维护成本 |
| **替换为集成** | 已有成熟开源方案、API 稳定、能力对等且更完善 |
| **模拟实现** | 初期保留最小实现，长期标记为可替换 |
| **删除** | 功能冗余、价值不明、或可通过其他模块覆盖 |

### 评估维度

1. **独特性**：该能力在业界是否有等价开源替代？
2. **复杂度**：自建维护成本 vs 集成改造成本？
3. **核心度**：是否是 skill-cert 的差异化竞争力？
4. **成熟度**：替代方案是否足够稳定/API 是否固化？

---

## 二、模块逐项评估

### 2.1 核心引擎层（保留——这些是 skill-cert 的"灵魂"）

#### ✅ analyzer.py — 保留自建
- **功能**：SKILL.md → SkillSpec（regex + AST + LLM fallback）
- **为什么保留**：SKILL.md 格式是 skill-cert 的核心假设，没有第三方工具专门解析这个格式。自定义 parser + LLM fallback 的混合策略是独特设计。
- **简化方向**：无

#### ✅ testgen.py — 保留自建（需修复）
- **功能**：自动生成评测用例（generate→review→gap-fill loop）
- **为什么保留**：测试生成必须深度理解 SkillSpec 结构。Promptfoo/DeepEval 的测试生成是通用的，不理解 SKILL.md 语义。
- **简化方向**：重写 prompt（修复断言质量问题），增加元数据关键词黑名单

#### ✅ runner.py — 保留自建
- **功能**：with/without skill 执行、并发、率限制、deadline
- **为什么保留**：with/without 对比框架是 skill-cert 的唯一架构决策，与 LLM adapter 紧密耦合
- **简化方向**：可考虑用 DeepEval 的 `TestResult` 包装单次执行结果（但 runner 本身必须保留）

#### ✅ metrics.py — 保留自建
- **功能**：L1-L8 指标计算
- **为什么保留**：L1-L8 是 skill-cert 最独特的差异化资产。没有任何第三方工具提供了等价的 8 维结构化指标体系
- **简化方向**：L4 可增加 `pass@k`/`pass^k` 计算（不替换现有逻辑）

#### ✅ grader.py — 保留自建（但 LLM judge 可委托给 DeepEval）
- **功能**：确定性断言 + LLM-as-judge
- **为什么保留**：确定性断言（contains/not_contains/regex/starts_with/json_valid）非常简单，自建成本极低。位置去偏（`_debias_position`）是差异化实现。
- **简化方向**：LLM judge 的 position debiasing 可参考 DeepEval 的 G-Eval（不替换，但可学习）

#### ✅ reporter.py → 保留自建
- **功能**：Markdown + JSON 报告生成
- **为什么保留**：报告格式是 skill-cert 的输出界面，自定义格式不可替代
- **简化方向**：无

### 2.2 安全与分析层（部分可集成）

#### ⚠️ security_probes.py → 替换为 Promptfoo/Giskard 集成
- **功能**：80 正则模式 x 6 类别安全扫描
- **为什么可替换**：
  - Promptfoo 已有 40+ red-teaming 插件，比 80 个静态正则更全面
  - Giskard 的 red-teaming 支持 prompt injection/harmful content/stereotypes/misinformation
  - skill-cert 的 80 个正则模式是简单字符串匹配，不如 Promptfoo 的 LLM-driven 探针
- **集成方案**：Giskard Python API（首选，Python-native 无 Node.js 依赖）或 Promptfoo CLI（备选）
- **推荐**：分层策略——(a) 80 静态探针始终开启（零外部依赖，~500ms 扫描），(b) 可选的 Giskard/Promptfoo 深度扫描通过 `--deep-security` flag 启用

#### ⚠️ drift.py → 保留自建
- **功能**：跨模型漂移检测
- **为什么保留**：这是 skill-cert 的独特能力（唯一有此功能）。Drift Thresholds 定义与 Verdict 逻辑深度耦合
- **简化方向**：无

#### ✅ envelope.py → 保留自建
- **功能**：操作包络检查（steps/tokens/timeout/tool_calls）
- **为什么保留**：只有 56 行，逻辑极简单，集成无意义
- **简化方向**：无

#### ⚠️ calibration.py → 框架保留，数据集成
- **功能**：Cohen's Kappa + FPR/FNR 黄金校准
- **为什么保留**：校准逻辑与 skill-cert 的 Verdict 逻辑深度耦合
- **简化方向**：**数据层面**—Anthropic 建议"10-20% 人类标注黄金集"，这部分不来自代码集成，而是流程改进

#### ⚠️ multi_skill.py → 保留自建
- **功能**：多技能冲突检测（trigger overlap/contamination/token overflow）
- **为什么保留**：高度定制化的分析，没有第三方工具专门做这个
- **简化方向**：无

#### ⚠️ skills_bench.py → 保留自建
- **功能**：多技能认知过载检测（sweet spot analysis）
- **为什么保留**：与 multi_skill.py 配套的独特分析方法
- **简化方向**：无

### 2.3 基础设施层（优先集成）

#### 🔄 adapters/（anthropic_compat/openai_compat/factory）→ 替换为 OpenAI SDK + LangChain/LiteLLM
- **功能**：LLM provider adapter 统一接口
- **为什么可替换**：
  - LiteLLM 支持 100+ 模型统一接口（`litellm.completion()`），完全覆盖当前 6 provider
  - OpenAI SDK 本身已支持兼容 endpoint（base_url 配置）
  - 当前的 AnthropicCompatAdapter 和 OpenAICompatAdapter 总共约 600 行，维护成本不高但非核心价值
- **集成方案**：
  - 方案 A（轻量）：保留当前 adapter，因为只有 600 行且无外部依赖
  - 方案 B（长期）：切换到 LiteLLM 统一接口（减少 provider 适配代码）
- **推荐**：保留当前实现（轻量且稳定），长远标记为 LiteLLM 候选

#### 🔄 pricing.py → 替换为 LiteLLM cost tracker
- **功能**：17 模型 x 6 provider 的定价表
- **为什么可替换**：LiteLLM 内置自动 cost tracking（`litellm.cost_per_token()`），覆盖 100+ 模型
- **集成方案**：如果切换到 LiteLLM adapter，定价表自动免费获得
- **推荐**：如果保留当前 adapter，pricing.py 也保留（只有 73 行）

#### 🔄 token_ledger.py → 可委托 LiteLLM callback
- **功能**：Token 使用跟踪
- **为什么可替换**：LiteLLM 的 `success_callback` 和 `failure_callback` 自动追踪所有 token
- **推荐**：保留当前设计（它使用 ExecutionTrace 作为真相源，设计良好且独立）

#### 🔄 observability.py → 替换为 OpenTelemetry + Langfuse
- **功能**：EventBus + TraceExporter + SessionTelemetry（436 行）
- **为什么可替换**：
  - Langfuse 是行业标准的 LLM observability 平台（open-source）
  - OpenTelemetry 的 GenAI instrumentation 已标准化
  - 当前自建 EventBus 需要独立维护
- **集成方案**：用 Langfuse SDK 替换 self-built EventBus，保留 SessionTelemetry 作为 facade
- **推荐**：优先集成（436 行可简化到 50 行 facade）

#### 🔄 trace_models.py → 保留（Pydantic 数据模型）
- **功能**：ExecutionTrace、TokenAccounting、TraceEvent
- **为什么保留**：这些 Pydantic 模型是内部契约，即使 observability 委托给 Langfuse，数据模型仍需保留作为内部表示
- **简化方向**：无

### 2.4 增强功能层（价值评估）

#### ⚠️ adversarial.py → 用 Promptfoo redteam 替代
- **功能**：弱点分析 + 对抗性用例生成（262 行）
- **为什么可替换**：
  - Promptfoo 的 red-teaming 更成熟（40+ 插件）
  - 当前实现是 PoC 级别的关键词匹配
- **集成方案**：调用 Promptfoo `promptfoo redteam generate`
- **推荐**：替换

#### ⚠️ stress_test.py → 用 DeepEval stress 替代
- **功能**：并发压力测试（333 行）
- **为什么可保留**：当前实现与 runner.py 共享 ThreadPoolExecutor，代价不高
- **集成方案**：DeepEval 也有 stress testing 但集成成本可能高于保留现有
- **推荐**：保留（与现有 runner 集成紧密）

#### ⚠️ dialogue_evaluator.py → 保留自建
- **功能**：多轮对话评测（5 维启发式 + LLM judge）
- **为什么保留**：518 行，与 skill-cert 的 workflow_step 模型深度耦合
- **简化方向**：无

#### ⚠️ dialogue_runner.py → 保留自建
- **功能**：对话执行 + OTel trace 录制
- **为什么保留**：与 dialogue_evaluator 紧密耦合
- **简化方向**：OTel 部分如果 Langfuse 集成后可简化

#### 🔄 trajectory_evaluator.py → 保留自建
- **功能**：轨迹质量评分（repetition + path + optimization + tool_accuracy + turn_relevance）
- **为什么保留**：与 skill-cert 的 ToolCall/TrajectoryStep 数据模型深度耦合
- **简化方向**：无

#### 🔄 replay.py → 保留自建
- **功能**：历史会话回放（113 行）
- **为什么保留**：逻辑简单，与 runner 紧密耦合
- **简化方向**：无

#### 🔄 reliability.py → 保留自建
- **功能**：错误分类 + 重试统计（87 行）
- **为什么保留**：仅 87 行，逻辑极简单
- **简化方向**：无

#### 🔄 maintainability.py → 保留自建
- **功能**：SKILL.md 可维护性评分（可读性/完整性/新鲜度）
- **为什么保留**：591 行，但高度定制化（SKILL.md 格式特定的分析）
- **简化方向**：可考虑用 SkillCompass 的部分逻辑（但 SkillCompass 本身也是独立工具，集成成本高）

#### 🔄 progressive_disclosure.py → 保留自建
- **功能**：三层成本模型（Index/Load/Runtime）
- **为什么保留**：这是 Anthropic Skill 方法论的特化实现，无替代
- **简化方向**：无

#### 🔄 gotchas_flywheel.py → 保留自建
- **功能**：失败经验积累（131 行）
- **为什么保留**：逻辑简单，与 eval 流程深度耦合
- **简化方向**：无

#### 🔄 trigger_accuracy_eval.py → 保留自建
- **功能**：L1 触发准确性（175 行）
- **为什么保留**：与 metrics.py 的 L1 计算互补
- **简化方向**：无

### 2.5 辅助层（纯基础设施）

#### 🔄 config.py → 保留自建
- **功能**：配置加载（模型配置/envelope/security）
- **为什么保留**：与 skill-cert CLI 深度耦合
- **简化方向**：无

#### 🔄 deadline.py → 保留自建
- **功能**：硬截止时间 + 阶段计时器
- **为什么保留**：155 行，逻辑简单
- **简化方向**：无

#### 🔄 constants.py → 保留自建
- **功能**：共享常量
- **为什么保留**：纯常量定义
- **简化方向**：无

#### 🔄 report_models.py → 保留自建
- **功能**：报告 Pydantic 模型
- **为什么保留**：内部数据契约
- **简化方向**：无

#### 🔄 stability.py → 保留自建
- **功能**：多运行稳定性（t-distribution CI）
- **为什么保留**：与 L4 指标计算紧密耦合
- **简化方向**：可增加 `pass@k`/`pass^k` 度量

#### 🔄 simulator.py → 可选删除
- **功能**：用户模拟器（132 行）
- **为什么可删**：仅在 dialogue mode 测试中使用，可用预定义脚本替代
- **推荐**：保留（代价低，测试中有用）

#### 🔄 integrations.py → 扩展为集成枢纽
- **功能**：SkillLab + DeepEval placeholder
- **为什么可扩展**：当前仅仅是骨架。应该扩展为同类模块的集成中心
- **推荐**：重写为真正的集成枢纽（Promptfoo security、DeepEval metrics、Langfuse observability、LiteLLM adapter）

---

## 三、总结三列表

### 保留自建（27 模块）

这些是 skill-cert 的**灵魂**——不可替代或集成成本远超维护成本：

| 模块 | 保留原因 | 行数 |
|------|---------|------|
| analyzer.py | SKILL.md parser 独特 | 622 |
| testgen.py | SkillSpec→评测用例 独特 | 1015 |
| runner.py | with/without 对比框架 | 388 |
| metrics.py | L1-L8 唯一指标 | 718 |
| grader.py | 确定性断言+去偏 | 664 |
| reporter.py | 自定义报告格式（10 行 facade → reporters/ 包 ~1288 行） | facade |
| drift.py | 唯一跨模型漂移 | 325 |
| envelope.py | 极简逻辑 | 56 |
| calibration.py | 与verdict深度耦合 | 222 |
| multi_skill.py | 无替代品 | 356 |
| skills_bench.py | 独特分析方法 | 192 |
| dialogue_evaluator.py | 与workflow耦合 | 518 |
| dialogue_runner.py | 与evaluator耦合 | — |
| trajectory_evaluator.py | 自定义数据模型 | 217 |
| replay.py | 极简逻辑 | 113 |
| reliability.py | 极简逻辑 | 87 |
| maintainability.py | SKILL.md特定分析 | 591 |
| progressive_disclosure.py | Anthropic方法论特化 | 351 |
| gotchas_flywheel.py | 极简+耦合 | 131 |
| trigger_accuracy_eval.py | 与L1耦合 | 175 |
| stability.py | 与L4耦合 | 261 |
| simulator.py | 测试用 | 132 |
| config.py | CLI耦合 | 307 |
| deadline.py | 极简逻辑 | 155 |
| constants.py | 纯常量 | 129 |
| report_models.py | 内部契约 | 211 |
| trace_models.py | 内部契约 | 247 |

### 替换为集成（4 模块）

这些已有成熟开源替代，集成后显著简化：

| 模块 | 行数 | 替换方案 | 简化后 | 节省 |
|------|------|---------|--------|------|
| security_probes.py | 600 | Giskard（首选）/ Promptfoo（备选） | ~50 行 facade | ~550 行 |
| adversarial.py | 262 | Promptfoo redteam | 删除 | ~260 行 |
| observability.py | 436 | Langfuse + OpenTelemetry | ~50 行 facade | ~380 行 |
| integrations.py | 110 | 重写为集成枢纽 | ~150 行 | — |

### 可选集成（评估后决定）

| 模块 | 行数 | 候选方案 | 建议 |
|------|------|---------|------|
| adapters/* | ~600 | LiteLLM (100+ model统一接口) | 保留（当前轻量稳定，长期标记候选） |
| pricing.py | 73 | LiteLLM cost tracker | 保留（仅73行） |
| token_ledger.py | 221 | LiteLLM callback | 保留（设计良好） |
| stress_test.py | 333 | DeepEval stress | 保留（与runner紧密耦合） |

---

## 四、集成目标 API 详细分析

### 4.1 DeepEval — 最推荐集成（纯 Python 库）

```python
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

class SkillMetric(BaseMetric):
    def measure(self, test_case: LLMTestCase) -> float:
        self.score = 0.8  # 你的计算逻辑
        self.success = self.score >= self.threshold
        return self.score

metric = SkillMetric(threshold=0.7)
metric.measure(test_case)
print(metric.score, metric.is_successful())
```

- **API 形态**：纯 Python 库，`pip install deepeval`
- **适用场景**：自定义 metric 计算、LLM-as-judge、回归检测
- **集成方式**：`BaseMetric` 子类化 → `metric.measure(test_case)` 调用
- **关键限制**：内置 50+ metrics，但你需要自定义 L1-L8（已支持 `BaseMetric`）

### 4.2 Promptfoo — 混合集成（Node.js + Python hooks）

```yaml
# YAML config + Python file:// hooks
tests:
  - file://tests.py:generate_tests
assert:
  - type: python
    value: file://assert.py:get_assert
```

- **API 形态**：Node.js CLI + Python `file://` hooks
- **适用场景**：red-teaming（40+插件）、LLM-as-judge (temp=0)、自定义 grader
- **集成方式**：Python hook 函数 → YAML 配置文件 → `npx promptfoo eval`
- **关键限制**：需要 Node.js 20+ 运行时（额外依赖）
- **推荐用法**：仅在 `--deep-security` 模式下调用 Promptfoo redteam

### 4.3 Giskard — 异步安全扫描

```python
from giskard.scan import generate_suite

suite = await generate_suite(description="Skill evaluation", languages=["en"])
result = await suite.run(target=my_async_agent)
```

- **API 形态**：Python `giskard-scan` 包（async-first, 3.12+）
- **适用场景**：red-teaming（OWASP Top-10 LLM）、注入检测
- **集成方式**：`async def` target 函数 + `suite.run()`
- **关键限制**：仅 Python 3.12+、需要 async 包装现有同步代码
- **推荐用法**：可选替代 Promptfoo redteam（选择 Giskard 或 Promptfoo，不同时集成）

### 4.4 Langfuse — LLM Observability 标准

```python
from langfuse import Langfuse

langfuse = Langfuse()
trace = langfuse.trace(name="skill-eval")
span = trace.span(name="eval-run")
span.generation(name="llm-call", model="gpt-4", usage={"input": 100, "output": 50})
```

- **API 形态**：纯 Python SDK + 自部署/云服务
- **适用场景**：trace recording、token tracking、cost monitoring
- **集成方式**：替换 `EventBus`，用 `langfuse.trace()` → `trace.span()` 模型
- **关键限制**：需要部署 Langfuse 服务或使用 Cloud 版本
- **推荐用法**：替换 self-built observability.py（436 行）

### 4.5 OpenAI Evals — 可选参考

- **API 形态**：`evals` Python 库 + OpenAI Cloud API
- **适用场景**：自定义 eval 类、completion function 协议
- **集成方式**：`Eval` 类继承 + `run_evals()`
- **关键限制**：Python 库已基本被 DeepEval 覆盖；Cloud API 仅限 OpenAI 用户
- **推荐用法**：参考其 CompletionFunction 协议设计，不直接集成

### 4.6 LiteLLM — 长期可选

- **API 形态**：纯 Python 库，100+ model 统一接口
- **适用场景**：替换 adapter 层，自动 cost tracking
- **集成方式**：`litellm.completion()` 替代自定义 adapter
- **关键限制**：当前 6 provider 维护成本不高，暂不切换
- **推荐用法**：Phase 3 评估（10+ provider 后切换）

---

## 五、简化路线图

### Phase 1：立即可执行（预估 6-10 周）

#### Step 1: integrations.py 重写为集成枢纽（先行，周 1-3）
- 保留现有的 `BaseIntegration` / `IntegrationDispatcher` 抽象
- 新增 `GiskardSecurityIntegration` 调用 Giskard Python API（**首选**，纯 Python 零 Node.js 依赖）
- 新增 `PromptfooSecurityIntegration` 调用 `npx promptfoo redteam run`（**备选**，需 Node.js 20+，详见 §四 4.7 收购风险说明）
- 新增 `LangfuseObservabilityIntegration` 替换 self-built EventBus
- 保持 `DeepEvalIntegration` 作为 metric 委托的入口

#### Step 2: security_probes.py → 分层架构（周 4-5，依赖 Step 1 的集成接口）
- 保留 80 探针作为**快速静态扫描**（默认模式，零外部依赖，始终可用）
- 新增 `--deep-security` flag 触发 Giskard 深度扫描（需 Step 1 的 `GiskardSecurityIntegration`）
- `SecurityReport` 合并两个结果，标注来源（static/deep）
- 快速扫描在解析后立即执行，深度扫描按需触发

#### Step 3: adversarial.py → 委托模式（周 6-7，依赖 Step 1）
- `WeaknessAnalyzer` 保留（SKILL.md 特定分析逻辑，不可替代）
- `AdversarialCase` 生成委托给 Giskard
- `AdversarialReport` 保留，接收外部工具输出

#### Step 4: 集成测试基础设施（周 8-10）
- Giskard mock fixtures、CI Docker 配置、集成测试用例、优雅降级（工具未安装时的 fallback）

### Phase 1 注意事项：Promptfoo 收购风险
- **OpenAI 于 2026 年 5 月收购了 Promptfoo**
- Promptfoo 作为**备选方案**保留，不做为主推荐路径
- 如果未来 Promptfoo 的 API 发生破坏性变化，可平稳切换到 Giskard（Python-native，无 Node.js 运行时依赖）
- 外部工具安装失败时，默认回退到自有的 80 探针

### Phase 2：中期（需要新增依赖，预估 4-8 周）

4. **observability.py** → Langfuse 集成（可选）
   - 添加 `langfuse` pip 依赖（可选 extras）
   - `EventBus` → `langfuse.trace()` + `trace.span()` 
   - `TraceExporter` → 保留现有 JSONL + OTLP 导出，Langfuse 作为**附加**导出目标
   - `SessionTelemetry` 保留作为 facade（内部接口不变）
   - 保留 `ExecutionTrace` / `TraceEvent` Pydantic 模型（内部契约）
   - **前提条件**：保留 JSONL 文件导出（默认），Langfuse 仅在配置 `--langfuse` 标志时启用
   - **离线兼容性**：当 Langfuse 不可用时，本地 SQLite 缓冲并后续回放

5. **grader.py** LLM judge 可选委托 DeepEval
   - `_llm_judge_with_call` → 可选择性委托给 `GEval` metric
   - 保留 `_debias_position` 逻辑（DeepEval 无此能力）
   - 保留确定性断言（`_evaluate_assertion`）独立

### Phase 3：长期（战略决策）

6. **adapters/* → LiteLLM** 评估
   - 当 model 列表达到 10+ provider 时切换到 `litellm.completion()`
   - 自动获得 pricing、token tracking、fallback 能力
   - 当前 6 provider 保持现有实现

---

## 六、不集成的原因（反证）

### DeepEval 不用于 L1-L8 计算
- DeepEval 的 `BaseMetric` 是通用抽象，不预设 L1-L8
- skill-cert 的 8 维指标设计是核心竞争力，自己算更灵活
- DeepEval 的 `evaluate()` 框架与 skill-cert 的 with/without 对比不兼容

### Promptfoo 不用于 core runner
- Promptfoo 的 YAML 配置模型与 skill-cert 的 SkillSpec 不匹配
- with/without 对比需要自定义 runner，Promptfoo 无此模式
- 集成胶水代码可能比保留当前实现更复杂

### Langfuse 仅用于 observability（不用于核心逻辑）
- token_ledger.py 保留：Langfuse 的 trace 粒度与 skill-cert 的 eval-level 不同
- metrics.py 保留：Langfuse 是观测工具，不是指标计算
- reporter.py 保留：Langfuse 的 UI 是开发工具，非最终报告

---

## 七、最终简化效果

| 指标 | 当前 | Phase 1 | Phase 2 | 最终 |
|------|------|---------|---------|------|
| engine/ 总模块 | 34 | 34 | 33 | 32 |
| engine/ 总代码行 | ~11,000 | ~11,400 | ~10,900 | ~10,900 |
| 新增测试代码 | - | +500 | +300 | +800 |
| 外部依赖数 | ~5 | ~6 | ~8 | ~8 |
| 集成程度 | 0% | 15% | 35% | 35% |
| 核心复杂度 | 高 | 中高 | 中高 | 中 |

**注意**：净节省的生产代码行数会被新增的集成测试基础设施（Giskard/Promptfoo mock fixtures、Langfuse 缓冲测试）部分抵消。但生产代码的复杂度（维护成本、bug 面）显著降低。

### Phase 1 效果（低风险，预估 6-10 周）
- security_probes.py：从 600 行缩减到 ~350 行（保留静态 80 探针扫描 + facade 到 Giskard）
- adversarial.py：从 262 行缩减到 ~150 行（保留 WeaknessAnalyzer，委托 AdversarialCase）
- integrations.py：从 110 行扩展到 ~150 行（真正的集成枢纽）
- 新增 ~500 行集成测试代码（Giskard mock fixtures、CI 配置）
- **净效果：生产代码 -600 行，测试代码 +500 行**

### Phase 2 效果（需要新依赖：langfuse，预估 4-8 周）
- observability.py：从 436 行缩减到 ~100 行（保留 + Langfuse facade，保留 JSONL 默认导出）
- grader.py LLM judge：可选委托给 DeepEval GEval
- **净节省：约 330 行（+ 50 行 facade），净节省 280 行**

### 不集成的底线
- **27 个核心模块保留**——它们体现 skill-cert 的独特价值
- **4 个渗透模块集成**——成熟工具做得更好
- **代码量减少约 14%，依赖增加 3 个**

## 八、最终建议

### 核心理念

> skill-cert 的"灵魂"必须保留自建，但"铠甲"可以借用成熟工具。

**自建（灵魂）**：
- L1-L8 8 维指标体系（`metrics.py`）
- with/without 基线对比框架（`runner.py`）
- SKILL.md 语义解析（`analyzer.py`）
- 自动评测生成 + 自审循环（`testgen.py`）
- 跨模型漂移检测（`drift.py`）
- 多技能冲突 + 认知过载（`multi_skill.py` + `skills_bench.py`）

**委托（铠甲）**：
- 安全扫描 → Giskard（首选，Python-native 零 Node.js 依赖）/Promptfoo（备选，40+ 探针 vs 自建 80）
- 可观测性 → Langfuse（可选附加，保留 JSONL 默认导出 + 离线缓冲）
- 对抗测试 → Giskard（Python-native，异步 API）
- LLM adapter → LiteLLM（长期，10+ provider 后）

**坚持自建而不错的原因**：
- 每个自建模块都是 skill-cert 的**差异化壁垒**
- 集成胶水代码的复杂度可能超过自建维护成本
- 成熟工具不理解 SKILL.md 语义，集成价值有限
- 外部工具带来运维成本（Node.js 运行时、服务端部署），须权衡收益

### 实施建议

```
Phase 1（6-10 周）：集成枢纽 + 分层安全 + 对抗委托
  ├── Step 1（周 1-3）：integrations.py 重写
  ├── Step 2（周 4-5）：security_probes.py 分层（依赖 Step 1）
  ├── Step 3（周 6-7）：adversarial.py 精简（依赖 Step 1）
  └── Step 4（周 8-10）：集成测试基础设施

Phase 2（4-8 周）：Observability 可选集成
  ├── observability.py → Langfuse（保留 JSONL 默认 + 离线缓冲）
  └── grader.py LLM judge 可选委托

Phase 3（评估）：长期架构决策
  ├── LiteLLM adapter 切换评估
  └── 不执行，除非条件触发
```
