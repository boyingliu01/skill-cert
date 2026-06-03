# Skill-Cert：AI Skill 评测与认证引擎

> 自动评测 AI Agent Skill 的质量、效果、稳定性、安全性和成本表现。

Skill-Cert 是一个面向 `SKILL.md` 的自动化评测引擎。它可以读取任意 AI Agent Skill 定义文件，自动解析技能结构，生成评测用例，执行 with-skill / without-skill 对比实验，计算 L1-L8 指标，检测跨模型漂移，并输出标准化的 PASS / PASS_WITH_CAVEATS / FAIL 判定报告。

一句话概括：

> Skill-Cert 让「一个 Skill 到底有没有用」从主观感觉变成可重复、可量化、可对比的评测结果。

[English](README.md) | [简体中文](README.zh.md)

---

## 目录

- [1. 为什么需要 Skill-Cert？](#1-为什么需要-skill-cert)
- [2. Skill-Cert 做什么？](#2-skill-cert-做什么)
- [3. 核心思路](#3-核心思路)
- [4. 评测流程详解](#4-评测流程详解)
- [5. 架构设计](#5-架构设计)
- [6. 使用方式](#6-使用方式)
- [7. 配置说明](#7-配置说明)
- [8. 开发指南](#8-开发指南)
- [9. 问题和局限](#9-问题和局限)
- [10. License](#10-license)

---

## 1. 为什么需要 Skill-Cert？

现在很多团队都会给 AI Coding Agent 编写 Skill，例如：

- 代码审查 Skill
- 安全审计 Skill
- 文档生成 Skill
- Debug Skill
- PR 发布 Skill
- 浏览器 QA Skill
- 项目特定开发规范 Skill

但 Skill 写完之后，通常会遇到几个问题：

### 1.1 不知道 Skill 是否真的生效

一个 Skill 看起来写得很详细，但模型是否真的会在正确场景触发它？触发后是否真的遵循里面的流程？输出是否比不用 Skill 更好？

如果没有评测，只能靠人工试几次，结论很容易受样例、模型状态、评审者主观判断影响。

### 1.2 不知道 Skill 是否稳定

同一个 Skill 在 Claude、GPT、Qwen、DeepSeek、Gemini 上是否表现一致？同一个模型多跑几次是否结果稳定？某个 Skill 是否只对一个模型有效，换模型就失效？

这些都需要跨模型、跨运行的系统化评测。

### 1.3 不知道 Skill 是否安全

Skill 本质上是给模型的高优先级操作指导。如果 Skill 中包含危险命令、凭证访问、提示注入、外传数据指令，就可能带来安全风险。

Skill-Cert 在评测前加入安全扫描，提前识别风险。

### 1.4 不知道 Skill 的成本和延迟影响

Skill 通常会增加上下文长度、工具调用次数和推理步骤。这可能提升效果，也可能带来更高成本和更慢响应。

Skill-Cert 会跟踪 token、成本、延迟，并评估收益是否值得。

---

## 2. Skill-Cert 做什么？

Skill-Cert 接收一个 `SKILL.md` 文件，执行完整评测流水线：

```
SKILL.md
  ↓
解析 Skill 结构
  ↓
安全扫描
  ↓
自动生成 eval 测试
  ↓
自审 + 补齐覆盖缺口
  ↓
with-skill / without-skill 执行
  ↓
断言评分 + LLM-as-judge
  ↓
L1-L8 指标计算
  ↓
跨模型漂移检测
  ↓
Markdown + JSON 报告
```

最终输出：

- `{skill}-report.md`：面向人的评测报告
- `{skill}-result.json`：面向机器处理的结构化结果
- `{skill}-evals-cache.json`：评测用例和执行缓存

---

## 3. 核心思路

Skill-Cert 的核心假设是：

> 一个好的 Skill 不应该只「看起来合理」，它必须在真实任务中稳定提升模型表现。

因此评测不是单纯检查 `SKILL.md` 文本，而是围绕四个问题展开：

| 问题 | 对应指标 |
|---|---|
| 模型知道什么时候该用这个 Skill 吗？ | L1 Trigger Accuracy |
| 用了 Skill 之后结果真的更好吗？ | L2 Output Delta |
| 模型是否遵守了 Skill 的流程？ | L3 Step Adherence |
| 多次运行、多个模型下表现是否稳定？ | L4 Stability / Drift |

在此基础上，再扩展评估效率、安全、成本、延迟、多轮对话质量等维度。

---

## 4. 评测流程详解

### Phase 0：Skill 解析

实现位置：`engine/analyzer.py`，核心对象 `SkillSpec`、`WorkflowStep`，核心函数 `parse_skill_md()`。

Skill-Cert 首先读取 `SKILL.md`，提取结构化语义模型 `SkillSpec`。主要提取内容：

- `name`、`description`、triggers
- workflow steps、anti-patterns
- output format、examples
- content length、parse method、parse confidence

解析方式：

1. YAML frontmatter 解析
2. Markdown AST 解析（基于 `markdown-it-py`）
3. Regex 提取关键章节
4. 必要时 fallback 到 LLM 辅助解析

解析后会计算 8 维置信度评分：frontmatter(0.30) + workflow(0.25) + headings(0.15) + anti-patterns(0.10) + output-format(0.08) + triggers(0.07) + examples(0.05) + bonus(0.05)。如果解析置信度过低，后续评测结果会被标记为不可靠。

### Phase 0.5：安全扫描

实现位置：`engine/security_probes.py`，核心对象 `SecurityScanner`。

安全扫描在测试生成之前执行。它检查 5 类风险：

| 类别 | 含义 |
|---|---|
| INJ | Prompt Injection / 指令注入 |
| EXF | Data Exfiltration / 数据外传 |
| DCMD | Dangerous Commands / 危险命令 |
| CRD | Credential Access / 凭证访问 |
| OBF | Obfuscation / 混淆行为 |

当前内置 19 个安全探测模式。扫描结果分为 PASS / WARN / BLOCK。如果出现 BLOCK 级风险，评测会直接失败，避免执行潜在危险 Skill。

### Phase 1：自动生成 eval 测试

实现位置：`engine/testgen.py`，核心对象 `EvalGenerator`，fallback 模板 `templates/minimum-evals.json`。

Skill-Cert 会根据 `SkillSpec` 自动生成评测用例。测试生成不是一次性完成，而是一个自审循环：

```
生成初始测试 → 评审覆盖率 → 发现缺口 → 补充测试 → 再次评审 → 直到 coverage >= 90%
```

覆盖范围包括：trigger cases（应该触发 / 不应该触发）、workflow step cases、anti-pattern cases、output format cases、security / robustness cases。

关键阈值：

| 阈值 | 含义 |
|---|---|
| coverage target = 90% | 理想覆盖率 |
| coverage degrade = 70% | 低于该值需要降级 |
| coverage block = 70% | 严重不足时阻断评测 |

如果自动生成失败，会使用 `minimum-evals.json` 作为保底测试集。

### Phase 2：with-skill / without-skill 执行

实现位置：`engine/runner.py`，核心对象 `EvalRunner`。

Skill-Cert 的核心不是「只看 Skill 输出」，而是对比实验：

```
同一批 eval
  ├── without-skill：模型不加载 Skill
  └── with-skill：模型加载 Skill
```

然后比较两组结果差异。这解决了一个关键问题：如果模型本来就能做好任务，那不能证明 Skill 有价值。只有 with-skill 明显优于 without-skill，才说明 Skill 真的带来了增量。

Runner 同时负责：并发执行、rate limit 控制、timeout 控制、token usage 跟踪、安全扫描接入、operating envelope 检查、部分失败时保留结果。

默认限制：

| 项 | 默认值 |
|---|---|
| max steps | 20 |
| max tool calls | 15 |
| token budget | 50,000 |
| timeout | 300s |
| max concurrency | 5 |
| rate limit | 60 RPM |

### Phase 3：评分

实现位置：`engine/grader.py`，核心对象 `Grader`、`JudgeResult`、`EvalAssertion`。

Skill-Cert 使用两类评分方式。

#### 确定性断言

支持 `contains`、`not_contains`、`regex`、`starts_with`、`json_valid`。断言带权重：Normal(1)、Important(2)、Critical(3)。确定性断言的优点是稳定、便宜、可重复。

#### LLM-as-judge

对于复杂行为（如「是否进行了合理的架构权衡」「是否识别了隐藏风险」），确定性断言可能不够。此时 Skill-Cert 可以启用 LLM-as-judge。约束：temperature 必须为 0，只在确定性断言不足时使用，L4 稳定性计算会排除 LLM judge 以避免引入随机性。

### Phase 4：L1-L8 指标计算

实现位置：`engine/metrics.py`，核心对象 `MetricsCalculator`。

Skill-Cert 使用 8 层指标体系：

| 指标 | 名称 | 衡量什么 | 通过标准 |
|---|---|---|---|
| L1 | Trigger Accuracy | 模型是否知道什么时候使用 Skill | >= 90% |
| L2 | Output Delta | with-skill 相比 without-skill 是否提升 | >= 20% |
| L3 | Step Adherence | 是否遵循 Skill 工作流 | >= 85% |
| L4 | Stability | 多次执行是否稳定 | std <= 10% |
| L5 | Step Efficiency | 是否在步骤/token/工具调用限制内 | 全部通过 |
| L6 | Trajectory Quality | 多轮对话轨迹是否合理 | dialogue 模式 |
| L7 | Cost Efficiency | 成本是否值得 | 低于预算 |
| L8 | Latency | 延迟是否可接受 | 无明显慢请求 |

其中 L1/L2 关注效果，L3/L4 关注可靠性，L5/L7/L8 关注效率，L6 关注多轮交互质量。

### Phase 5：跨模型漂移检测

实现位置：`engine/drift.py`，核心对象 `DriftDetector`。

Skill-Cert 会在多个模型上运行同一套 eval，比较 pass rate 差异。

漂移分级：

| 等级 | 方差范围 | 含义 |
|---|---|---|
| none | <= 0.10 | 基本一致 |
| low | <= 0.20 | 轻微差异，可接受 |
| moderate | <= 0.35 | 明显差异，需要关注 |
| high | > 0.35 | 不稳定，不能发布 |

判定规则：none/low 不影响 PASS，moderate 降级为 PASS_WITH_CAVEATS，high 直接 FAIL。

### Phase 6：报告生成

实现位置：`engine/reporter.py`，核心对象 `Reporter`。

Skill-Cert 输出两类报告：

**Markdown 报告**：适合人阅读，包含执行摘要、verdict、overall score、L1-L8 指标、drift 分析、security scan、cost analysis、latency analysis、improvement suggestions、config summary。

**JSON 报告**：适合自动化系统消费，包含结构化字段：

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
    "highest_severity": "none",
    "average_variance": 0.0,
    "overall_verdict": "PASS"
  },
  "evaluation_coverage": {
    "total_evaluations": 207,
    "avg_pass_rate": 1.0
  }
}
```

### 扩展能力

| 能力 | 模块 | 说明 |
|---|---|---|
| 多技能冲突检测 | `multi_skill.py` | trigger 重叠、prompt 干扰、token 预算溢出 |
| 压力测试 | `stress_test.py` | 并发公平性、内存追踪、可扩展性评分 |
| 可靠性追踪 | `reliability.py` | 错误分类、重试统计、优雅降级 |
| 可维护性评分 | `maintainability.py` | SKILL.md 可读性、完整性、新鲜度评分 |
| 外部集成 | `integrations.py` | SkillLab / DeepEval providers（优雅降级） |
| 运行包络 | `envelope.py` | steps/tokens/timeout/tool_calls 限制执行 |
| 真实 Token 追踪 | `adapters/` | TokenUsage dataclass，非近似值 |
| 成本分析 | `adapters/pricing.py` | 17 个模型，5 个 provider 家族 |

---

## 5. 架构设计

Skill-Cert 采用 Clean Architecture 风格，核心分层如下：

```
skill_cert/       Presentation 层：CLI 入口
    ↓
engine/           Domain 层：核心评测逻辑
    ↓
adapters/         Infrastructure 层：LLM Provider 适配
    ↓
prompts/
schemas/
templates/        Support 层：提示词、Schema、模板
```

### 5.1 Presentation：CLI 层

实现位置：`skill_cert/cli.py`、`skill_cert/cli/main.py`。职责：解析命令行参数、加载配置、调用核心 pipeline、输出退出码、生成报告文件。

### 5.2 Domain：评测核心层

实现位置：`engine/`。

| 文件 | 职责 |
|---|---|
| `analyzer.py` | 解析 SKILL.md 为 SkillSpec |
| `testgen.py` | 自动生成 eval 测试 |
| `runner.py` | 执行 with-skill / without-skill |
| `grader.py` | 对模型输出评分 |
| `metrics.py` | 计算 L1-L8 指标 |
| `drift.py` | 跨模型漂移检测 |
| `reporter.py` | 生成 Markdown / JSON 报告 |
| `security_probes.py` | 安全扫描 |
| `envelope.py` | 运行包络检查 |
| `config.py` | 配置加载和校验 |
| `dialogue_evaluator.py` | 多轮对话评测 |
| `replay.py` | 历史会话重放 |
| `simulator.py` | 测试用 LLM 行为模拟 |
| `multi_skill.py` | 多 Skill 冲突检测 |
| `stress_test.py` | 压力测试 |
| `reliability.py` | 可靠性追踪 |
| `maintainability.py` | SKILL.md 可维护性评分 |

### 5.3 Infrastructure：模型适配层

实现位置：`adapters/base.py`、`adapters/anthropic_compat.py`、`adapters/openai_compat.py`、`adapters/pricing.py`。

职责：定义统一 LLM 调用协议、适配 Anthropic / OpenAI-compatible API、追踪真实 token usage、根据 pricing table 计算成本。

目前 pricing 支持多个模型家族：Anthropic、OpenAI、Qwen、DeepSeek、Gemini。

### 5.4 Support：模板和 Schema

实现位置：`prompts/`、`schemas/`、`templates/`。

职责：LLM judge prompt、testgen prompt、test-review prompt、test-gap prompt、eval JSON schema、SkillSpec schema、minimum eval fallback template。

---

## 6. 使用方式

### 6.1 安装

```bash
pip install -e .
```

开发模式：

```bash
pip install -e ".[dev]"
```

### 6.2 单模型评测

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=https://api.example.com/v1,$API_KEY" \
  --output ./results/
```

适合快速检查 Skill 是否基本可用、本地调试、生成初步报告。

### 6.3 多模型漂移检测

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=url,key|m2=url,key" \
  --output ./results/
```

适合发布前验证 Skill 是否跨模型稳定、比较不同 provider 表现、发现模型依赖性。

### 6.4 多轮对话模式

```bash
skill-cert --skill path/to/SKILL.md \
  --mode dialogue \
  --max-turns 10
```

适合 Orchestration Skill、Debug Skill、QA Skill、Code Review Skill 等需要多轮决策的 Agent Skill。

### 6.5 Replay 回归测试

```bash
skill-cert --skill path/to/SKILL.md \
  --mode replay \
  --session session.jsonl
```

适合历史会话回放、Skill 改动前后对比、防止回归。

### 6.6 多次运行稳定性测试

```bash
skill-cert --skill path/to/SKILL.md \
  --models "m1=url,key|m2=url,key" \
  --runs 5
```

适合计算 L4 稳定性、检测随机波动、验证 Skill 是否可重复。

### 6.7 压力测试

```bash
skill-cert --skill path/to/SKILL.md \
  --stress \
  --stress-concurrency 50 \
  --stress-evals 100
```

适合验证高并发场景下的表现、检测资源泄漏、评估可扩展性。

### 6.8 Verdict 判定逻辑

| Verdict | 条件 |
|---|---|
| **PASS** | L1 >= 90%, L2 >= 20%, L3 >= 85%, L4 std <= 10%, drift none/low |
| **PASS_WITH_CAVEATS** | 核心指标通过，但 drift moderate |
| **FAIL** | 任一核心指标不达标，或 drift high，或覆盖率 < 70% |

---

## 7. 配置说明

### 7.1 环境变量

| 变量 | 说明 |
|---|---|
| `SKILL_CERT_MODELS` | 模型配置：`name=url,key[,fallback]\|name2=url,key` |
| `SKILL_CERT_MAX_CONCURRENCY` | 最大并发数（默认 5） |
| `SKILL_CERT_RATE_LIMIT_RPM` | 速率限制 RPM（默认 60） |
| `SKILL_CERT_TIMEOUT` | 超时秒数（默认 300） |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `OPENAI_API_KEY` | OpenAI-compatible API Key |
| `OPENAI_BASE_URL` | OpenAI-compatible Base URL |

### 7.2 配置文件

`~/.skill-cert/models.yaml`：

```yaml
models:
  - model_name: "qwen3.6-plus"
    base_url: "https://api.example.com/v1"
    api_key: "$API_KEY"
    fallback_model: "qwen3-coder-plus"
```

配置优先级：CLI 参数 > 环境变量 > 配置文件 > 默认值。

---

## 8. 开发指南

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行所有测试
pytest

# 运行测试并查看覆盖率
pytest --cov=engine --cov=skill_cert --cov=adapters --cov-report=term-missing

# 格式化和 lint
ruff check . && ruff format .
```

**项目规范：**

- Pydantic v2 用于所有数据模型
- 所有函数签名带类型注解
- ruff 用于 linting 和格式化
- pytest 用于测试（测试文件与 engine/ 模块结构 1:1 对应）
- Prompt 模板是 `.md` 文件，不是 Python 字符串
- 无硬编码密钥，API Key 通过环境变量或配置文件提供

**项目结构：**

```
skill-cert/
├── engine/          # 核心 pipeline：parser, testgen, runner, grader, metrics, reporter, drift,
│                    # dialogue, replay, simulator, security_probes, envelope, integrations,
│                    # reliability, maintainability, multi_skill, stress_test, stability, config
├── skill_cert/      # CLI 入口 (cli.py)
├── adapters/        # LLM provider 适配器 (Anthropic, OpenAI-compatible) + pricing table
├── prompts/         # LLM prompt 模板 (judge, dialogue, drift, testgen, test-review, test-gap)
├── schemas/         # JSON schemas (eval cases, SkillSpec)
├── templates/       # Fallback eval 模板 (minimum-evals.json)
├── tests/           # pytest 测试套件 — 402 个测试，与 engine/ 模块 1:1 对应
└── results/         # 输出目录：{skill}-report.md, {skill}-result.json
```

---

## 9. 问题和局限

### 9.1 当前已知局限

**L3 Step Adherence 粒度不足**

当前 L3 只检查「步骤是否被覆盖」，不检查中间决策质量（工具调用是否正确、每轮交互是否合理）。这意味着一个 Skill 即使步骤被覆盖了，但中间过程质量差，L3 也不会反映出来。

**L4 稳定性需要更多采样**

当前单次 `--runs N` 计算 std dev。行业标准通常需要 5-10 次独立试验才能得到可靠的置信区间。单次运行的 std dev 可能不够稳定。

**LLM-as-judge 缺少校准**

当前 LLM-as-judge 没有：
- Position bias 处理（选项顺序可能影响判断）
- 人工标注校准（golden eval set）
- 具体失败原因（只给 binary 判断）

**Dialogue 评测依赖词重叠**

多轮对话评测目前过度依赖词重叠而非语义理解，可能漏判或误判。

**安全扫描覆盖有限**

当前 19 个安全探测模式，行业标准（如 SpecWeave）推荐 52+ 模式。可能存在未覆盖的攻击向量。

**单模型评测不够**

虽然支持多模型，但如果用户只用一个模型评测，无法检测模型依赖性。Skill 可能只对一个模型有效。

### 9.2 使用注意事项

- **评测需要 API Key**：Skill-Cert 依赖 LLM API 调用，需要配置至少一个模型的 API Key。评测过程会产生 API 费用。
- **评测时间较长**：完整评测（含多模型、多轮对话）可能需要数十分钟到数小时，取决于 eval 数量和模型响应速度。
- **结果受模型影响**：同一 Skill 在不同模型上结果可能不同，建议至少用 2 个不同 provider 的模型评测。
- **评测不是 100% 准确**：自动化评测无法完全替代人工评审，尤其是复杂行为判断。建议将 Skill-Cert 作为辅助工具，结合人工评审使用。
- **覆盖率 < 70% 会阻断**：如果 Skill 结构过于简单或模糊，可能无法生成足够测试，评测会被阻断。
- **不要修改执行后的 eval 用例**：Phase 2 执行后 eval 用例被锁定，修改会破坏评测完整性。

### 9.3 与行业对比的差距

| 维度 | 当前状态 | 行业参考 |
|---|---|---|
| L1 触发粒度 | 二元触发判断 | CodeIF 的 50 子维度 |
| L3 轨迹质量 | 缺少轮次级质量指标 | 需要 turn-level 评估 |
| L4 统计方法 | 单次运行 std | 5-10 次试验置信区间 |
| 不确定性检测 | 无 CMP/CME | 跨模型困惑度/熵 |
| 校准数据集 | 无人工标注 golden set | 需要人工标注校准 |

---

## 10. License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
