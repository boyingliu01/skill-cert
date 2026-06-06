"""Delphi Review Round 2 — Fix Report + Re-review.

Present the fix report addressing all R1 issues to both experts.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_KEY = "ailab_YL+F7NNalGHNiJUHB46TaCAiMPJk2Q9PrgOcdm2aSqbEHUtxgnQjudORt2Z5BxP2BZ/qMmtBdRHHxCg6rcDlWf+CpV6em2iubEdJzVy5AiDQ"
PROXY_URL = "https://lab.iwhalecloud.com/gpt-proxy"
OUTPUT_DIR = Path(".sprint-state/phase-outputs")

EXPERT_A_REVIEW = (OUTPUT_DIR / "delphi-r1-expert-A.md").read_text(encoding="utf-8")
EXPERT_B_REVIEW = (OUTPUT_DIR / "delphi-r1-expert-B.md").read_text(encoding="utf-8")

FIX_REPORT = """# 修复报告 — Round 1 问题修复方案

## Critical Issues 修复

### C1: Token 数据双写一致性（Expert A #1 + Expert B #2）

**问题**：ExecutionTrace.token_usage 和 TokenLedger.record() 存在双写路径，可能导致数据不一致。

**修复方案**：**确立 ExecutionTrace 为唯一数据源，TokenLedger 为只读聚合器**。
- `ExecutionTrace.token_usage` 是每次 LLM 调用后的唯一写入点（由 runner._run_single 负责）
- `TokenLedger` 不再接受手动 `record()` 调用，改为 `TokenLedger.aggregate(traces: list[ExecutionTrace])` 方法
- 聚合逻辑：遍历 traces，按 phase/model/eval_id 分组，从 `trace.token_usage` 读取数据
- 消除 `TraceEvent.tokens` 字段（事件级 token 记录），token 数据只在 `ExecutionTrace.token_usage` 中记录
- `TraceEvent` 仅记录时间线事件（类型、时间戳、延迟），不承担 token 计量职责

```python
class TokenLedger:
    def aggregate(self, traces: list[ExecutionTrace]) -> None:
        \"\"\"从 ExecutionTrace 列表聚合 token 数据（只读消费）。\"\"\"
        for trace in traces:
            key_phase = trace.phase
            key_model = trace.token_usage.model
            key_eval = str(trace.eval_id)
            # 聚合到 phase_totals / model_totals / eval_totals
            ...
```

### C2: EventBus 异常处理改为日志记录（Expert A #2 + Expert B #3）

**问题**：`except Exception: pass` 导致静默数据丢失。

**修复方案**：
- `EventBus.emit()` 改为 `except Exception as e: logging.error(f"EventBus handler failed: {e}", exc_info=True)`
- `OTLPTraceExporter.export()` 在依赖不可用时：
  - 若用户显式指定 `--trace-export otlp`：抛出 `click.ClickException("opentelemetry not installed. Run: pip install opentelemetry-api")`
  - 若为默认行为：记录 `logging.warning("OTLP export skipped: opentelemetry not installed")` 并返回 None
- CLI 层在调用 exporter 前增加 `check_available()` 前置检查

### C3: TokenLedger 并发模型明确化（Expert A #3 + Expert B #1）

**问题**：threading.Lock 与 runner 实际并发模式可能不匹配。

**修复方案**：
- runner 的并发模型已确认为 **ThreadPoolExecutor**（同步线程池），非 asyncio/multiprocessing
- `TokenLedger` 采用 **per-thread local + phase-end merge** 策略：
  ```python
  import threading
  class TokenLedger:
      def __init__(self):
          self._local = threading.local()
          self._lock = threading.Lock()
          self._records: list[dict] = []

      def record(self, ...):
          # 每个线程先写入 thread-local buffer
          if not hasattr(self._local, 'buffer'):
              self._local.buffer = []
          self._local.buffer.append({...})

      def flush(self):
          # Phase 结束时调用，合并所有线程的 buffer
          # 在 ThreadPoolExecutor.shutdown() 后调用
          ...
  ```
