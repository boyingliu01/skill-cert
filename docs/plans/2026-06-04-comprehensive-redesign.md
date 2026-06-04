# Skill-Cert 通盘重构设计方案

**日期**: 2026-06-04
**状态**: **APPROVED** — Delphi Review 共识通过 (2/2 APPROVED, 100%, 2 rounds)
**范围**: 报告结构化输出 + Skill 可观测性 + Token 占用监测

---

## 1. Context

skill-cert v0.3.0 已完成核心引擎（L1-L8 指标、安全扫描、包络线检查、外部集成框架），但存在三个相互关联的结构性缺口：

| 维度 | 现状 | 缺口 |
|------|------|------|
| **报告结构** | JSON 是内联 dict，Markdown 是自由文本列表 | 无 Pydantic 模型、无 Schema 验证、无 eval_details/security_scan 结构化字段 |
| **可观测性** | runner 产生扁平 result dict，无标准化 trace | 评估粒度停留在输出层，缺少中间决策过程记录，无法对接外部可观测工具 |
| **Token 监测** | TokenUsage 仅在 adapter 层，runner 只累计 total | 无 per-eval/per-phase/per-model 分解，无预算告警，无趋势分析 |

**核心洞察**：这三个维度共享同一个数据枢纽 — **ExecutionTrace**。统一设计可以一次到位，避免分三次"伤筋动骨"。

### 需求来源

| 来源 | 内容 |
|------|------|
| REQ-REPORT-001~004 | 结构化 JSON/Markdown 报告、JSON Schema、CLI --format 参数 |
| EVALUATION_REVIEW_2026 P0 | L3 增加过程/轨迹级指标 |
| EVALUATION_REVIEW_2026 P1 | 操作包络线检查（已实现），效率指标 |
| TOOLCHAIN_LANDSCAPE_2026 | 推荐组合架构中 runner.py 需增加效率追踪 |
| specification-v2.yaml | execution-trace.schema.json 数据契约（已定义未实现） |
| Open Issue: 可观测性 | 执行追踪、中间决策评估、OpenTelemetry 对齐 |
| Open Issue: Token 监测 | per-eval/per-phase/per-model 分解、预算告警 |

---

## 2. 架构设计

### 2.1 数据流全景

```
runner._run_single()
  │
  ├─► ExecutionTrace (Pydantic model)
  │     ├─ events: list[TraceEvent]  ← 每步时间线
  │     ├─ token_usage: TokenAccounting  ← 分层 token 分解
  │     └─ metadata: dict  ← 扩展点
  │
  ├─► TokenLedger (per-eval token 账本)
  │     ├─ by_phase: {with_skill, without_skill, grading, judge}
  │     ├─ by_model: {model_name: TokenAccounting}
  │     └─ by_eval: {eval_id: TokenAccounting}
  │
  └─► EventBus (可选, OpenTelemetry 对齐)
        ├─ emit(trace_event)
        └─ exporters: [JSONFileExporter, OTLPExporter?]
              │
              ▼
        reporter.generate_report()
          ├─ StructuredReport (Pydantic) ← 消费 trace + ledger
          ├─ Jinja2 Markdown
          └─ JSON Schema 验证
```

### 2.2 核心模型关系

```
ExecutionTrace
  ├── TraceEvent (timestamp, type, data)
  │     types: TurnStart | ToolCall | ToolResult | StepComplete | LLMCall
  ├── TokenAccounting (input, output, total, cost, model)
  └── EnvelopeSnapshot (steps, tool_calls, tokens, time_ms, cost)

TokenLedger (聚合器)
  ├── phase_totals: dict[str, TokenAccounting]
  ├── model_totals: dict[str, TokenAccounting]
  ├── eval_totals: dict[str, TokenAccounting]
  └── budget_alerts: list[BudgetAlert]

StructuredReport (报告模型, 基础已 Delphi APPROVED)
  ├── metadata, verdict_summary, metrics, eval_details
  ├── token_analysis: TokenAnalysisSection  ← 新增
  │     ├── total_tokens, total_cost
  │     ├── by_phase, by_model, by_eval
  │     └── budget_utilization, alerts
  └── observability: ObservabilitySection  ← 新增
        ├── trace_summary (event_count, duration, tool_calls)
        └── trace_export_path (JSONL file reference)
```

