# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.2] - 2026-06-27

### Fixed — P0 Bugfixes
- **Cost calculation (#55)**: `EvalRunner._run_single()` now reads adapter's `model` attribute when `model_name` is missing. Previously `getattr(adapter, "model_name")` always returned `"unknown"` because adapters store model as `self.model`, not `self.model_name`. All cost reports are now accurate.
- **LLM judge JSON parsing (#56)**: Added `_repair_json_trailing_commas()` static method to fix common LLM JSON output errors (trailing commas before `}`/`]`). Previously caused all LLM judge evaluations to fall back to assertion-based grading.
- **eval_details integration tests (#54)**: Added 3 integration tests verifying the full data flow from `_run_all_evals()` → `metrics["_results"]` → `build_structured_report(eval_results=...)` → `StructuredReport.eval_details`. Core fix was already in commit 9f94974; tests lock in regression prevention.
- **skill_type fully verified (#57)**: `SkillSpec.skill_type` detection and testgen prompt branching confirmed working. 14 existing tests cover CLI tool, library, and agent guide detection.

### Added
- `tests/test_grader.py`: 10 new tests for robust JSON extraction (trailing commas, prose-wrapped JSON, confidence clamping)
- `tests/test_evals.py`: 3 new integration tests (`TestEvalDetailsIntegration`) for eval_details data flow

## [0.6.1] - 2026-06-26

### Added — Pipeline Integrity Fixes
- **Assertion quality scoring**: Coverage metric now penalizes keyword-only assertions (e.g. `contains "skill"`) with a diversity penalty. TestGen prompt includes keyword blacklist and 2+ assertion type requirement. See `engine/testgen.py:_calculate_coverage`.
- **L3 signal integrity**: `_calculate_l3_step_adherence` returns `None` when trajectory data is unavailable instead of proxying through `avg(pass_rate)`. L3 is excluded from overall score when unavailable.
- **Circularity risk detection (Type B mitigation)**: `EvalRunner` now detects same-family model conflicts via `_detect_circularity_risk()`. Logs warnings when testgen and judge share a model family (e.g. both Qwen). Exposes `circularity_risk` and `circularity_warnings` on the runner.
- **Pipeline wiring**: `deep_security` flag and `IntegrationDispatcher` are now connected through `EvalRunner` → `SecurityScanner.scan(deep_security=True)`. CLI `--deep-security` flag is fully wired end-to-end.

### Changed
- `_calculate_coverage` now applies type-diversity and keyword-penalty factors to coverage score.
- `EvalRunner.__init__` accepts `model_names`, `integration_dispatcher`, and `deep_security` params.
- `SecurityScanner` constructed with `integration_dispatcher` from EvalRunner.

## [0.6.0] - 2026-06-26

### Added — Phase 1 Integration Hub
- **Integration Hub** (`engine/integrations.py`): Rewritten as an extensible integration dispatcher with three new providers:
  - `GiskardSecurityIntegration`: Deep security scanning via Giskard red-teaming (Python-native, primary recommendation).
  - `PromptfooSecurityIntegration`: Red-team scanning via Promptfoo CLI (backup option, requires Node.js 20+). Includes OpenAI acquisition risk documentation (May 2026).
  - `IntegrationDispatcher.health_check()`: Reports availability status (available/degraded/unavailable) for all registered providers.
- **Layered Security Scanner** (`engine/security_probes.py`):
  - `SecurityScanner` now accepts optional `integration_dispatcher` parameter for deep scan delegation.
  - `scan(skill_content, skill_name, deep_security=False)`: When `deep_security=True` and dispatcher available, delegates to external security tools.
  - `SecurityReport.coverage`: New computed property for assertion quality scoring.
  - `SecurityReport.summary`: Now includes `categories_scanned`, `deep_scan` (bool), and `deep_source` keys.
- **CLI**: New `--deep-security` flag enables Giskard-based deep security scanning.
  - Also settable via `SKILL_CERT_DEEP_SECURITY` environment variable.
- **Adversarial Delegation** (`engine/adversarial.py`):
  - New `generate_adversarial_cases()` function delegates adversarial case generation to integration dispatcher.
  - `WeaknessAnalyzer` kept self-built (SKILL.md-specific analysis).
- **Graceful Degradation**: All external tool integrations gracefully skip when tools are not installed (zero external dependency baseline).
- **Tests**: +238 new tests (1,372 total), including integration-level graceful degradation tests.

### Changed
- `SecurityScanner.scan()`: Signature changed from `(self, text)` to `(self, skill_content, skill_name, deep_security=False)` — fully backward compatible via positional args.
- `_build_summary()`: Now includes `categories_scanned` key for coverage calculation.

### Fixed
- Security probe count corrected from 52 to 80 across all documentation and `constants.py`.
- L3 fallback description in documentation updated to match actual code behavior.
- Circuit breaker analysis now distinguishes Type A (testgen, one-time) vs Type B (grader, per-eval) circularity risks.
- 3 pre-existing E501 line-length warnings resolved.

### Docs
- `INDUSTRY_SURVEY.md`: Comprehensive industry survey of 9+ Skill/Agent evaluation tools.
- `INTEGRATION_ASSESSMENT.md`: Module-by-module keep-vs-integrate assessment with Phase 1-3 roadmap.
- `docs/superpowers/plans/2026-06-26-phase1-integration-hub.md`: TDD implementation plan.

## [0.5.9] - 2026-06-26

### Added
- `SecurityReport.coverage`: computed property returning ratio of categories with findings vs total categories scanned. Used for assertion quality scoring in the integration hub.

## [0.5.8] - 2026-06-25

### Fixed
- **Asymmetric assertion bias**: eval generation prompt previously instructed LLM to use `not_contains` assertions for without_skill phase while using `regex` assertions for with_skill phase. This made without_skill evaluation trivially easier, producing false L2=0% results. Fixed by instructing symmetric assertion types and adding explicit fallback mechanism documentation.

## [0.5.7] - 2026-06-25

### Fixed
- `_parse_models_from_cli`: auto-detect CLI model format when provider_model precedes base_url (e.g. `name=provider_model,base_url,api_key`). Now validates that at least one field looks like a URL (http:// or https://) and emits clear error messages on mismatch.
- `freshness_score`: convert `FreshnessFinding` dataclass instances to dicts before storing in result dict, fixing `Object of type FreshnessFinding is not JSON serializable` during report generation.

## [0.5.6] - 2026-06-25

### Added
- `EvalCase.without_skill_assertions`: 独立的 without-skill 断言列表，用于 L2 增益计算的差异化评分。空时回退到 `assertions`（完全向后兼容）
- `model_validator`: 拒绝 `assertions` 和 `without_skill_assertions` 同时为空的 EvalCase
- `Grader.grade_output(mode=)`: keyword-only 参数，按 mode 选择 with-skill 或 without-skill 断言集
- `_normalize_eval_case`: 保留 without_skill_assertions；双空时 fallback 一个最小断言

### Changed
- 生成 prompt 要求 without-skill 的 `not_contains` 使用 ≥3 token 技能专属结构标记（非通用词）
- `minimum-evals.json`: ID=1/3 添加差异化 without_skill_assertions，ID=2 省略以利用 fallback
- `_evaluate_all_assertions` 改为 `_evaluate_assertions` 的 backward-compat wrapper

### Fixed
- fail-fast report 模板键名不匹配 (l2_details/l3_details/l4_details)
- 20+ 个预存测试因空断言被 validator 拒绝，已补齐 dummy assertion

## [0.5.5] - 2026-06-24

### Fixed
- SKILL.md: 收紧触发边界 — 增加"不应触发"列表和 4 条精确匹配规则，防止 `skill-cert --help`、`skill-cert-setup`、`certify SKILL.md` 等输入错误触发评测
- SKILL.md: 修正配置检查逻辑 — 任意配置源就绪时直接执行评测，不再阻塞在 setup 引导步骤

## [0.5.3] - 2026-06-23

### Fixed
- `SessionTelemetry.flush()` 缺失导致单模型评测崩溃 — 添加 flush() 代理到 cleanup()
- `drift` 为 None 时 reporter 未防护 — 6 处方法签名改为 `dict | None`，添加 None 守卫
- `StructuredReport.drift` 字段接收 None 导致 Pydantic 校验失败 — 改为空 dict fallback

### Changed
- `Reporter` 类所有 drift 相关参数类型改为 `dict[str, Any] | None`
- `_prepare_drift_data()` 增加 None 默认值返回
