# Skill-Cert: AI Skill 评测引擎

通用 AI Skill 评测引擎 — 自解析、自生成测试、自执行、自评估。

## 核心能力

| 能力 | 说明 |
|------|------|
| **自解析** | 读取任意 SKILL.md，提取语义结构（SkillSpec） |
| **自生成** | LLM 自动生成测试用例（evals.json） |
| **自执行** | with/without-skill 交叉验证 |
| **自评估** | L1-L4 四层指标 + 跨模型漂移检测 |

## 快速开始

```bash
pip install -e .
skill-cert --skill /path/to/SKILL.md [--models m1,m2] [--output results/]
```

## L1-L4 评估维度

| 维度 | 指标 | 及格线 |
|------|------|--------|
| L1: 触发准确性 | trigger evals 准确率 | >= 90% |
| L2: 输出正确性 | with/without skill delta | >= 20% |
| L3: 步骤遵循度 | workflow 步骤覆盖率 | >= 85% |
| L4: 执行稳定性 | 同 eval 多次运行标准差 | std <= 10% |

## 评测流程

```
Phase 0: Skill 解析（SKILL.md → SkillSpec）
Phase 1: 测试生成 + 自审循环（生成 → 审查 → 补缺）
Phase 2: 交叉验证执行（with-skill vs without-skill）
Phase 3: 渐进补充（分析薄弱区域，补充测试）
Phase 4: 完整 L1-L4 评估
Phase 5: 跨模型漂移检测
Phase 6: 报告生成（Markdown + JSON）
```

## 支持的模型

通过 `~/.skill-cert/models.yaml` 配置，支持所有 OpenAI/Anthropic 兼容 API：

```yaml
models:
  - name: bailian-coder
    base_url: "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1"
    api_key: "sk-..."
    model_name: "qwen3.6-plus"
    fallback_model: "qwen3-coder-plus"
```

## 项目结构

```
skill-cert/
├── engine/          # 评测引擎核心
│   ├── analyzer.py  # SKILL.md 解析器
│   ├── testgen.py   # 测试用例生成（LLM 自生成）
│   ├── runner.py    # 测试执行引擎
│   ├── grader.py    # 评分引擎（确定性断言 + LLM-as-judge）
│   ├── metrics.py   # L1-L4 指标计算
│   ├── drift.py     # 跨模型漂移检测
│   ├── reporter.py  # 报告生成器
│   └── config.py    # 配置管理
├── adapters/        # 模型适配层
│   ├── base.py      # 抽象模型接口
│   └── anthropic_compat.py  # Anthropic 兼容（百炼 coding plan）
├── prompts/         # LLM 评测 prompts
├── schemas/         # JSON Schema 定义
├── templates/       # 模板文件
├── scripts/         # UAT 验证脚本
├── tests/           # 单元测试 + 集成测试
├── specification.yaml  # 需求规格
└── SKILL.md         # Skill 自描述
```

## 测试结果

已对 4 个真实 Skill 完成 UAT 验证：

| Skill | Verdict | Score |
|-------|---------|-------|
| delphi-review | PASS_WITH_CAVEATS | 63.0% |
| plan-eng-review | PASS_WITH_CAVEATS | 67.0% |
| test-spec-alignment | FAIL | 45.2% |
| sprint-flow | FAIL | 26.6% |

详细报告见 `results/` 目录。

## License

MIT