### 2.3 与现有架构的兼容性

| 现有组件 | 影响 | 兼容策略 |
|----------|------|----------|
| `runner.py` result dict | 新增 `trace` 字段 | 保留所有原有字段（tokens_used, token_breakdown, execution_time） |
| `metrics.py` `_DictTrace` | 继续工作 | `ExecutionTrace.to_envelope_trace()` 提供兼容接口 |
| `reporter.py` Jinja2 模板 | 重写 | `ImprovementSuggestion.__str__()` 过渡 |
| `adapters/base.py` TokenUsage | 不修改 | TokenAccounting 从 TokenUsage dict 构建 |
| `envelope.py` EnvelopeChecker | 不修改 | ExecutionTrace 适配其属性访问协议 |
| CLI evals.py / multi_skill.py / stress.py | 小幅修改 | format 感知写入 + TokenLedger 注入 |

---

## 3. 分阶段实施计划

### Phase 1: 数据基础层（ExecutionTrace + TokenAccounting）

#### Task 1.1: 新建 `engine/trace_models.py`

Pydantic 模型定义：

```python
class TraceEvent(BaseModel):
    timestamp: float           # time.time()
    event_type: str            # TurnStart|ToolCall|ToolResult|StepComplete|LLMCall|Error
    data: dict[str, Any] = {}  # 事件载荷
    tokens: int = 0            # 该事件的 token 消耗
    latency_ms: float = 0     # 该事件的耗时

class TokenAccounting(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    model: str = ""

    def merge(self, other: "TokenAccounting") -> "TokenAccounting":
        """合并两个 TokenAccounting"""
        ...

class BudgetAlert(BaseModel):
    level: str          # warning | critical
    message: str
    used: float
    budget: float

class ExecutionTrace(BaseModel):
    run_id: str                # UUID
    eval_id: int | str
    phase: str                 # with_skill | without_skill | grading | judge
    events: list[TraceEvent] = []
    token_usage: TokenAccounting = TokenAccounting()
    start_time: float = 0
    end_time: float = 0
    error: str | None = None
    metadata: dict[str, Any] = {}

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000 if self.end_time else 0

    @property
    def step_count(self) -> int:
        return sum(1 for e in self.events if e.event_type == "StepComplete")

    @property
    def tool_call_count(self) -> int:
        return sum(1 for e in self.events if e.event_type == "ToolCall")

    def to_envelope_trace(self):
        """兼容 EnvelopeChecker 的属性访问协议"""
        class _Compat:
            pass
        c = _Compat()
        c.steps = self.step_count
        c.tool_call_count = self.tool_call_count
        c.tokens = self.token_usage.total_tokens
        c.time_ms = self.duration_ms
        c.cost = self.token_usage.cost
        return c
```

#### Task 1.2: 新建 `engine/token_ledger.py`

```python
class TokenLedger:
    """Per-evaluation token accounting aggregator."""

    def __init__(self):
        self._records: list[dict] = []

    def record(self, eval_id: int | str, phase: str, model: str,
               token_usage: dict, cost: float = 0.0) -> None:
        """记录一次 token 消耗"""
        ...

    def get_phase_totals(self) -> dict[str, TokenAccounting]:
        """按 phase 聚合: with_skill / without_skill / grading / judge"""
        ...

    def get_model_totals(self) -> dict[str, TokenAccounting]:
        """按 model 聚合"""
        ...

    def get_eval_totals(self) -> dict[str, TokenAccounting]:
        """按 eval_id 聚合"""
        ...

    def get_summary(self) -> dict:
        """生成完整摘要，供 reporter 消费"""
        return {
            "total_tokens": ...,
            "total_cost": ...,
            "by_phase": {k: v.model_dump() for k, v in self.get_phase_totals().items()},
            "by_model": {k: v.model_dump() for k, v in self.get_model_totals().items()},
            "by_eval": [...],
        }

    def check_budget(self, budget: float) -> list[BudgetAlert]:
        """检查预算告警"""
        ...
```

