"""Supported LLM providers and their default configurations."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    """Static configuration for an LLM provider."""

    name: str
    base_url: str
    env_key: str  # environment variable name for the API key
    default_model: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Registry of known providers
# ---------------------------------------------------------------------------
# Providers that expose an OpenAI-compatible /v1/chat/completions endpoint
# can all share the same client code — only base_url and auth differ.
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        default_model="gpt-4o",
        aliases=("gpt",),
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        env_key="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-20250514",
        aliases=("claude",),
    ),
    "mistral": ProviderConfig(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        env_key="MISTRAL_API_KEY",
        default_model="mistral-large-latest",
        aliases=("mistral-ai",),
    ),
    "gemini": ProviderConfig(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        env_key="GOOGLE_API_KEY",
        default_model="gemini-2.0-flash",
        aliases=("google",),
    ),
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
    ),
    "minimax": ProviderConfig(
        name="minimax",
        base_url="https://api.minimax.chat/v1",
        env_key="MINIMAX_API_KEY",
        default_model="MiniMax-Text-01",
    ),
    "kimi": ProviderConfig(
        name="kimi",
        base_url="https://api.moonshot.cn/v1",
        env_key="MOONSHOT_API_KEY",
        default_model="moonshot-v1-auto",
        aliases=("moonshot",),
    ),
    "qwen": ProviderConfig(
        name="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        default_model="qwen-max",
        aliases=("dashscope", "aliyun"),
    ),
    "local": ProviderConfig(
        name="local",
        base_url="http://localhost:11434/v1",  # overridden by LOCAL_LLM_BASE_URL
        env_key="",  # no auth required for local
        default_model="llama3",
        aliases=("ollama", "vllm", "lmstudio"),
    ),
}

# Build a reverse lookup: alias → canonical provider name
ALIAS_MAP: dict[str, str] = {}
for _name, _cfg in PROVIDERS.items():
    ALIAS_MAP[_name] = _name
    for _alias in _cfg.aliases:
        ALIAS_MAP[_alias] = _name


def resolve_provider(name: str) -> ProviderConfig:
    """Resolve a provider name or alias to its config. Raises KeyError if unknown."""
    canonical = ALIAS_MAP.get(name.lower())
    if canonical is None:
        raise KeyError(
            f"Unknown provider '{name}'. "
            f"Available: {', '.join(sorted(ALIAS_MAP.keys()))}"
        )
    return PROVIDERS[canonical]
