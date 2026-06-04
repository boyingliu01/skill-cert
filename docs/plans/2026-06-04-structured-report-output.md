# 评测报告结构化输出 — 实施设计文档

**日期**: 2026-06-04
**状态**: **APPROVED** — Delphi Review 共识通过 (2/2, 100%, 3 rounds)
**需求来源**: REQ-REPORT-001 ~ REQ-REPORT-004

---

## 1. Context

当前 skill-cert 的 JSON 报告是内联构建的简单 dict，缺少 `metadata`、`eval_details`、`security_scan` 等结构化字段；Markdown 报告以自由文本列表为主，缺少表格化指标概览和评估详情。需要按 4 个 REQ 进行全面改造，同时保持向后兼容。

### 需求概览

| REQ | 名称 | 核心要求 |
|-----|------|----------|
| REQ-REPORT-001 | 结构化 JSON 报告 | metadata, skill_summary, verdict_summary, metrics(含per-level), eval_details, drift_analysis, security_scan, improvement_suggestions, benchmark, config, raw_results, 可选sections |
| REQ-REPORT-002 | Markdown 结构化改造 | Executive Summary 加 metrics 表格, 指标改表格, 新增 Eval Details 表格, 建议加优先级(P0/P1/P2), Benchmark 加覆盖率 |
| REQ-REPORT-003 | JSON Schema | 定义 schemas/report.schema.json, 输出符合 schema, 支持 --json-schema-validate |
| REQ-REPORT-004 | CLI 参数 | --format json\|markdown\|both (默认 both), --json-schema-validate, 向后兼容 |

---

## 2. 设计方案

### Task 1: 新建 Pydantic 报告模型 (`engine/report_models.py`)

定义报告结构的 Pydantic 模型，作为 JSON 报告的 source of truth：

- `ReportMetadata` — report_version, generated_at, tool_version, spec_version
- `MetricLevelDetail` — level(L1-L4), name, score, threshold, status(PASS/FAIL/WARN), details
- `MetricsSummary` — overall_score, levels: list[MetricLevelDetail]
- `EvalDetailItem` — eval_id, name, category, result, pass_rate, key_findings
- `VerdictSummary` — verdict, overall_score, summary
- `SecurityScanResult` — verdict, total_findings, findings_by_severity, findings
- `ImprovementSuggestion` — text, priority(P0/P1/P2), expected_impact(high/medium/low)
- `BenchmarkInfo` — 扩展加 test_coverage_rate (float)
- `StructuredReport` — 顶层模型，组装所有 section

阈值从 `VerdictThresholds` 读取（L1=0.9, L2=0.2, L3=0.85, L4 std<=0.1）。

### Task 2: 生成 JSON Schema (`schemas/report.schema.json`)

由 Pydantic 模型自动生成：`StructuredReport.model_json_schema()`，新增辅助函数 `export_report_schema()`。
**不再手写维护**，Pydantic 模型为 Single Source of Truth。静态文件仅在发布流程中导出。

- **required** 字段：metadata, verdict_summary, metrics, eval_details, drift_analysis, improvement_suggestions, benchmark, config, raw_results
- **可选**：security_scan（when available）, cost_analysis, latency_analysis, reliability, maintainability, multi_skill_analysis, scalability

### Task 3: 改造 `engine/reporter.py`

**3a. 重构 `_generate_suggestions()`**：返回 `list[ImprovementSuggestion]` 而非 `list[str]`。优先级规则（阈值提取到 `SuggestionThresholds` 常量类）：
- P0: overall_score < 0.6, drift high, security BLOCK
- P1: 单层级不达标, cost_delta > 50%, error_rate > 20%
- P2: 优化建议

**过渡方案**：`ImprovementSuggestion` 实现 `__str__` 返回 `self.text`；`generate_report()` 内部自动将旧格式 `list[str]` 转换为 `ImprovementSuggestion(text=s, priority="P2", expected_impact="low")`。

**3b. 新增 `_build_eval_details(eval_case_meta)`**：接收 `eval_case_meta: dict[int, dict]` 参数（由 `_run_single_phase()` 构建），从 `metrics['_results']` 提取逐条结果，通过 eval_id 关联 name/category。找不到时赋值 "N/A" 并记录 Warning。构建 `list[EvalDetailItem]`，含 key_findings（从 assertion_results 生成）。