#### Task 1.3: 改造 `engine/runner.py`

在 `_run_single()` 中注入 trace 收集：

1. 方法入口创建 `ExecutionTrace(run_id=uuid4(), eval_id=..., phase=...)`
2. 记录 `trace.start_time = time.time()`
3. LLM 调用后追加 `TraceEvent(event_type="LLMCall", tokens=total_tokens, latency_ms=...)`
4. 结束时填充 `trace.end_time`, `trace.token_usage`
5. 将 trace 附加到 result: `result["trace"] = trace.model_dump()`
6. 如有 TokenLedger，向其 record

**关键约束**：
- result dict 保留所有原有字段（tokens_used, token_breakdown, execution_time, cost）
- TokenLedger 通过 runner 构造函数可选注入（`token_ledger=None`）
- trace 是纯增量，不影响任何现有逻辑

#### Task 1.4: 改造 `skill_cert/cli/evals.py`

在 `_run_single_phase()` 中：
1. 创建 `TokenLedger` 实例
2. 传入 runner: `EvalRunner(..., token_ledger=ledger)`
3. Phase 结束后 `metrics["token_analysis"] = ledger.get_summary()`
4. 可选：将原始 traces 导出为 `{skill}-traces.jsonl`

---

### Phase 2: 可观测性层（EventBus + Trace Export）

#### Task 2.1: 新建 `engine/observability.py`

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

class EventBus:
    """Simple in-process event bus for trace events."""
    def __init__(self):
        self._handlers: list[Callable] = []

    def subscribe(self, handler: Callable) -> None:
        self._handlers.append(handler)

    def emit(self, event: "TraceEvent") -> None:
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                pass  # 观测性不应影响主流程

class TraceExporter(ABC):
    @abstractmethod
    def export(self, traces: list["ExecutionTrace"], output_path: Path) -> Path:
        ...

class JSONLTraceExporter(TraceExporter):
    """Export traces as JSONL — one JSON object per line."""
    def export(self, traces, output_path):
        path = output_path / "traces.jsonl"
        with open(path, "w") as f:
            for trace in traces:
                f.write(trace.model_dump_json() + "\n")
        return path

class OTLPTraceExporter(TraceExporter):
    """Optional OpenTelemetry export — graceful skip if unavailable."""
    def check_available(self) -> bool:
        try:
            import opentelemetry  # noqa: F401
            return True
        except ImportError:
            return False

    def export(self, traces, output_path):
        if not self.check_available():
            return None  # graceful skip
        # OTLP export logic (future)
        ...
```

#### Task 2.2: CLI 集成

`skill_cert/cli/main.py` 新增参数：
```
--trace-export {jsonl,otlp,none}  (default=jsonl)
--trace-dir DIR                    (default=output_dir)
```

`evals.py` 在报告写入后追加 trace 导出步骤。

---

### Phase 3: 报告结构化输出（已 Delphi APPROVED 基础 + 扩展）

#### Task 3.1: 新建 `engine/report_models.py`

基础模型（已 APPROVED）：
- ReportMetadata, MetricLevelDetail, MetricsSummary, EvalDetailItem
- VerdictSummary, SecurityScanResult, ImprovementSuggestion(__str__)
- BenchmarkInfo, StructuredReport

**新增两个 section**：

```python
class EvalTokenDetail(BaseModel):
    eval_id: int | str
    eval_name: str = ""
    tokens: int
    cost: float
    input_tokens: int = 0
    output_tokens: int = 0

class TokenAnalysisSection(BaseModel):
    total_tokens: int
    total_cost: float
    by_phase: dict[str, TokenAccounting]
    by_model: dict[str, TokenAccounting]
    by_eval: list[EvalTokenDetail]
    budget_utilization: float | None = None
    alerts: list[str] = []

class ObservabilitySection(BaseModel):
    trace_count: int
    total_events: int
    total_duration_ms: float
    tool_call_count: int
    trace_export_path: str | None = None
