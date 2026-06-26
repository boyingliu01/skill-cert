# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