**数据映射构建**（在 `_run_single_phase()` 中，调用 `generate_report()` 之前）：
```python
eval_cases = spec["evals"].get("eval_cases", spec["evals"].get("cases", []))
eval_case_meta = {c["id"]: {"name": c.get("name", ""), "category": c.get("category", "normal")} for c in eval_cases}
```

**3c. 新增 `_build_structured_json()`**：用 `StructuredReport` 模型构建完整 JSON dict，`model_dump(mode="json", exclude_none=True)` 输出。保留顶层 `verdict` 和 `overall_score` 快捷字段确保向后兼容。

**security_scan 执行流控制**：
```python
security_data = metrics.get("security_scan")
if security_data is not None:
    structured.security_scan = SecurityScanResult(**security_data)
# else: None + exclude_none=True 自动排除
```

**3d. 重写 Jinja2 模板**：
- Executive Summary 后新增 Metrics Overview 表格（Level | Score | Threshold | Status）
- L1-L4 Metrics 改为表格格式
- 新增 Evaluation Details section（ID | Name | Category | Result | Key Findings）
- Improvement Suggestions 加 `[P0]`/`[P1]`/`[P2]` 优先级标记和 expected impact
- Benchmark 加 test_coverage_rate

**3e. 更新 `generate_report()` 的 JSON 构建部分**（原 L372-407）：替换为调用 `_build_structured_json()`。

**3f. 新增模块级函数 `validate_report_schema(report: dict) -> list[str]`**：加载 `schemas/report.schema.json`，用 `jsonschema.Draft7Validator` 验证，返回错误列表。

### Task 4: CLI 参数支持 (`skill_cert/cli/main.py`)

在 argparse 中 `--envelope` 之后新增：
```
--format {json,markdown,both}  (dest="report_format", default="both")
--json-schema-validate         (action="store_true")
```

### Task 5: 报告写入逻辑改造

**5a. `skill_cert/cli/evals.py`** (L188-204)：根据 `args.report_format` 决定写 .md / .json / 两者。`--json-schema-validate` 时调用 `validate_report_schema()` 打印结果。evals-cache 始终写入。

**5b. `skill_cert/cli/multi_skill.py`** (L55-58)：同样 format 感知。

**5c. `skill_cert/cli/stress.py`** (L51-78)：同样 format 感知。

### Task 6: 辅助修改

- `engine/constants.py`：新增 `ReportConstants`（REPORT_VERSION, TOOL_VERSION, DEFAULT_FORMAT, SUPPORTED_FORMATS）+ `SuggestionThresholds`（P0_SCORE=0.6, P1_COST_DELTA=0.5, P1_ERROR_RATE=0.2）
- `pyproject.toml`：dependencies 加 `"jsonschema>=4.18"`，验证所有运行时依赖已声明（pip check）

### Task 7: 测试

**`tests/test_reporter.py`** 新增约 25 个测试：
- JSON 结构验证：metadata, verdict_summary, metrics.levels(4元素), eval_details, improvement_suggestions 含 priority, benchmark 含 coverage_rate
- Markdown 结构验证：metrics overview table, eval details table, suggestions 含 [P0]/[P1]/[P2], 表格列数一致性
- 端到端渲染测试：完整 mock 数据渲染验证所有 section、数值格式化、空值兜底（cost_analysis=None 不渲染）
- Schema 验证：文件存在、有效报告通过、缺字段失败、validate_report_schema() 函数
- 向后兼容：顶层 verdict/overall_score 仍存在
- 性能基准：1000 条 eval results 的 model_dump < 2.0s

**`tests/test_cli_pipeline.py`** 新增约 6 个测试：
- 默认 format=both, json-only, markdown-only, schema validate flag

### Task 8: 验证

1. `pytest tests/test_reporter.py tests/test_cli_pipeline.py -v`
2. `pytest` 全量回归
3. `ruff check . && ruff format .`
4. `pip check` 验证依赖完整性
5. 手动运行 `skill-cert --skill SKILL.md --format json --json-schema-validate` 验证输出

---

## 3. 关键文件路径

