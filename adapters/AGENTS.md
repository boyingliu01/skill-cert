# adapters/ — LLM Provider Adapters

## OVERVIEW
Provider-agnostic LLM adapter layer — implements `ModelAdapter` abstract base class for Anthropic and OpenAI-compatible providers. Engine imports `adapters/` transparently; swap providers without changing pipeline code.

## STRUCTURE
```
adapters/
├── base.py               # Abstract ModelAdapter: chat() + batch_chat() interface
├── anthropic_compat.py   # Anthropic Claude adapter (uses anthropic SDK)
└── openai_compat.py      # OpenAI-compatible adapter (works with OpenAI, Azure, any OpenAI API)
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Define adapter interface | `base.py` | `ModelAdapter` abstract class — all adapters extend this |
| Anthropic Claude | `anthropic_compat.py` | Implements `chat()` + `batch_chat()` with rate limiting |
| OpenAI-compatible | `openai_compat.py` | Uses `openai` SDK — works for OpenAI, Azure, local models |

## CONVENTIONS
- All adapters extend `adapters.base.ModelAdapter`
- Must implement: `chat(messages, system, timeout)` → str, `batch_chat(requests, max_concurrency)` → List[str]
- `batch_chat` defaults to `max_concurrency=5`
- Error handling: exponential backoff for retryable errors, immediate raise for invalid keys
- API keys from environment variables — no hardcoded secrets
