# Skill-Cert 方法论审视报告 (2026-05-02)

## 审视框架

本次审视综合了三方面资料：
1. **代码实现** — engine/ 全部模块的实际代码
2. **Wiki 知识库** — SkillsBench(2026)、Agent Skills 机制、Skill设计模式、质量管理体系、Token优化
3. **外部业界研究(2025-2026)** — Google Cloud 三支柱评估、Zylos 双层架构、CLASSic框架、SpecWeave Verified Skills标准、LLM-as-Judge陷阱研究、多模型漂移检测等

---

## 一、整体判断：方向正确，但有多处可以升级

引擎骨架与业界方向基本一致，没有"方向性错误"。但 SkillsBench(2026) 和 Google Cloud(2025) 揭示了一些实现中**应该升级的假设**。

---

## 二、逐模块审视

### 2.1 核心评估架构（L1-L4）— 骨架正确，粒度不足

**当前做法**：L1(触发准确率) → L2(Delta) → L3(步骤遵循) → L4(稳定性)

**业界标准对照**：

| 当前指标 | 业界对应 | 差距 |
|----------|---------|------|
| L1 触发准确率 | CLASSic-Accuracy | **粒度不足**：CodeIF 有50个子指令维度，当前只有触发/不触发二元 |
| L2 Delta | SkillsBench 比较效用 | **方向正确**：SkillsBench 用配对基线计算归一化增益，当前做的是abs差值 |
| L3 步骤遵循 | Google Process/Trajectory | **严重不足**：只检查"步骤被覆盖"，没有检查**中间决策质量**（工具调用是否正确、每轮对话是否在主题上） |
| L4 稳定性 | CLASSic-Stability | **统计基础薄弱**：单次运行算std dev不够，业界要求5-10次试验 |

**建议优先级**：

- **P0** — L3 补全过程/轨迹维度：增加 turn-level 指标（轮次相关性、知识保留、工具调用正确性）
- **P1** — L2 改为归一化增益(Δ = (with - without)/without)，而非 abs 差值
- **P1** — L4 改为多试验(≥5次)聚合，报告置信区间

---

### 2.2 评测生成(testgen.py) — 自审查循环好，但缺少人工锚定

**当前做法**：generate → review → gap-fill 循环直到 coverage ≥ 90%

**SkillsBench 的核心发现**：**AI 自生成 Skills 平均 -1.3pp（有毒）**。虽然生成的是 eval cases 而不是 skills，但同质化风险存在——LLM 生成的评测可能系统性偏向 LLM 擅长的领域。

**建议**：
- 引入 **人工锚定集**（golden eval set），定期校准自动生成的评测质量
- 对生成的 eval 做覆盖率验证时，确保包含 SkillsBench 发现的**高杠杆领域**（医疗+51.9pp、制造+41.9pp）的测试模式

---

### 2.3 LLM-as-Judge(grader.py) — 二元判断 + 校准缺失

**当前做法**：确定性断言 + 可选 LLM-as-Judge，temperature=0

**业界发现(2025-2026)**：

| 问题 | 当前现状 | 业界建议 |
|------|---------|---------|
| 位置偏见 | 未处理 | 打乱响应顺序，检出偏见 |
| 冗长偏见 | 未处理 | 使用二元 Pass/Fail 替代1-5评分 |
| 校准 | 未做 | 需与人工标注对比，目标 >90% 对齐 |
| 评审原因 | 只有 passed/confidence/reasoning | 要求**具体书面批评**（为什么失败） |
| 中文 judge prompt | 可能存在语言偏见 | 验证中英文提示的交叉一致性 |

**建议**：
- **P1** — 切换为二元判断 + 必须给出具体失败原因
- **P2** — 建设人工校准集(50+ case)，对标人工判断

---

### 2.4 跨模型漂移(drift.py) — 阈值合理，但缺行为级漂移

**当前做法**：基于 pass_rate 绝对差，阈值 0.10/0.20/0.35

**业界新方法(arXiv 2604.17112)**：

跨模型分歧本身可以是**正确性信号**：
- Epistemic Uncertainty(EU)：模型间分歧大 → 可能不正确
- Aleatoric Uncertainty(AU)：模型间一致 → 可能正确

指标：**CMP**(Cross-Model Perplexity) 和 **CME**(Cross-Model Entropy)

**建议**：
- **P2** — 增加 CMP/CME 指标，在高分歧处标记"不确定/不可信"
- **P2** — 增加**中轮目标变更**测试(AgentChangeBench风格)：模拟用户中途改需求，检查模型是否适应

---

### 2.5 安全性测试 — 完全缺失