| 文件 | 操作 | 覆盖需求 |
|------|------|----------|
| `engine/report_models.py` | 新建 | REQ-REPORT-001 |
| `schemas/report.schema.json` | 新建 | REQ-REPORT-003 |
| `engine/reporter.py` | 修改 | REQ-REPORT-001, 002, 003 |
| `engine/constants.py` | 修改 | 支撑 |
| `skill_cert/cli/main.py` | 修改 | REQ-REPORT-004 |
| `skill_cert/cli/evals.py` | 修改 | REQ-REPORT-004 |
| `skill_cert/cli/multi_skill.py` | 修改 | REQ-REPORT-004 |
| `skill_cert/cli/stress.py` | 修改 | REQ-REPORT-004 |
| `pyproject.toml` | 修改 | 依赖 |
| `tests/test_reporter.py` | 修改 | 测试 |
| `tests/test_cli_pipeline.py` | 修改 | 测试 |

---

## 4. 风险与注意事项（已含 Delphi Review 修复方案）

1. **`_generate_suggestions()` 返回类型变更**：`ImprovementSuggestion` 实现 `__str__` 返回 `self.text` + `generate_report()` 内部自动转换旧格式 `list[str]`，降低爆炸半径
2. **Jinja2 模板兼容性**：`{{ suggestion }}` 通过 `__str__` 仍可工作；新增端到端渲染测试和表格列数校验
3. **JSON 向后兼容**：保留顶层 `verdict`/`overall_score` 作为冗余快捷字段
4. **eval_details 数据完整性**：在 `_run_single_phase()` 中构建 `eval_case_meta` 映射表传入 `generate_report()`，找不到时 "N/A" + Warning
5. **security_scan 数据来源**：Pydantic 模型 `Optional` + Schema 不在 required + `exclude_none=True` + 执行流显式 None 检查
6. **`jsonschema` 依赖**：Task 6 添加到 pyproject.toml + Task 8 增加 `pip check` 验证
7. **JSON Schema 与 Pydantic 同步**：Schema 由 `model_json_schema()` 自动生成，不再手写维护
8. **Pydantic 性能**：Task 8 增加 1000 条数据基准测试 (< 2.0s)

---

## 5. 验收标准

| AC | 描述 |
|----|------|
| AC-001 | JSON 报告包含 metadata, skill_summary, verdict_summary, metrics, eval_details, drift_analysis, improvement_suggestions, benchmark, config, raw_results。security_scan 为可选字段（when available） |
| AC-002 | metrics 含 per-level 子指标（score, threshold, status, details） |
| AC-003 | JSON 报告通过 schemas/report.schema.json 验证 |
| AC-004 | Markdown Executive Summary 含 metrics 概览表格 |
| AC-005 | Markdown 指标从列表改为表格格式 |
| AC-006 | Markdown 含 Evaluation Details 表格 |
| AC-007 | 改进建议含优先级（P0/P1/P2）和预期影响 |
| AC-008 | Benchmark 含测试覆盖率数值 |
| AC-009 | `--format json` 仅输出 JSON |
| AC-010 | `--format markdown` 仅输出 Markdown |
| AC-011 | `--format both`（默认）输出两者 |
| AC-012 | `--json-schema-validate` 触发 schema 验证 |
| AC-013 | 无 `--format` 参数时行为等同 `both`（向后兼容） |

---

## 6. Delphi Review 共识记录

- **Expert A** (glm-5.1, 智谱, 架构师): APPROVED (9/10) — Round 2
- **Expert B** (Qwen3.5-122B-A10B, 阿里, 实现工程师): APPROVED (9/10) — Round 3
- **共识比例**: 100% (>= 95% 阈值)
- **状态文件**: `.sprint-state/delphi-reviewed.json`

### 关键修复（Round 1→3 迭代）

| 轮次 | 问题级别 | 问题 | 修复方案 |
|------|---------|------|----------|
| R1 | Critical | eval_details 数据映射断层 | _run_single_phase 构建 eval_case_meta 映射表 |
| R1 | Major | JSON Schema 双重维护 | 由 Pydantic model_json_schema() 自动生成 |
| R1 | Major | _generate_suggestions 破坏性变更 | __str__ 过渡 + 旧格式自动转换 |
| R1 | Major | security_scan required 但不可用 | 设为 Optional + exclude_none |
| R2 | Critical | 依赖声明缺证据 | pyproject.toml 实际内容 + pip check |
| R2 | Major | Jinja2 测试深度不足 | 端到端渲染 + 表格列数校验 + 空值兜底 |
| R2 | Major | Pydantic 性能未验证 | 1000 条数据基准测试 < 2.0s |
