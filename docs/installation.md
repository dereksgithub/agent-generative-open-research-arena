# Installation

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Install from source

```bash
git clone https://github.com/agora-sim/agora.git
cd agora
```

### With uv (recommended)

```bash
uv venv .venv --python 3.12
source .venv/bin/activate    # macOS / Linux
uv pip install -e ".[dev]"
```

### With pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Verify installation

```bash
agora --help
```

You should see the AGORA CLI help message with available commands.

## Optional: LLM provider setup

If you want to use LLM-backed agent reasoning (instead of the default heuristic mode), set the appropriate API key:

```bash
# OpenAI (default provider)
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Or copy the example env file and fill in your keys
cp .env.example .env
```

See [Model Configuration](model-configuration.md) for details on supported providers.

## Dependencies

Core dependencies (installed automatically):

| Package | Purpose |
|---------|---------|
| pydantic >= 2.0 | Scenario schema validation |
| pyyaml >= 6.0 | Scenario file parsing |
| httpx >= 0.27 | Async HTTP for LLM providers |
| python-dotenv >= 1.0 | Environment variable loading |

Dev dependencies (`.[dev]`):

| Package | Purpose |
|---------|---------|
| pytest >= 8.0 | Test runner |
| pytest-asyncio >= 0.23 | Async test support |
| ruff >= 0.4 | Linter |