- 文档明确声明：`TokenLedger` 仅支持 `threading` 并发模型（与 runner.py 一致）
- 如未来切换到 asyncio，需改用 `asyncio.Lock` + per-task buffer

---

## Major Concerns 处理

### M1: jsonschema 依赖兼容性（Expert B #1）

**修复方案**：**使用 Pydantic 内置验证替代 jsonschema**。
- `validate_report_schema()` 改为使用 `StructuredReport.model_validate(json_data)` 进行验证
- 不再引入 `jsonschema>=4.18` 依赖
- `schemas/report.schema.json` 仍由 `model_json_schema()` 导出（供外部工具消费），但内部验证不依赖它
- pyproject.toml 不新增 jsonschema 依赖

### M2: to_envelope_trace() 兼容层改为显式 DTO（Expert A #4 + Expert B #2）

**修复方案**：
- 删除动态 `_Compat` 类
- 新增 `EnvelopeTraceDTO` dataclass：
  ```python
  from dataclasses import dataclass
  @dataclass(frozen=True)
  class EnvelopeTraceDTO:
      steps: int
      tool_call_count: int
      tokens: int
      time_ms: float
      cost: float
  ```
- `ExecutionTrace.to_envelope_trace() -> EnvelopeTraceDTO`
- 在测试中验证 `EnvelopeChecker.check(trace.to_envelope_trace())` 正常工作
- 在 `EnvelopeChecker` 文档中标注 `_DictTrace` 为 deprecated

### M3: TokenLedger.record() 参数类型强化（Expert B #3）

**修复方案**：由于 C1 已将 TokenLedger 改为只读聚合器，`record()` 方法被 `aggregate(traces)` 替代，此问题自动解决。不再接受松散的 `dict` 参数。

### M4: 补充性能基准测试（Expert B #4）

**修复方案**：Phase 4 测试计划新增 `test_trace_performance.py`：
- 1000 事件追加到 ExecutionTrace.events 的内存和耗时
- TokenLedger.aggregate() 处理 10k traces 的耗时
- EventBus.emit() 100 handlers 的吞吐量
- 目标：单次 aggregate(10k traces) < 1.0s

---

## Minor Concerns 说明

| # | 问题 | 处理 |
|---|------|------|
| m1 | TraceEvent.latency_ms 精度 | 采纳：改用 `time.perf_counter()` 测量延迟，`timestamp` 仍用 `time.time()` 记录绝对时间 |
| m2 | BudgetAlert.level 改 Literal | 采纳：`level: Literal["warning", "critical"]` |
| m3 | --trace-export 默认 jsonl 的磁盘 I/O | 采纳：新增 `--no-trace-export` 参数可关闭 |
| m4 | ExecutionTrace 缺 schema_version | 采纳：新增 `schema_version: str = "1.0"` 字段 |
| A-7 | 时间戳标准化 | 采纳：duration 用 perf_counter，timestamp 用 datetime.utcnow() |
| A-8 | OTLP span 映射策略 | 延后：Phase 2 实施前定义，当前标注为 TODO |
| A-9 | trace-detail-level 参数 | 延后：Phase 2 后续迭代 |
| A-10 | 旧 Reporter 废弃路径 | 采纳：本版本直接重写 Jinja2 模板，旧测试同步更新 |
| A-5 | TraceEvent.data 改为 Discriminated Union | 采纳：Phase 1 实施时使用 Union[LLMCallEvent, ToolCallEvent, ...] |
| A-6 | runner.py 用装饰器模式 | 部分采纳：LLM 调用用装饰器拦截，trace 生命周期用 contextvars 管理 |
"""

EXPERTS = {
    "A": {"model": "glm-5.1", "provider": "Zhipu (GLM)", "role": "架构师"},
    "B": {"model": "kimi-k2.6", "provider": "Moonshot (Kimi)", "role": "实现工程师"},
}

PROMPT_TEMPLATE = """你正在参与 Delphi Review Round 2。

Round 1 中你（以及其他专家）对通盘重构设计方案提出了问题。现在作者提交了修复报告。

===== 原始设计文档 =====
{design_doc}

===== 你的 Round 1 评审 =====
{your_review}

