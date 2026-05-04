# Skill 评测工具全景分析 (2026-05-02)

## 一、核心结论

**不存在一个开箱即用的全能 Skill 评测方案，但存在明确的"组合复用"路径。**

业界有 5 个 Skill 专用工具、3 个通用 LLM 评测框架、4 个安全扫描工具可被组合使用。推荐策略：**skill-cert 作为编排层，调度外部工具做 static/security/process 评估，自身保留 parser/testgen/runner/reporter 作为核心引擎。**

---

## 二、第一层：Skill 专用评测工具

### 2.1 SkillTester
- **GitHub**: [skilltester-ai/skilltester](https://github.com/skilltester-ai/skilltester)
- **论文**: arXiv:2603.28815 (2026-03)
- **成熟度**: 实验性（"scoring system is still evolving"）
- **评测维度**:
  - **效用(Utility)**: 配对基线执行（baseline vs with-skill）→ 量化 Skill 的实际贡献
  - **安全(Security)**: 独立探针套件 → 异常行为/权限边界/敏感数据处理
- **工作流**: SampleAgent(生成任务) → ExecAgent(双轨执行) → SpecAgent(审查+报告)
- **输出**: Template.json + Template.csv + benchmark_report.md
- **与 skill-cert 关系**: skill-cert 的 L2 delta 已实现基线对比，但缺安全探针套件
- **License**: 开源 (GitHub)

### 2.2 Skill-Lab
- **GitHub**: [8ddieHu0314/Skill-Lab](https://github.com/8ddieHu0314/Skill-Lab)
- **PyPI**: `pip install skill-lab` (v0.7.0, Apache-2.0)
- **成熟度**: Beta (production-ready CLI)
- **评测维度**:
  - **静态分析**: 28项检查，4维度（Structure/Schema/Naming/Content），0-100质量评分
  - **触发测试**: 4类触发（explicit/implicit/contextual/negative），~13自动生成用例
  - **安全扫描**: 正则+熵检测+隐藏字符+IOC 匹配
  - **LLM 质量评审**: 可选 Anthropic/OpenAI/Gemini 多模型支持
- **关键能力**:
  - `sklab evaluate` — 全量静态分析 + 质量评分
  - `sklab validate` — CI/CD 快速通过/失败（exit code）
  - `sklab generate` — LLM 自动生成触发测试
  - `sklab trigger` — 真实 LLM 运行时触发测试
  - `sklab scan` — 安全扫描
  - `sklab info` — 元数据 + Token 成本估算
  - `sklab list-checks` — 浏览全部37项检查
- **可编程性**: 可通过 `from skill_lab.evaluators import StaticEvaluator` 作为 library 调用
- **与 skill-cert 关系**: analyzer.py 有解析但缺19项静态检查 + 触发测试

### 2.3 SkillsBench
- **GitHub**: [benchflow-ai/skillsbench](https://github.com/benchflow-ai/skillsbench)
- **网站**: [skillsbench.ai](https://skillsbench.ai)
- **论文**: arXiv:2602.12670, 36位学者+105位专家
- **成熟度**: 研究基准 (Apache-2.0, 1080 stars, 50 contributors)
- **规模**: 84任务/11领域/7模型配置, 7,308条轨迹, Docker 确定性验证
- **核心发现**:
  - 人工 Skills +16.2pp；AI 自生成 -1.3pp（有毒）
  - 2-3个 Skills 是甜点区(+18.6pp)
  - 聚焦胜过详尽(Detailed +18.8pp, Comprehensive -2.9pp)
  - 小模型+Skills > 大模型裸奔
- **用法**: `bench tasks init` → `bench eval create` → 自动化评估
- **与 skill-cert 关系**: skill-cert 已实现类似评测流程，但缺标准化数据集和 Docker 确定性验证环境

### 2.4 vskill CLI (SpecWeave)
- **网站**: [verified-skill.com](https://verified-skill.com)
- **成熟度**: 生产就绪
- **三级认证**:
  | Tier | 方法 | 成本 | 速度 |
  |------|------|------|------|
  | Scanned | 52 正则模式 + 结构验证 | 免费 | < 500ms |
  | Verified | Tier 1 + LLM 意图分析 | ~$0.03/skill | 5-15s |
  | Certified | Tiers 1+2 + 人工安全审查 + 沙箱 | $50-200/skill | 1-5天 |
- **扫描类别**: 9大类（凭证注入/提示注入/数据外泄/混淆/破坏性命令/动态上下文注入等）
- **关键命令**: `vskill scan`, `vskill find`, `vskill install` (装前强制扫描), `vskill audit`, `vskill eval`
- **与 skill-cert 关系**: skill-cert 完全没有安全扫描 ← **最大缺口**

### 2.5 agent-skills-eval
- **GitHub**: [caohaotiantian/agent-skills-eval](https://github.com/caohaotiantian/agent-skills-eval)
- **成熟度**: 实验性
- **评测维度**:
  - 5维静态评估（Outcome/Process/Style/Efficiency/Security）
  - Trace-based 安全分析（8类检查，分析实际 agent 行为）
  - YAML 驱动安全规则（9类：恶意代码/数据外泄/权限滥用/后门/提示注入/依赖/Web安全/供应链/加密弱点）
  - LLM-as-Judge 安全评分（5维：命令安全/数据保护/访问控制/输出安全/网络安全）
- **特殊能力**: 熵检测(阈值5.5bits)、隐藏字符(零宽/Unicode bidi/Cyrillic 同形字)、复合攻击检测、IOC 情报匹配

---

## 三、第二层：通用 LLM 评测框架

### 3.1 DeepEval（最高组合价值）
- **GitHub**: [confident-ai/deepeval](https://github.com/confident-ai/deepeval) (15K+ stars)
- **License**: Apache-2.0
- **成熟度**: 生产就绪
- **Agent 专用指标（直接填补 gap 1）**:
  - `TaskCompletionMetric` — 任务是否完成
  - `ToolCorrectnessMetric` — 工具调用是否正确
  - `ArgumentCorrectnessMetric` — 参数是否有效
  - `StepEfficiencyMetric` — 步骤效率
  - `PlanAdherenceMetric` — 计划遵循度
  - `PlanQualityMetric` — 计划质量
- **LLM Tracing**: 全链路 trace + span 级评分
- **合成数据**: 多轮对话场景自动生成
- **CI/CD**: pytest 原生集成
- **调用方式**: `pip install deepeval` → `from deepeval.metrics import TaskCompletionMetric`

### 3.2 Promptfoo（安全 + CI/CD）
- **GitHub**: [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) (20K+ stars)
- **License**: MIT
- **成熟度**: 生产就绪（OpenAI 内部使用，156家Fortune 500客户）
- **关键能力**:
  - **Red teaming**: 50+ 漏洞类型自动探测
  - **Skill 对比**: 直接支持 SKILL.md A/B 测试 (skill-used 断言)
  - **多模型对比**: 声明式 YAML 配置
  - **效率断言**: `cost` (token 费用), `latency` (响应时间)
  - **CI/CD**: GitHub Actions/GitLab/Jenkins 集成
  - **Agent 支持**: Claude Agent SDK + Codex SDK
- **Skill 测试示例**:
  ```yaml
  defaultTest:
    assert:
      - type: skill-used
        value: review-standards
      - type: cost
        threshold: 0.50
      - type: latency
        threshold: 120000
  ```

### 3.3 AgentShield（安全扫描专家）
- **GitHub**: [affaan-m/agentshield](https://github.com/affaan-m/agentshield)
- **成熟度**: 生产就绪 (v1.4.0, 305 stars)
- **规则规模**: 102+ 规则 / 5 类别
  - secrets (10 rules): API keys, tokens, passwords
  - permissions (10 rules): allow/deny, dangerous flags
  - hooks (34 rules): injection, exfiltration, persistence
  - MCP (23 rules): risky servers, npx supply chain
  - agents (25 rules): prompt injection, reflection attacks
- **输出**: A-F 评级 + 分类得分 + 具体修复建议
- **调用**: `agentshield scan [path]` CLI 或 GitHub Action
- **局限性**: skill-md 格式的覆盖弱于 agent-md 格式

### 3.4 其他可选框架
| 工具 | 类型 | 备注 |
|------|------|------|
| LangSmith | SaaS | tracing + human eval，适合持续观测 |
| Braintrust | SaaS/开源 | agent eval + 生产监控 |
| Ragas | RAG专项 | 不适合通用 Skill 评测 |
| Arize Phoenix | 可观测性 | OpenTelemetry based |
| Langfuse | 开源可观测 | 替代 LangSmith 的开源方案 |

---

## 四、效率评测补充说明

效率评测（执行速度 + Token 消耗）在现有工具中已有覆盖：

| 效率维度 | 已有工具支持 |
|----------|-------------|
| **执行时间** | Promptfoo `latency` 断言, DeepEval StepEfficiency, SkillsBench 计时 |
| **Token 消耗** | Promptfoo `cost` 断言, Skill-Lab `sklab info` Token 估算 |
| **步骤效率** | DeepEval `StepEfficiencyMetric`, Braintrust operating envelopes |
| **包络线检查** | skill-cert 新增 `engine/envelope.py` (max_steps/token_budget/timeout) |

skill-cert 当前缺少所有这些维度，需要在 `engine/runner.py` 中新增执行追踪（时间/Token/步骤计数），并在 `engine/metrics.py` 中增加效率指标。

---

## 五、推荐组合架构

```
skill-cert v2 (编排层)

Phase 0: SKILL.md 解析 ──────► engine/analyzer.py (保留)
Phase 1: 静态质量检查 ─────────► 调用 sklab evaluate
Phase 2: 安全扫描 ────────────► 调用 vskill scan + agentshield scan
Phase 3: 评测生成 ────────────► engine/testgen.py (保留) + SkillsBench 校准集
Phase 4: 执行 (with/without) ─► engine/runner.py (保留 + 增加效率追踪)
Phase 5: 评分 ────────────────► engine/grader.py (保留确定性) + deepeval (轨迹)
Phase 6: 指标计算 (L1-L4) ────► engine/metrics.py (升级)
         + 过程指标 ──────────► deepeval (TaskCompletion/ToolCorrectness)
         + 效率包络 ──────────► engine/envelope.py (新增)
Phase 7: 漂移检测 ────────────► engine/drift.py (保留)
Phase 8: Red teaming ─────────► 调用 promptfoo redteam
Phase 9: 报告生成 ────────────► engine/reporter.py (保留)
```

### 保留 vs 复用的决策原则

| 决策 | 模块 | 理由 |
|------|------|------|
| **保留** | analyzer, testgen, runner, grader, metrics, reporter | 已有完整实现，外部无同等替代 |
| **复用** | static checks | Skill-Lab 的 28项检查远超 analyzer 的简单解析 |
| **复用** | security scan | vskill + AgentShield 的 154+ 规则你不可能重写 |
| **复用** | trajectory eval | DeepEval 的 Agent 指标是专业领域 |
| **复用** | red team | Promptfoo 的 50+ 漏洞类型成熟可靠 |
| **复用** | calibration data | SkillsBench 84任务可作为 golden set |
| **新增** | envelope | 操作包络线是业界标准，需自行实现但不复杂 |

---

## 六、中文生态补充

百度搜索结果显示中文 AI 社区目前主要关注 Agent Skill 的概念普及和使用教程（阿里云、腾讯云、知乎、CSDN 大量文章），尚未出现成熟的中文 Skill 评测工具。阿里云 ClawHub 的安全扫描文章提到了 3万个 Skill 的安全度量尝试，但未形成独立工具。
