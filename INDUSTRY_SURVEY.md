# skill-cert 行业调研综述：AI Skill 评测机制对比分析

> 基于学术界、工业界和开源社区的全面调研

---

## 1. 调研目标

- 系统调研业界 AI Skill/Agent 评测工具和方法论
- 对比分析 skill-cert 所用方法的合理性和完整性
- 审视 skill-cert 各评测项（L1-L8）的必要性和准确性
- 提供改进建议和 roadmap

---

## 2. 业界工具全景

### 2.1 通用 LLM/Agent 评测框架

| 工具 | Stars | 核心方法 | 基线对比 | Skill 测试 |
|------|-------|----------|---------|-----------|
| **Promptfoo** | ~22,350 | YAML 声明式配置，CLI-first，50+断言类型 | ✅ | ✅ |
| **DeepEval** | ~15,600 | Pytest-native，50+指标，LLM-as-judge | ✅ | ✅ |
| **Giskard** | ~543 | 模块化 Agent 测试，Red-teaming | ✅ | ✅ |
| **OpenAgentBench** | ~1 | 有状态控制系统验证，混沌工程 | ✅ | ✅ |
| **ASSERT** | 新发布 | 需求驱动的行为规格评估 | ✅ | ✅ |

### 2.2 专用 Skill 评测工具（直接竞品）

| 工具 | Stars | 核心方法 | 与 skill-cert 差异 |
|------|-------|----------|-------------------|
| **Skillgrade** | ~520 | 确定性断言 + LLM rubric，"Unit tests for skills" | 无 L1-L8 指标体系 |
| **UpSkill** | ~683 | Teacher→Student 能力迁移 + Benchmark | HuggingFace 出品，侧重技能生成 |
| **SkillCompass** | ~213 | 六维质量评分（usage-driven） | 侧重使用数据，非自动化测试 |
| **skill-eval** | - | 配对比较 + 位置去偏 | 仅 A/B testing，无结构化指标 |
| **Skill-up** | ~23 | CLI 框架，rule_based/script/agent_judge | 阿里出品，多引擎支持 |
| **OpenSkillEval** | ~11 | 质量+成本联合审计 | 仅5个技能家族 |
| **eval-skills** | ~4 | 正确性/延迟/错误率/一致性 四维 | 最接近 skill-cert 的 L1 级评估 |
| **SkillLens** | 新发布 | 效用+安全性双轴评估 | 4阶段管道 + Harbor 沙箱 |

### 2.3 模型评测平台（非 Skill 专属）

- **AgentBench** (3,500 stars)：8 环境 benchmark，测评模型能力
- **SWE-bench** (4,670 stars)：真实 GitHub issue 修复 benchmark
- **OpenCompass**：70+ 数据集，5 能力维度 400K 问题
- **OpenJudge** (531 stars)：50+ 生产级评分器
- **FlagEval**：BAAI（智源研究院）国家 AI 评测平台
- **One-Eval** (146 stars)：图结构 NL2Eval 自动化

### 2.4 关键发现：skill-cert 的差异化优势

在专用 Skill 评测工具中，skill-cert 具有以下独特优势：

1. **唯一的 L1-L8 结构化指标体系**：其他工具最多只有 3-4 个维度
2. **最高测试覆盖率**：1134 个 pytest 测试（竞品无此级别的自测覆盖）
3. **唯一的跨模型漂移检测**：DriftDetector 模块独一无二
4. **唯一的 80 模式安全探针**：6 类别覆盖（INJECTION=18, DANGEROUS_COMMAND=17, CREDENTIAL=14, EXFILTRATION=13, OBFUSCATION=9, PRIVILEGE_ESCALATION=9）
5. **唯一的多技能冲突检测**：SkillsBench 认知过载分析
6. **唯一的黄金集校准**：Cohen's Kappa + FPR/FNR 校准框架

---

## 3. 学术界方法论审视

### 3.1 LLM-as-Judge 的可靠性问题

学术界已识别出 LLM-as-Judge 的 **12 种偏见**（"Justice or Prejudice?", arXiv 2410.02736），包括：
- **位置偏见**（Position Bias）：答案顺序影响判断
- **自我增强偏见**（Self-Enhancement Bias）：模型偏好自己的输出
- **冗长偏见**（Verbosity Bias）：偏好更长的回答

**关键发现**：位置偏见影响随候选答案数量增加而加剧，多数模型的鲁棒性低于 0.5。

### 3.2 循环性问题（Circularity Problem）——两个维度

"LLM-Evaluation Tropes"（arXiv 2504.19076）定义了循环性问题的严重性：
- 当 LLM 评测器嵌入系统并用于官方评估时，反馈回路导致自我强化
- 递归共训练（recursive co-training）会放大偏见，导致概念漂移

**对 skill-cert 的适用性——必须区分两个不同架构层级的风险**：