```

将 `token_analysis` 和 `observability` 作为 `StructuredReport` 的 Optional 字段。

#### Task 3.2: 生成 `schemas/report.schema.json`

由 `StructuredReport.model_json_schema()` 自动导出，不再手写维护。

#### Task 3.3: 改造 `engine/reporter.py`

- **3a**: `_generate_suggestions()` → `list[ImprovementSuggestion]` + `__str__` 过渡
- **3b**: `_build_eval_details(eval_case_meta)` + N/A 兜底
- **3c**: `_build_structured_json()` + security_scan None 检查
- **3d**: Jinja2 模板重写（Metrics Overview 表格, Eval Details 表格, Token Analysis 表格, 建议加优先级）
- **3e**: `generate_report()` JSON 部分替换为 `_build_structured_json()`
- **3f**: `validate_report_schema()` 函数

#### Task 3.4: CLI 参数

```
--format {json,markdown,both}  (default=both)
--json-schema-validate
```

#### Task 3.5: 报告写入逻辑

evals.py, multi_skill.py, stress.py — format 感知 + schema 验证

#### Task 3.6: 辅助修改

- `engine/constants.py`: ReportConstants + SuggestionThresholds
- `pyproject.toml`: jsonschema>=4.18

---

### Phase 4: 测试与验证

#### Task 4.1: 单元测试 (~40 新测试)

| 模块 | 测试文件 | 测试数 | 覆盖要点 |
|------|---------|--------|----------|
| trace_models | test_trace_models.py | 8 | 创建、属性计算、to_envelope_trace 兼容、序列化 |
| token_ledger | test_token_ledger.py | 10 | record、phase/model/eval 聚合、budget alert、空数据 |
| runner trace | test_runner.py 扩展 | 6 | trace 生成、token 事件记录、向后兼容 |
| observability | test_observability.py | 6 | EventBus emit/subscribe、JSONL export、OTLP graceful skip |
| reporter 扩展 | test_reporter.py 扩展 | 10 | token_analysis section、observability section、端到端渲染 |

#### Task 4.2: 端到端验证

1. `pytest` 全量回归（651+ existing + 40 new）
2. `ruff check . && ruff format .`
3. `pip check`
4. 手动运行：
   - `skill-cert --skill SKILL.md --format json --json-schema-validate`
   - `skill-cert --skill SKILL.md --trace-export jsonl`
   - 检查 `{skill}-traces.jsonl` 和 `{skill}-result.json` 中的 token_analysis

---

## 4. 关键文件清单

| 文件 | 操作 | Phase | 说明 |
|------|------|-------|------|
| `engine/trace_models.py` | **新建** | 1 | ExecutionTrace + TraceEvent + TokenAccounting |
| `engine/token_ledger.py` | **新建** | 1 | per-eval/per-phase/per-model token 聚合 |
| `engine/observability.py` | **新建** | 2 | EventBus + TraceExporter |
| `engine/report_models.py` | **新建** | 3 | Pydantic 报告模型（含 token_analysis, observability） |
| `schemas/report.schema.json` | **新建** | 3 | 由 Pydantic 自动生成 |
| `engine/runner.py` | **修改** | 1 | 注入 ExecutionTrace 收集 |
| `engine/reporter.py` | **修改** | 3 | 结构化 JSON + Markdown 表格改造 |
| `engine/constants.py` | **修改** | 3 | ReportConstants + SuggestionThresholds |
| `skill_cert/cli/main.py` | **修改** | 2+3 | --trace-export, --format, --json-schema-validate |
| `skill_cert/cli/evals.py` | **修改** | 1+3 | TokenLedger 集成 + format 感知写入 |
| `skill_cert/cli/multi_skill.py` | **修改** | 3 | format 感知 |
| `skill_cert/cli/stress.py` | **修改** | 3 | format 感知 |
| `pyproject.toml` | **修改** | 3 | jsonschema>=4.18 |
| `tests/test_trace_models.py` | **新建** | 4 | |
| `tests/test_token_ledger.py` | **新建** | 4 | |
| `tests/test_observability.py` | **新建** | 4 | |
| `tests/test_reporter.py` | **修改** | 4 | 扩展 |
| `tests/test_runner.py` | **修改** | 4 | trace 集成测试 |

---

## 5. 设计原则

1. **向后兼容**：result dict 保留原有字段，trace 是新增；顶层 verdict/overall_score 冗余保留
2. **渐进式交付**：4 个 Phase 可独立交付，Phase 1 不依赖 Phase 2/3
3. **零新外部依赖**（Phase 1-2）：Trace 用 Pydantic，EventBus 是纯 Python；OTLP 是可选集成
4. **单一数据源**：ExecutionTrace 同时服务报告、可观测性、token 监测三个消费者
5. **Delphi 共识复用**：Phase 3 完全复用已 APPROVED 的设计（2/2 APPROVED, 100%, 3 rounds），仅扩展两个 section

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| runner.py 改造影响面大 | 所有评测流程 | trace 收集通过组合（非继承），result dict 保持兼容，原有 _DictTrace 继续工作 |
| Pydantic 模型增加报告体积 | JSON 输出变大 | model_dump(exclude_none=True) 控制输出，Optional section 按需包含 |
| JSONL trace 文件过大 | 磁盘占用 | 默认仅导出 summary events，完整 trace 可选 |
| TokenLedger 线程安全 | 并发评测 | per-thread local buffer + phase-end merge（runner 确认使用 ThreadPoolExecutor） |
| 测试数量多（~40 新测试） | 实施周期 | Phase 1-2 先保证基础测试，Phase 3-4 补充报告测试 |
| EventBus 性能 | 高频事件 | 同步 handler，异常记录 logging.error（不再静默吞没） |

---

## 7. 与前序 Delphi Review 的关系

前序设计 `docs/plans/2026-06-04-structured-report-output.md` 已通过 Delphi Review（2/2 APPROVED, 100%, 3 rounds）。本次通盘设计：
- **完全复用**其报告结构化部分（Phase 3 的 Task 3.2~3.6）
- **扩展**两个新 section（TokenAnalysisSection, ObservabilitySection）
- **新增**Phase 1（数据基础）和 Phase 2（可观测性）作为前置支撑
- 已通过新一轮 Delphi Review 评审（2/2 APPROVED, 100%, 2 rounds）

---

## 8. Delphi Review 共识记录

- **Expert A** (glm-5.1, 智谱, 架构师): APPROVED (9/10) — Round 2
- **Expert B** (kimi-k2.6, 月之暗面, 实现工程师): APPROVED (9/10) — Round 2
- **共识比例**: 100% (>= 95% 阈值)
- **状态文件**: `.sprint-state/delphi-reviewed.json`

### 关键修复（Round 1→2 迭代）

| 轮次 | 问题级别 | 问题 | 修复方案 |
|------|---------|------|----------|
| R1 | Critical | Token 数据双写一致性 | ExecutionTrace 为唯一数据源，TokenLedger 改为只读聚合器 aggregate(traces) |
| R1 | Critical | EventBus 异常吞没 | except Exception: pass → logging.error + OTLP 显式指定时 ClickException |
| R1 | Critical | TokenLedger 并发模型 | 确认 ThreadPoolExecutor，per-thread local + phase-end merge |
| R1 | Major | jsonschema 依赖兼容性 | 改用 Pydantic model_validate()，不引入 jsonschema 依赖 |
| R1 | Major | to_envelope_trace() 动态类 | 改为 EnvelopeTraceDTO frozen dataclass |
| R1 | Major | TokenLedger.record() 类型松散 | 因 aggregate() 重构自动解决 |
| R1 | Major | 缺少性能基准测试 | 新增 test_trace_performance.py，10k traces < 1.0s |
| R1 | Minor | TraceEvent.data 过于松散 | 采用 Discriminated Union（LLMCallEvent, ToolCallEvent 等） |
| R1 | Minor | runner.py 侵入性改造 | LLM 调用装饰器拦截 + contextvars trace 生命周期 |
| R1 | Minor | 缺少 schema_version | 新增 schema_version: str = "1.0" |

### 遗留观察（非阻塞）

| 问题 | 处理 |
|------|------|
| record() vs aggregate() API 最终选择 | 实现阶段明确，推荐方案 A（纯只读聚合） |
| OTLP span 映射策略 | Phase 2 实施前定义，observability.py 预留 TODO |
| trace-detail-level 参数 | 延后，schema 预留字段避免 breaking change |
