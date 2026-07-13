# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.14.0] - 2026-07-13

### Added — Instruction-Type Skill Parser Extension (Issue #84)
- **engine/analyzer.py**: Extended `_detect_skill_type()` to recognize instruction-type skills (Phase 1 → Phase 2 → ... workflows). Added `_extract_instruction_patterns()` for regex-based phase/step extraction from structured headings. Integrated fallback detection in `parse_skill_md()` for unclassified skills.
- **SkillSpec**: New `instruction_type` field with confidence scoring.
- **Tests**: 63 new tests in `test_analyzer.py` covering instruction-type detection, false-positive prevention, confidence scoring, reference merging, mixed phase formats, and backward compatibility.
- **Design spec**: `docs/superpowers/specs/2026-07-10-instruction-type-parser-design.md` (Delphi review APPROVED, 95% consensus).

### Added — Documentation
- **archy.yaml**: Clean Architecture layer boundary configuration (domain/infrastructure/presentation/support layers).
- **docs/retrospective-v0.13.1.md**: Project retrospective covering 75 days of development (2026-04-26 to 2026-07-09).
- **improvements/**: Methodology improvement proposals from delphi-review evaluation.

## [0.13.0] - 2026-07-09

### Added — Report 5-Dimension Enhancement (Issue #71)
- **engine/constants.py**: Added `METRIC_METADATA` dictionary with purpose + method strings for all 12 metrics (L1-L8, drift, security, cost, reliability) in Chinese.
- **engine/report_models.py**: Added `MetricAnalysis` Pydantic model with metric_name, purpose, method, result_summary, analysis, and suggestions fields.
- **engine/reporters/builders.py**: Added `build_metric_analysis()` deterministic function with per-metric analysis rules (L1 fp/fn bias detection, L2 low-gain warning, L4 single-run N/A, drift single-model skip).
- **engine/reporters/generator.py**: Jinja2 template upgraded to 5-dimension format (评测目的/评测方法/评测结果/分析/改进建议) for all metric sections.
- **Tests**: 32 new builder tests, 10 new constants tests, 6 new report model tests.

### Added — Exclusion Scenarios Detection (Issue #75 P1)
- **engine/gotchas_analyzer.py**: Added `analyze_exclusion_scenarios()` with English and Chinese exclusion pattern matching. Scores description coverage (0-100) based on exclusion phrase count.
- **Tests**: 14 new exclusion scenario tests (empty, single/multiple matches, Chinese keywords, case insensitivity).

### Changed — SKILL.md Restructuring (Issues #76, #82)
- **SKILL.md**: Restructured from 278-line monolithic file to 38-line router with description exclusion clause ("Do NOT trigger for: code reviews, sprint progress checks...").
- **references/**: 6 new reference files extracted from original SKILL.md (setup, evaluation-flow, metrics, output-format, anti-patterns, examples).
- **tools.md**: New tool allowlist with dangerous tool restrictions.
- **engine/analyzer.py**: Added `_load_references()` for multi-file skill loading, backward-compatible (no references/ directory = no change). Added `references` field to `SkillSpec`.
- **Tests**: 6 new analyzer tests for references loading, backward compatibility, file filtering.

### Fixed — Code Quality
- **engine/hooks_detector.py**: Removed unused `total_hooks` variable.
- **engine/reporters/builders.py**: Removed unused `wos` variable. Fixed E501 line length violations.
- **engine/constants.py**: Fixed all E501 line length violations via string concatenation.
- **engine/gotchas_analyzer.py**: Removed unused `Path` and `Any` imports. Fixed E501 in GOTCHA_PATTERNS.
- **tests/test_builders.py**: Removed unused `pytest` import.
- **ruff**: 0 errors, 0 warnings across all project files.

## [0.11.3] - 2026-07-05

### Added — Progressive Disclosure Phase 0.5 Gate (Issue #72)
- **engine/progressive_disclosure.py**: Added CJK-aware token counting (`_count_tokens` now handles CJK at ~1.5 chars/token vs 4 chars/token for ASCII). New `analyze_structure_quality()` for SKILL.md line count, routing table detection, and router pattern analysis. Removed duplicate `analyze_description_quality` (moved to `engine/maintainability.py`).
- **skill_cert/cli/evals.py**: Phase 0.5 gate runs `progressive_disclosure_test()` before Phase 1, storing results in `spec["progressive_disclosure"]` for downstream report generation.
- **engine/reporters/generator.py**: JSON report now includes `progressive_disclosure` field when available.
- **Tests**: 1453 total (8 new for structure quality).

### Added — Report Metrics Five-Field Enhancement (Issue #71)
- **engine/report_models.py**: New `MetricDimension` Pydantic model with `purpose`/`method`/`result`/`analysis`/`improvement` fields. `MetricsSection` extended with `l1_detail` through `l8_detail`.
- **engine/reporters/builders.py**: 8 new `_build_l*_detail()` functions generating meaningful per-metric analysis. `build_metrics_section()` refactored to wire all details.

### Added — Description Quality Analysis (Issue #73)
- **engine/maintainability.py**: New `analyze_description_quality()` evaluating WHAT/WHEN/trigger words/exclusion/third-person checks. `DescriptionQualityResult` dataclass with 0-100 scoring.

### Added — Structure Quality Analysis (Issue #74)
- **engine/structure_quality.py** (new): `check_tool_permission()` for tools.md whitelist validation + dangerous tool pattern detection. `check_script_usage()` for scripts/ directory discovery.
- **tests/test_structure_quality.py** (new): 8 test cases covering tool permission, script usage, edge cases.

## [0.11.2] - 2026-07-03

### Fixed — Pre-existing pyright type errors (5 files)
- **engine/integrations.py**: Added `# type: ignore[import-not-found]` for optional `skill_lab` and `deepeval` imports.
- **engine/observability.py**: Added `# type: ignore[import-not-found]` for optional `opentelemetry` import.
- **engine/security_probes.py**: Added `None` guard on `_dispatcher.run_all()` call (type safety).
- **skill_cert/cli/dialogue.py**: Fixed `judge_callback=primary_adapter` -> `primary_adapter.chat` (type mismatch).
- **scripts/run_uat.py**: Added `# type: ignore[arg-type]` on `grade_output()` call (EvalCase type collision).

### Changed — Architecture config rewritten for archy Python tool
- **architecture.yaml**: Switched from old xp-gate/archlinter format to [archy](https://github.com/hslee16/Archy) format. Layers mapping + forbid rules, excluding tests/build/scripts/results. Verified: 0 layer violations.

### Changed — Ruff formatting cleanup (24 files)
- Bulk `ruff format` applied across `engine/`, `adapters/`, `skill_cert/`, `tests/`.

## [0.11.1] - 2026-07-03

### Fixed — Parallel test race condition in test_config.py (#67)
- **FS race in file-based config tests**: Three tests (`test_provider_model_in_file_config` file-loading section, `test_config_from_file_with_error`, `test_config_from_file_with_malformed_yaml`) all wrote to the same shared path `{tempdir}/.skill-cert/models.yaml`, causing non-deterministic `FileNotFoundError` failures under `pytest --fast` parallel execution.
- **Fix**: Each test now creates its own temp dir via `tempfile.mkdtemp()` with unique paths. Cleanup uses `shutil.rmtree` in `finally` blocks.
- **Rename**: `test_config_from_file_with_error` → `test_config_from_file_with_valid_yaml` (the YAML was valid, not an error case).
- **Total tests**: 1445 (1 new from splitting inlined file-loading into dedicated test).

## [0.11.0] - 2026-07-03

### Changed — Project-level quality gates migrated to global hooksPath
- Removed project-level `.git/pre-commit` and `.git/pre-push` hooks
- Set `core.hooksPath` globally to `~/.config/xp-gate/hooks/`
- Synced global hooks adapters directory with latest versions

## [0.8.2] - 2026-06-30

### Fixed — Coverage Scoring Over-Penalization (#66)
- **Mixed-type assertion examples**: Generation prompt now includes `contains`, `json_valid`, and `regex` examples in both trigger and normal sections. LLMs previously emitted all-regex assertions because all examples were regex.
- **Remove diversity penalty**: The keyword-blacklist penalty (`diversity_penalty = 1.0 - filtered_ratio * 6.0`) falsely penalized correctly-filtered anti-slop assertions. Removed entirely — type diversity factor alone is sufficient.
- **Soften type diversity factor**: Changed from `avg_types / 2.0` (severe: 0.5 at 1 type) to `0.5 + 0.5 * avg_types / 2.0` (gentle: 0.75 baseline). Single-type assertion cases no longer cut coverage in half.
- **Impact**: delphi-review skill coverage rose from 0.25 → 0.50 with the same eval cache.

## [0.8.1] - 2026-06-30

### Fixed — TestGen Timeout Resilience (#65)
- **gap-fill timeout**: Use `TestGenLimits.GAP_FILL_TIMEOUT` (now 300s) even when no deadline object is present. Previously single mode ran with no explicit timeout, defaulting to adapter-level 120s.
- **gap-fill retry**: Add 1 automatic retry on gap-fill failure before returning empty. Reduces false-negative coverage results when LLM API is temporarily slow.
- **review_evals timeout**: Chat call in `review_evals` now passes explicit timeout parameter. Prevents hanging on slow review responses.
- **MockModelAdapter**: Accept `**kwargs` in `chat()` to match real adapter signature.

## [0.8.0] - 2026-06-29

### Changed — L4 Statistical Method Upgrade (#62)
- **Bootstrap CI**: Replaced t-distribution CI with percentile Bootstrap resampling (10k resamples) in `engine/stability.py`. Falls back to t-distribution for n<3. More accurate for small samples and non-normal distributions.
- **min_samples enforcement**: L4 now requires >=5 runs (`MIN_SAMPLES_FOR_L4=5`). Fewer runs produces `l4_execution_stability=None` with clear warning. `DEFAULT_RUNS` raised from 1 to 5.
- **Method unification**: `_calculate_l4_execution_stability()` in `metrics.py` now emits deprecation warning when used without multi-run data. CI history path preserved as alternative data source.
- **CLI integration**: `_calculate_metrics_with_stability()` handles `None` from Bootstrap L4 gracefully.

### Fixed
- **#57 closed** — skill_type detection (cli_tool/library/agent_guide) fully implemented and tested in v0.6.x.

## [0.7.0] - 2026-06-29

### Added — Evaluation Quality Hardening
- **TestGen JSON robustness (#58)**: Multi-retry (up to 3 attempts) with progressive hint escalation in `EvalGenerator.generate_initial_evals()`. Added `_repair_json_trailing_commas()` static method ported from grader.py to fix trailing comma LLM errors before every `json.loads` call. +4 new tests.
- **Calibration pipeline integration (#60)**: `StructuredReport` now has explicit `calibration` field (not just extras). Markdown report renders calibration section (Agreement Rate, Cohen's Kappa, FPR/FNR). New `templates/golden-evals.json` with 10 sample cases. +2 new tests.
- **SKILL.md freshness tracking (#63)**: Added `version`, `last_updated`, `engine_version_min` to skill-cert's own SKILL.md frontmatter. Freshness score now detects version.

### Changed
- **Security probe count documented (#64)**: `constants.py` PATTERN_COUNT updated 52→80. README and AGENTS.md docs synced to 80.

### Fixed
- **#61, #59 closed** — L2 zero-guard already in v0.6.2; reporter.py already decomposed to 3 modules.

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