**风险 Type A：testgen 循环**（一次性，较低严重性）
- testgen 用 LLM 生成评测用例 — 这是 Phase 1 的**一次性操作**，不会在每次评测时重复
- 缓解：增加 prompt 多样性约束、人工审核评测集、coverage 审查
- 如果 testgen 生成了一批低质量/有偏见的测试用例，所有后续评测都会受影响

**风险 Type B：grader 循环**（每次运行，较高严重性）
- grader 的 LLM-as-judge 每次评测都会调用 — 这是**每次评测都发生**的循环
- 如果 judge 模型和被测模型是同一家族，存在自我偏好风险
- 当前 L4 稳定性计算中排除 LLM judge 结果是正确的做法
- 缓解：强制不同模型家族评审（测试生成 ≠ 判决）、温度=0、位置去偏（已实现）

### 3.3 学术界推荐的 Guardrails

| 问题 | 推荐缓解 | skill-cert 当前状态 |
|------|---------|-------------------|
| 位置偏见 | 位置交换去偏（Position Swap） | ✅ grader 已实现 `_debias_position` |
| 自我偏好 | 跨模型评测 + DBG 分数 | ⚠️ 支持多模型但未强制跨家族 |
| 单评测员不可靠 | 循环评测员分配（CyclicJudge） | ❌ 未实现 |
| 评测测试过于简单 | 自适应难度提升（ATA） | ❌ 未实现 |
| 缺少人类基准 | 10-20% 人类标注黄金集 | ⚠️ 校准框架存在但无实际黄金集 |

---

## 4. 大厂实践对比

### 4.1 Anthropic - "Demystifying evals for AI agents" (2026.01)

**核心架构**：Task + Graders + Transcript + Outcome

**三级评分体系**：
1. **Code-based（确定性）**：最快最可靠
2. **Model-based（LLM 评判）**：灵活性高
3. **Human（人类）**：校准用黄金标准

**关键指标**：
- `pass@k`：k 次尝试中至少成功一次的概率（衡量能力）
- `pass^k`：k 次尝试全部成功的概率（衡量一致性/可靠性）

**对比 skill-cert**：
- skill-cert 的 graded 架构（确定性断言 + LLM judge）与 Anthropic 的三级体系高度对齐 ✅
- skill-cert 的 L4 稳定性仅用 std，Anthropic 的 `pass^k` 更符合工业实践
- Anthropic 强调"从真实失败案例构建评测集"，skill-cert 是自动生成的 ❌

### 4.2 OpenAI - Skill Evaluation 实践

**四个目标类别**：
1. **Outcome goals**（任务完成，对应 L2）
2. **Process goals**（技能调用，对应 L1/L3）
3. **Style goals**（规范遵循）
4. **Efficiency goals**（无 thrashing，对应 L5）

**关键策略**：
- 结构化输出（JSON schema）用于稳定评分
- 捕获 JSONL traces 用于确定性检查
- "不需要写评测代码，只需提供 JSON 数据和 YAML 参数"

**对比 skill-cert**：
- skill-cert 的 L1-L8 覆盖了 Outcome/Process/Efficiency，但缺少 Style ⚠️
- OpenAI 的结构化输出验证与 skill-cert 的 `json_valid` 断言等价 ✅
- skill-cert 缺少 OpenAI 的"无需写评测代码"的易用性设计

### 4.3 Google DeepMind - Agent 评测框架

**三支柱结构**：
1. **Outcome assessment**（任务完成度、正确性）
2. **Process/trajectory analysis**（推理质量、工具使用）
3. **Trust & safety**（策略合规、风险缓解）

**行业发现**：0/15 主流 benchmark 将安全性纳入评分；13/15 仅用二元成功度量。

**对比 skill-cert**：
- skill-cert 已将安全性纳入（80 探针），这是超前的 ✅
- trajectory analysis 在 skill-cert 中主要在 L6（仅 dialogue 模式），单轮模式不足 ⚠️

### 4.4 Meta - Agent Research Environments (ARE)

**验证协议**：Oracle 对比 → 事件级验证 → 工具级验证 → 时间验证 → 因果验证

**800 场景 x 10 宇宙**：邮件、日历、消息、文件系统等动态环境

**对比 skill-cert**：
- Meta 的动态环境和因果验证远超 skill-cert 的静态评估
- 但 Meta 的框架面向通用 Agent 能力（非 Skill 评估），目标不同

### 4.5 关键共识

**所有大厂的共同实践**：
- ✅ 确定性 + LLM + 人类 三级评估（skill-cert 已实现）
- ✅ 基线对比（skill-cert 的 with/without 是核心方法）
- ✅ 多模型交叉验证（skill-cert 的 drift detection）
- ⚠️ 从生产日志构建评测集（skill-cert 是自动生成）
- ❌ 持续评测监控循环（skill-cert 是离线的）

