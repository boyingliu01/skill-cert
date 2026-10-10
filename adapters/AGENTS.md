# adapters/ — LLM Provider Adapters

## OVERVIEW
Provider-agnostic LLM adapter layer — implements `ModelAdapter` abstract base class for Anthropic and OpenAI-compatible providers. Engine imports `adapters/` transparently; swap providers without changing pipeline code.

## STRUCTURE
```
adapters/
├── base.py               # TokenUsage / LLMResponse models + abstract ModelAdapter (chat, chat_with_usage, batch_chat)
├── anthropic_compat.py   # Anthropic Claude adapter (uses anthropic SDK)
├── openai_compat.py      # OpenAI-compatible adapter over httpx (OpenAI, Azure, gateways, local models);
│                         # passes response_format through and rejects extra_headers that would
│                         # override an adapter-owned header (authorization, api-key, host, …)
├── factory.py            # create_adapter(model_config) — maps ModelConfig (incl. headers) to an adapter
├── pricing.py            # Model pricing table: 19 entries (Anthropic/OpenAI/Qwen/DeepSeek/Gemini + 2 whalecloud LOCAL at 0)
└── harness/
    ├── base.py           # HarnessAdapter protocol + HarnessRunResult model (sandbox install + non-interactive run)
    ├── opencode_harness.py  # drives `opencode run --format json`, parses the event stream
    └── dsh_harness.py    # dsh backend
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Define adapter interface | `base.py` | `ModelAdapter` abstract class — all adapters extend this |
| Anthropic Claude | `anthropic_compat.py` | Implements `chat()` + `batch_chat()` with rate limiting |
| OpenAI-compatible | `openai_compat.py` | Raw httpx client (not the `openai` SDK) so gateway quirks stay visible |
| Structured (JSON-schema) judge output | `openai_compat.py` | `response_format` is threaded through `chat`/`chat_with_usage`/`batch_chat` |
| Build an adapter from config | `factory.py` | Passes `model_config.headers` in as `extra_headers` |
| Run a task on a real agent runtime | `harness/` | Used by `engine/harness/`, not by the LLM pipeline |

## CONVENTIONS
- All adapters extend `adapters.base.ModelAdapter` — harness backends do not: they satisfy the separate `harness/base.HarnessAdapter` protocol
- Must implement: `chat(messages, system, timeout)` → str, `batch_chat(requests, max_concurrency)` → List[str]
- `batch_chat` defaults to `max_concurrency=5`
- Error handling: exponential backoff for retryable errors, immediate raise for invalid keys
- API keys from environment variables — no hardcoded secrets
