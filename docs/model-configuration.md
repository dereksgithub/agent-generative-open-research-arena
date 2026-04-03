# Model Configuration

AGORA supports multiple LLM providers for agent reasoning. By default, simulations use heuristic (rule-based) decisions that require no API keys.

## Decision modes

| Mode | Flag | API Key Required | Deterministic | Cost |
|------|------|------------------|---------------|------|
| Heuristic | `--no-llm` (default) | No | Yes (with seed) | Free |
| LLM-backed | `--llm` | Yes | No* | Per-token |

*LLM mode with prompt caching and a fixed seed will produce cached responses on repeat runs.

## Supported providers

| Provider | Alias(es) | Default Model | Env Variable |
|----------|-----------|---------------|--------------|
| OpenAI | `openai`, `gpt` | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `anthropic`, `claude` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| Mistral | `mistral`, `mistral-ai` | `mistral-large-latest` | `MISTRAL_API_KEY` |
| Google Gemini | `gemini`, `google` | `gemini-2.0-flash` | `GOOGLE_API_KEY` |
| DeepSeek | `deepseek` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| MiniMax | `minimax` | `MiniMax-Text-01` | `MINIMAX_API_KEY` |
| Kimi/Moonshot | `kimi`, `moonshot` | `moonshot-v1-auto` | `MOONSHOT_API_KEY` |
| Qwen/DashScope | `qwen`, `dashscope`, `aliyun` | `qwen-max` | `DASHSCOPE_API_KEY` |
| Local (Ollama/vLLM) | `local`, `ollama`, `vllm`, `lmstudio` | `llama3` | — |

## CLI options

```bash
agora run scenario.yaml --llm \
  --llm-provider openai \
  --llm-model gpt-4o \
  --llm-temperature 0.4 \
  --llm-max-tokens 512 \
  --llm-timeout 60.0 \
  --llm-max-retries 2 \
  --llm-max-consecutive-failures 3 \
  --llm-cache-dir .prompt_cache
```

### Key options

**`--llm-provider`**: Provider name or alias (see table above).

**`--llm-model`**: Override the default model for the chosen provider.

**`--llm-temperature`**: Sampling temperature (0.0 = deterministic, 1.0+ = creative). Default: 0.4.

**`--llm-max-tokens`**: Maximum tokens per completion. Default: 512.

**`--llm-max-consecutive-failures`**: After this many consecutive LLM failures, AGORA disables LLM mode for the rest of the run and falls back to heuristic. Default: 3.

**`--llm-cache-dir`**: Directory for prompt caching. Cached responses are reused when the same prompt + model + settings are seen again.

## Using a local model

Run a local model with Ollama, vLLM, or LM Studio:

```bash
# Start Ollama
ollama serve
ollama pull llama3

# Run with local provider
agora run scenario.yaml --llm --llm-provider local --llm-model llama3
```

To use a custom endpoint:

```bash
export LOCAL_LLM_BASE_URL="http://localhost:8000/v1"
agora run scenario.yaml --llm --llm-provider local
```

Or pass the URL directly:

```bash
agora run scenario.yaml --llm --llm-base-url http://localhost:8000/v1
```

## Prompt contract

In LLM mode, each agent decision is a single chat completion call with:

1. **System prompt**: instructs the LLM to respond with a JSON object containing `action`, `target`, `mode`, and `reasoning`.
2. **User prompt**: includes the agent's persona (name, role, traits, values, backstory), current situation (tick, location, goal), available routes with travel times, and active policy interventions.

The LLM must respond with valid JSON. Responses that fail parsing fall back to heuristic mode for that decision.

## Audit logging

Every LLM interaction is logged to the event log (`events.jsonl`):

- `llm_request` — full prompt, settings, and prompt hash
- `llm_response` — response content, token usage, latency, parsed decision
- `llm_error` — error details and whether the error was retryable
- `llm_cache_hit` — cached response reuse
- `llm_disabled` — LLM mode disabled after consecutive failures

Run metadata (`metadata.json`) includes:
- `llm_settings` — temperature, model, provider, etc.
- `llm_accounting` — total tokens, requests, latency, cache hits
- `llm_status` — whether LLM was disabled and why

## Cost control

- Use **heuristic mode** (`--no-llm`) for development and testing — it's free and deterministic.
- Use **prompt caching** (`--llm-cache-dir`) to avoid redundant API calls across runs.
- Set **low temperatures** (0.0-0.4) for more consistent responses.
- Set **`--llm-max-consecutive-failures`** to auto-disable LLM mode if the provider is unreliable.