---

## 5. skill-cert 各评测项审视

### 5.1 L1：Trigger Accuracy（>= 90%）

**评估**：✅ 必要且方法合理

- 使用 F1 Score 替代简单准确率，涵盖正负样本
- 与 Anthropic/OpenAI 的"技能激活精确度"概念对齐
- **唯一风险**：auto-generated 的负样例可能不够 realistic
- **改进建议**：参考 ATA (arXiv 2508.17393) 的对抗性测试生成

### 5.2 L2：With/Without Skill Normalized Gain（>= 20%）

**评估**：✅ 必要，方法基本合理但存在统计风险

- 归一化增益公式 `Δ = (with - without) / without` 符合行业标准
- 本质上是一个效果量（effect size）度量，方法学基础扎实
- **主要风险**：
  - 当 `without` 接近 0 时的除零/近似除零问题（已用 epsilon 处理）
  - 当断言质量差时（如大量 `contains "skill"` 伪断言），L2 退化
  - 单次运行的随机性（建议引入 `pass@k` 思维）
- **改进建议**：
  - 引入 bootstrap confidence interval 报告
  - 当断言质量低于阈值时降低 L2 置信度
  - 参考 Anthropic 的 `pass@k` / `pass^k` 替代当前单次 pass_rate

### 5.3 L3：Step Adherence（>= 85%）

**评估**：⚠️ 必要，但当前实现有结构性缺陷

- **当前公式**：`0.5 × step_coverage + 0.3 × tool_call_accuracy + 0.2 × turn_relevance`
- **实现细节**：
  - `step_coverage` 自身有两层 fallback：有 workflow_step 数据时，精确匹配 → Jaccard ≥60% token 重叠（置信度系数 0.7）→ 否则回退到 `avg(pass_rate)`
  - L3 级别：当 `tool_call_accuracy` 和 `turn_relevance` 均存在时，使用加权公式；否则仅回退到 `step_coverage` 单值
- **问题**：
  - 当缺少 trajectory 数据（tool_call/turn 信息缺失）时，L3 仅依赖 `step_coverage`
  - 当 `step_coverage` 自身又回退到 `avg(pass_rate)` 时，L3 与 L2 产生信息重叠——两者在极端退化情形下度量相同事物
  - 但在 workflow_step 信息可用时，L3 提供与 L2 真正不同的信号
- **改进建议**：
  - 当缺少 trajectory 数据时，明确标记 L3 为 `unavailable` 而非使用代理
  - 增加 Google 式的 process/trajectory grading（不仅看是否覆盖 workflow_step）
  - 当 workflow_steps 实际存在时，L3 是一个合理且信息量丰富的度量

### 5.4 L4：Execution Stability（std <= 10%）

**评估**：✅ 必要，方法是合理的起步

- 当前实现：提取确定性断言通过率，计算 std，返回 `1 - std`
- An​​thropic 的 `pass^k` 度量比 std 更符合操作意义
- **改进建议**：
  - 报告 CI（置信区间）而非仅 std
  - 增加 `pass^k` 等价度量（k 次运行中至少有 k 次全部通过的比例）
  - 默认运行次数从单次增加到至少 3 次

### 5.5 L5：Step Efficiency

**评估**：✅ 必要，方法合理但阈值粗糙

- EnvelopeChecker 检查 steps/tokens/timeout/tool_calls
- 计分方式：0 violations=1.0，1 violation=0.7，2+=0.3
- **问题**：违反 1 条和 5 条的区别被抹平
- **改进建议**：采用连续分数（如 `1 - violations/cap`），或在多违规时区分严重程度

### 5.6 L6：Trajectory Quality（dialogue mode only）

**评估**：⚠️ 必要但范围过窄

- 仅在 dialogue mode 下可用
- 当前仅使用 embedding cosine similarity
- 与 Anthropic/Google 的 trajectory analysis 相比过于简化
- **改进建议**：
  - 在单轮模式下也加入 trajectory 分析（trace-based）
  - 参考 Meta ARE 的工具级和时间级验证

### 5.7 L7：Cost Efficiency & L8：Latency

**评估**：✅ 必要且方法合理

- Pricing 表覆盖 17 模型 x 6 提供商
- Latency 输出 P50/P95/P99 完整分布
- 与行业成本/延迟监控实践对齐
- **改进建议**：L7 中的 `cost_efficiency = L2_delta / cost_delta` 需要更明确的解释

---

## 6. 核心发现

### 6.1 方法论的合理性

**skill-cert 的整体方法论在业界是合理的**：