===== 修复报告 =====
{fix_report}

请评估修复报告是否充分解决了你提出的所有问题。

请按以下格式输出：
## Round 2 Response

### 响应修复报告
**你的 Critical Issues 修复评估**：
1. C? [问题]: [已修复/未完全修复] — 理由: [...]

**你的 Major Concerns 处理评估**：
1. M? [问题]: [已修复/已接受] — 理由: [...]

### 更新后裁决: [APPROVED / REQUEST_CHANGES]
### 更新后置信度: [X/10]
### 立场变化说明（如有）

最后输出 JSON：
```json
{{"expert_id": "{expert_id}", "round": 2, "verdict": "APPROVED|REQUEST_CHANGES", "confidence": X, "resolved_issues": ["..."], "remaining_issues": ["..."], "consensus_report": {{"agreed_items": ["..."], "final_verdict": "APPROVED|REQUEST_CHANGES"}}}}
```"""


def call_model(model, prompt):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位严谨的技术评审专家。请用中文回答。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    try:
        resp = httpx.post(
            f"{PROXY_URL}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def main():
    design_doc = Path("docs/plans/2026-06-04-comprehensive-redesign.md").read_text(encoding="utf-8")

    print("=" * 60)
    print("Delphi Review — Round 2: Fix Report Re-review")
    print("=" * 60)

    results = {}
    for eid, info in EXPERTS.items():
        print(f"\n--- Expert {eid} ({info['model']}, {info['provider']}) ---")

        your_review = EXPERT_A_REVIEW if eid == "A" else EXPERT_B_REVIEW
        prompt = PROMPT_TEMPLATE.format(
            design_doc=design_doc,
            your_review=your_review,
            fix_report=FIX_REPORT,
            expert_id=eid,
        )

        start = time.time()
        response = call_model(info["model"], prompt)
        elapsed = time.time() - start

        print(f"  Response: {elapsed:.1f}s ({len(response)} chars)")

        output_file = OUTPUT_DIR / f"delphi-r2-expert-{eid}.md"
        output_file.write_text(
            f"# Delphi Review Round 2 — Expert {eid}\n\n"
            f"**Model**: {info['model']} ({info['provider']})\n"
            f"**Timestamp**: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n{response}\n",
            encoding="utf-8",
        )
        print(f"  Saved: {output_file}")

        # Extract verdict
        verdict = "UNKNOWN"
        confidence = 0
        try:
            json_start = response.rfind('{"expert_id"')
            if json_start >= 0:
                json_str = response[json_start:]
                depth = 0
                for i, c in enumerate(json_str):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            vdata = json.loads(json_str[:i+1])
                            verdict = vdata.get("verdict", "UNKNOWN")
                            confidence = vdata.get("confidence", 0)
                            break
        except Exception:
            pass

        if verdict == "UNKNOWN":
            for line in response.split("\n"):
                if "APPROVED" in line.upper() and "REQUEST" not in line.upper() and "CONDITIONALLY" not in line.upper():
                    verdict = "APPROVED"
                    break
                elif "REQUEST_CHANGES" in line.upper():
                    verdict = "REQUEST_CHANGES"

        results[eid] = {"verdict": verdict, "confidence": confidence, "model": info["model"]}
        print(f"  Verdict: {verdict} (confidence: {confidence}/10)")

    # Summary
    print("\n" + "=" * 60)
    print("Round 2 Summary")
    print("=" * 60)
    for eid, r in results.items():
        print(f"  Expert {eid} ({r['model']}): {r['verdict']} ({r['confidence']}/10)")

    verdicts = [r["verdict"] for r in results.values()]
    all_approved = all(v == "APPROVED" for v in verdicts)
    print(f"\n  Consensus: {'ALL APPROVED' if all_approved else 'DIVERGENT — ' + str(verdicts)}")

    summary = {
        "round": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experts": results,
        "consensus": "ALL APPROVED" if all_approved else "DIVERGENT",
    }
    summary_file = OUTPUT_DIR / "delphi-round2.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Summary saved: {summary_file}")

    return 0 if all_approved else 1


if __name__ == "__main__":
    sys.exit(main())