**当前做法**：没有任何安全探测

**SpecWeave Verified Skills 标准(2026)** 要求：
- 52+ 模式自动化扫描
- 三层认证：Scanned → Verified → Certified
- 必选 SKILL.md 字段：Security Notes、Permissions、Scope

**建议**：
- **P0** — 增加安全探测套件：提示注入、数据外泄、危险命令、凭证访问
- **P0** — 强制执行 SKILL.md schema：缺少必选字段直接拒绝

---

### 2.6 运行效率约束 — 缺失

**当前做法**：只评估质量，不评估效率

**业界标准(Braintrust 2026)**：
- 操作包络线：最大步数、最大工具调用、Token预算、挂钟超时
- 超过包络线的运行即使质量好也标记失败

**建议**：
- **P1** — 增加包络线检查：max_steps=20, max_tool_calls=15, token_budget=50000, timeout=300s

---

### 2.7 对话评估(dialogue_evaluator.py) — 启发式过重

**当前做法**：5维启发式评分（意图识别、引导质量、工作流遵循、异常处理、输出质量），基于词重叠、问句检测等

**问题**：
- 词重叠不是语义理解 → 与 SkillsBench 发现一致（Skill 触发依赖 token overlap 而非语义匹配）
- 但评估应该**用语义**，不能用同样的浅层方法

**建议**：
- **P2** — 对话评估改用 LLM-as-Judge + 结构化评分，辅以启发式作为效率检查
- 增加 SkillsBench 验证的 **2-3个Skills甜点区** 检查（同时加载过多Skill会导致认知过载）

---

## 三、与 Wiki 知识库的关键关联

| Wiki 知识 | 对引擎的启示 |
|-----------|-------------|
| **SkillsBench**：人工Skills +16.2pp，自生成 -1.3pp | eval 生成也是LLM自生成，需人工锚定校准 |
| **SkillsBench**：2-3个Skills是甜点区 | 评估时应限制同时加载的Skill数量 |
| **SkillsBench**：聚焦胜过详尽(Detailed +18.8pp, Comprehensive -2.9pp) | 评估时区分"精炼Skill"和"冗长Skill"的表现 |
| **Skill设计模式**：5+1模式 | 不同模式的Skill应有不同的评估权重（线性 vs 循环迭代 vs 多阶段） |
| **Description铁律**：500字符内，不写流程 | `analyzer.py` 解析 description 时应检查这些规则 |
| **岗位能力认证规定**：90分及格，3次机会 | PASS阈值(L1≥90%)与此一致，但缺少"重试机会"机制 |
| **质量管理(戴明/克劳斯比)**：预防优于检验 | 引擎是检验工具，缺少**预防性检查**（安全扫描、schema验证） |

---

## 四、优先级行动清单

| 优先级 | 行动 | 涉及模块 |
|--------|------|---------|
| **P0** | 增加安全探测套件(提示注入/数据外泄/危险命令/凭证访问) | 新增 engine/security_probes.py |
| **P0** | 强制执行 SKILL.md 必选字段(Security Notes, Permissions, Scope) | engine/analyzer.py |
| **P0** | L3 增加过程/轨迹级指标(轮次相关性、知识保留、工具调用正确性) | engine/metrics.py |
| **P1** | 增加操作包络线检查(max_steps, token_budget, timeout) | engine/runner.py |
| **P1** | LLM-as-Judge 改为二元判断 + 书面批评 | engine/grader.py, prompts/judge.md |
| **P1** | L2 改为归一化增益(Δ = (with-without)/without) | engine/metrics.py |
| **P1** | L4 改为多试验聚合(≥5次) + 置信区间 | engine/runner.py, engine/metrics.py |
| **P2** | 建设人工校准集(50+ case)，对标LLM Judge | 新增 tests/calibration/ |
| **P2** | 增加 CMP/CME 跨模型分歧指标 | engine/drift.py |
| **P2** | 对话评估增加 LLM-as-Judge 结构化评分 | engine/dialogue_evaluator.py |
| **P2** | eval 生成引入人工锚定集定期校准 | engine/testgen.py |

---

## 五、总结

引擎架构**没有过时**——L1-L4 多层级指标 + 自审查循环 + 跨模型漂移检测在 2026 年仍然是正确的方向。SkillsBench 的实证结果也验证了比较效用评估(L2)的必要性。

但需要承认两个关键局限：
1. **评估粒度停留在输出层**——缺少对中间决策过程的评估，这是 2025-2026 年业界最大的升级方向
2. **缺少安全维度和运行效率约束**——SpecWeave Verified Skills 和 Braintrust 已经把这两个维度作为必选项
