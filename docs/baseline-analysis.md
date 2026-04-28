# Skill-Cert Phase 0: Interface Baseline

Date: 2026-04-28
Branch: feature/multi-turn-eval

## EvalRunner

- **File:** `engine/runner.py`
- **Constructor signature:** `__init__(self, max_concurrency: int = 5, rate_limit_rpm: int = 60, request_timeout: int = 120)`
- **Public methods:**
  - `async run_with_skill(self, evals: List[Dict[str, Any]], skill_path: str, model_adapter) -> List[Dict[str, Any]]` — Runs evals with skill context prepended to input. Creates its own `asyncio.Semaphore` + uses `self.limiter`.
  - `async run_without_skill(self, evals: List[Dict[str, Any]], model_adapter) -> List[Dict[str, Any]]` — Runs evals without skill context. Same concurrency/rate-limiting structure.
  - `close(self) -> None` — Shuts down `ThreadPoolExecutor`.
- **Private methods:**
  - `async _run_with_timeout(self, coro, timeout: int)` — Wraps `asyncio.wait_for`.
- **Rate limiting:** Yes — `self.limiter = AsyncLimiter(max_rate=rate_limit_rpm / 60, time_period=1)` (per-instance, created in `__init__`). Each eval acquires via `async with self.limiter`.
- **Concurrency:** `asyncio.Semaphore(self.max_concurrency)` created per method call (not shared across calls).
- **Timeout:** Default `120` seconds, applied per-eval via `_run_with_timeout`.
- **No `run_single_call` method exists.** The closest is the internal closure `run_single_eval` inside `run_with_skill`/`run_without_skill`. There is no standalone public method for a single chat call.

## SkillCertConfig

- **File:** `engine/config.py`
- **`load()` returns:** `SkillCertConfig` instance (classmethod: `@classmethod def load(cls, cli_args=None) -> 'SkillCertConfig'`)
- **How to get model adapter:** **No factory method exists.** `SkillCertConfig` stores `models: List[ModelConfig]` where `ModelConfig` has `base_url`, `api_key`, `model_name`, `fallback_model`. To get an adapter, you must manually instantiate `OpenAICompatAdapter` or `AnthropicCompatAdapter` from a `ModelConfig` object. There is no `config.get_adapter()` or equivalent.
- **Config priority:** CLI args > env vars > config file (`~/.skill-cert/models.yaml`) > defaults.
- **Key fields:** `max_concurrency`, `rate_limit_rpm`, `request_timeout`, `judge_temperature`, `max_testgen_rounds`, `max_gapfill_rounds`, `max_total_time`, `models`.

## Adapters

- **Location:** `adapters/` directory (no `__init__.py`)
- **Available classes:**

| Class | File | Inherits |
|-------|------|----------|
| `ModelAdapter` | `adapters/base.py` | `ABC` (abstract) |
| `OpenAICompatAdapter` | `adapters/openai_compat.py` | `ModelAdapter` |
| `AnthropicCompatAdapter` | `adapters/anthropic_compat.py` | `ModelAdapter` |

- **`chat()` signature (from `ModelAdapter` base):**
  ```python
  @abstractmethod
  def chat(self, messages: List[Dict[str, str]], system: str = None, timeout: int = 120) -> str:
  ```
  - **Important:** This is a **sync** method on the base class. Both implementations handle this:
    - `OpenAICompatAdapter.chat()` — sync wrapper around async `_make_request()` using `asyncio.get_running_loop()` / `loop.run_until_complete()` / `asyncio.run()`.
    - `AnthropicCompatAdapter.chat()` — uses synchronous `requests.Session` directly.

- **`batch_chat()` signature:**
  ```python
  @abstractmethod
  def batch_chat(self, requests: List[Dict[str, Any]], max_concurrency: int = 5) -> List[str]:
  ```

- **`OpenAICompatAdapter.__init__`:**
  ```python
  def __init__(self, base_url: str, api_key: str, model: str, fallback_model: Optional[str] = None, rpm_limit: int = 60)
  ```
  Has its own per-instance `AsyncLimiter(max_rate=rpm_limit, time_period=60)`.

- **`AnthropicCompatAdapter.__init__`:**
  ```python
  def __init__(self, base_url: str, api_key: str, model: str, fallback_model: Optional[str] = None, rpm_limit: int = 60)
  ```
  Uses synchronous `requests.Session`. No rate limiter on the adapter itself.

## aiolimiter

- **Used in:**
  - `engine/runner.py:5,16` — `from aiolimiter import AsyncLimiter`; `self.limiter = AsyncLimiter(max_rate=rate_limit_rpm / 60, time_period=1)`
  - `adapters/openai_compat.py:6,26` — `from aiolimiter import AsyncLimiter`; `self.rate_limiter = AsyncLimiter(max_rate=rpm_limit, time_period=60)`
- **Configuration:**
  - `EvalRunner`: `max_rate = rate_limit_rpm / 60` requests per second, `time_period = 1` second. With default `rate_limit_rpm=60`, this means 1 request per second.
  - `OpenAICompatAdapter`: `max_rate = rpm_limit`, `time_period = 60`. With default `rpm_limit=60`, this means 60 requests per 60 seconds.
  - **They are NOT shared** — each `EvalRunner` and each `OpenAICompatAdapter` creates its own `AsyncLimiter` instance.

## Compatibility Assessment

- [x] **`run_single_call` exists:** **NO** → The actual methods are `run_with_skill()` and `run_without_skill()`, which both batch-process a `List[Dict]`. For multi-turn dialogue, a single-call method or a new multi-turn variant would need to be added.
- [x] **Adapter can be obtained from config:** **NO** → `SkillCertConfig` holds `List[ModelConfig]` but has no factory. Manual instantiation required: `OpenAICompatAdapter(model_cfg.base_url, model_cfg.api_key, model_cfg.model_name, model_cfg.fallback_model)`.
- [x] **Rate limiter can be shared:** **PARTIALLY** → `EvalRunner` has its own `AsyncLimiter` instance. `OpenAICompatAdapter` also has its own. For multi-turn evaluation, if we reuse the same `EvalRunner` instance, its limiter is shared across all evals in that batch. But there is no mechanism to share a limiter across multiple runners or adapters.
- [x] **`chat()` is sync:** **YES (base signature)** → `ModelAdapter.chat()` is declared as sync, not async. `EvalRunner` calls it via `await model_adapter.chat(...)` which works because `OpenAICompatAdapter` returns a coroutine when called from a running event loop (it detects the loop and uses `loop.run_until_complete`). For multi-turn, passing the same `messages` list and mutating it across turns is feasible.

## Key Observations for Multi-Turn Implementation

1. **No existing multi-turn support** — `runner.py` sends a single message list `model_adapter.chat([{"role": "user", "content": ...}])`. Multi-turn would require: (a) accumulating assistant responses, (b) appending to messages, (c) re-sending.

2. **`model_adapter.chat()` is sync** — If multi-turn needs async streaming or multiple sequential awaits, the sync wrapper in `OpenAICompatAdapter` may cause issues. `AnthropicCompatAdapter` is fully sync.

3. **No stateful conversation tracking** — Each eval case is independent. The result dict has `"run": "with-skill"` or `"without-skill"` but no turn-number or conversation-id fields.

4. **`EvalRunner` owns the semaphore + limiter** — Any new multi-turn method should reuse the same pattern for consistency.
