# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.3] - 2026-06-23

### Fixed
- `SessionTelemetry.flush()` 缺失导致单模型评测崩溃 — 添加 flush() 代理到 cleanup()
- `drift` 为 None 时 reporter 未防护 — 6 处方法签名改为 `dict | None`，添加 None 守卫
- `StructuredReport.drift` 字段接收 None 导致 Pydantic 校验失败 — 改为空 dict fallback

### Changed
- `Reporter` 类所有 drift 相关参数类型改为 `dict[str, Any] | None`
- `_prepare_drift_data()` 增加 None 默认值返回