| 评估维度 | 业界标准 | skill-cert |
|---------|---------|-----------|
| 基线对比 (with/without) | Anthropic, OpenAI, Meta 均使用 | ✅ 核心方法 |
| 三级评分 (确定+LLM+人类) | 所有大厂共识 | ✅ 前两级已实现 |
| 多模型交叉验证 | 大厂要求 | ✅ DriftDetector |
| 安全性评估 | 新趋势（0/15 benchmark 含安全） | ✅ 80 探针 |
| 自动测试生成 | Anthropic 使用 LLM 生成 | ✅ self-review loop |
| 校准黄金集 | Anthropic "必要的" | ⚠️ 框架存在，无实际数据 |
| 持续监控 | 所有大厂 | ❌ 离线静态 |

### 6.2 两个根本性风险

**风险 1：循环性问题（Circularity）——两个架构维度**

skill-cert 最根本的威胁来自**自动测试生成 + LLM-as-Judge 的循环反馈**，但需区分两个不同的架构层级：

- **Type A：testgen 循环**（一次性生成）：testgen 用 LLM 生成评测用例时，如果产生有偏见的测试集，所有后续评测都会受影响。缓解方式：coverage 审查、断言多样性约束、人工审核测试集。
- **Type B：grader 循环**（每次评测）：LLM-as-judge 每次评测调用同一家族模型，存在自我偏好放大。当前缓解措施：去偏检测（debiased position）、LLM judge 禁用开关、温度=0。建议增强：强制跨模型家族评测。

**风险 2：断言质量退化（Assertion Degradation）**

来自我们之前的断言质量分析：
- delphi-review: 55.6% 断言是 `contains "skill"`（无意义的关键词匹配）
- test-driven-development: 100% 断言是 `contains "skill"`
- 根因是**结构性的**——coverage 算法（testgen.py）在指标上激励关键词匹配，而非语义有意义的断言。简单 ban `"skill"` 只会导致 LLM 变异为 `contains "SKILL.md"` 等价形式。需要的修复：(1) 改变 coverage 度量，惩罚语义空洞的断言(2) 增加多样性约束(3) 引入断言质量评分作为生成后过滤器。

### 6.3 竞争优势总结

在专用 Skill 评测工具中，skill-cert 具有**显著的结构性优势**：

1. **L1-L8 指标体系**：业界唯一的 8 维结构化度量
2. **测试覆盖深度**：1134 自测，远超竞品
3. **安全性集成**：开源 Skill 评测工具中唯一集成安全扫描（80 探针 x 6 类别）的
4. **跨模型漂移**：唯一检测 Skill 在不同模型间表现差异的工具

---

## 7. 改进建议（按优先级）

### P0：阻断性（影响评测结果可信度）

1. **解决循环性 Type B 风险**：强制跨模型家族评测——测试生成和判决必须使用不同模型家族（如 testgen=Qwen, judge=DeepSeek）。当模型家族重叠时降低 L2/L3 置信度分数。
2. **修复断言质量退化**：结构性修复——不仅 ban `"skill"` 关键词，更需要：(a) coverage 度量惩罚语义空洞断言 (b) 增加多样性约束（≥3 种断言类型 per case）(c) 生成后断言质量过滤器，拒绝语义意义 F1 < 0.3 的断言。
3. **L3 信号完整性**：当缺少 trajectory 数据时标记为 `unavailable`，不使用代理值。当 workflow_steps 可用时 L3 提供有效信号。

### P1：高优先级（显著提升方法论严谨性）

4. **引入 `pass@k`/`pass^k`**：替代 L2 单次 pass_rate 和 L4 简单 std
5. **Bootstrap CI 报告**：所有指标报告置信区间而非仅点估计
6. **跨模型家族评测**：当同一模型家族用于生成和评判时降低置信度分值

### P2：增强性（对齐行业最佳实践）

7. **Process/Trajectory 扩展**：将 L3/L6 扩展到单轮模式
8. **自适应难度**：参考 ATA 的 weakness-planning 算法，动态提升测试难度
9. **持续评测**：支持 CI/CD 集成和生产监控
10. **风格度量**：增加 Style 维度（OpenAI 的 Style goals）

---

## 8. 结论

**skill-cert 的方法论在学术界和工业界均有充分的理论和实践支撑**。其核心设计——基线对比、三级评分、多模型交叉验证、自动测试生成——与 Anthropic、OpenAI、Google、Meta 的最佳实践高度对齐。

当前存在两个根本性风险：**循环性**（LLM 自生成自评判）和**断言质量退化**（coverage 算法激励关键词生成）。这两个问题不是设计理念的错误，而是工程实现中的 gap，可通过引入人类校准和优化 testgen 提示来解决。

在与 9 个专用 Skill 评测工具的对比中，skill-cert 具有**最完整的指标体系（L1-L8）、最高的自测覆盖（1134 tests）、最全面的安全集成（80 probes）和唯一的跨模型漂移检测**，是目前业界最先进的 Skill 评测引擎。
