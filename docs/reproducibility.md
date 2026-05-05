# Reproducibility

AGORA is designed for research use, where reproducibility is essential. This document explains how AGORA achieves deterministic outputs and what its limitations are.

## Seed-based determinism

Every AGORA run accepts a `--seed` integer. When the same scenario, seed, and decision mode are used, the simulation produces byte-identical outputs.

```bash
agora run scenario.yaml --seed 42 --output-dir run_a
agora run scenario.yaml --seed 42 --output-dir run_b
diff run_a/decisions.jsonl run_b/decisions.jsonl
# No differences
```

### How seeding works

1. The **master seed** is passed to the simulation engine.
2. Each agent receives a **derived seed**: `master_seed + agent_index`.
3. Agent-local RNG is used for tie-breaking when multiple routes have equal cost.
4. The **run ID** is a deterministic hash of `scenario_id | seed | strategy_name`.

### What is deterministic

In heuristic mode (default):

| Component | Deterministic? |
|-----------|---------------|
| Agent decisions | Yes |
| Decision ordering | Yes (agents processed in definition order) |
| Event log | Yes |
| KPI values | Yes |
| Run ID | Yes |
| Output file contents | Yes |

### What is NOT deterministic

| Component | Why |
|-----------|-----|
| LLM responses | API providers may return different completions |
| Output directory timestamps | Based on wall clock |
| Metadata `agora_version` | Tracks the installed version |

## Golden-run fixtures

AGORA maintains golden-run fixtures in `engine/tests/fixtures/`. These are reference outputs for specific scenario + seed combinations. The CI test suite verifies that the current engine produces identical outputs.

If you change the simulation engine in a way that alters outputs, you must regenerate the fixtures:

```bash
# Example: regenerate the morning commute fixture intentionally
agora run scenarios/examples/morning_commute.yaml --seed 42 --output-dir /tmp/agora_golden
cp /tmp/agora_golden/decisions.jsonl engine/tests/fixtures/morning_commute_seed42.jsonl

# Then rerun the golden tests
pytest engine/tests/test_golden.py -v
```

Current golden fixtures:
- `morning_commute_seed42.jsonl` — morning commute scenario, seed 42
- `vaccine_uptake_seed7.jsonl` — vaccine uptake scenario, seed 7

## Run artifacts for audit

Every run produces a self-contained output directory with everything needed to understand and reproduce the run:

| File | Purpose |
|------|---------|
| `scenario.yaml` | Exact copy of the input scenario |
| `config.json` | Resolved config including effective seed and AGORA version |
| `metadata.json` | Run metadata: seed, run_id, agent/tick counts, LLM settings |
| `decisions.jsonl` | Complete decision trace |
| `events.jsonl` | Full event log with stable sequential IDs |
| `kpis.json` | Evaluated KPI values |

## Reproducibility with LLM mode

LLM-backed runs are inherently non-deterministic because API providers may return different completions for the same prompt. AGORA provides tools to manage this:

1. **Prompt caching**: Enable with `--llm-cache-dir`. Cached responses are keyed by the full prompt context + model + settings. A cached run will produce identical outputs.

2. **Audit logging**: Every LLM interaction is logged with the prompt hash, response content, token usage, and latency. This allows post-hoc analysis of model behavior.

3. **Fallback recording**: When LLM calls fail, the fallback to heuristic mode is recorded in decision metadata (`decision_source: "llm_error"` or `"llm_disabled"`).

## Comparing runs

To compare two runs:

```bash
# Compare decisions
diff run_a/decisions.jsonl run_b/decisions.jsonl

# Compare KPIs
python -c "
import json
a = json.load(open('run_a/kpis.json'))
b = json.load(open('run_b/kpis.json'))
for k in a['kpis']:
    print(f\"{k}: {a['kpis'][k]['overall']} vs {b['kpis'][k]['overall']}\")
"
```

## Version pinning

For long-term reproducibility, pin AGORA to a specific git commit or release tag in your research environment.

Example:

```bash
git clone https://github.com/agora-sim/agora.git
cd agora
git checkout <commit-or-tag>
uv pip install -e ".[dev]"
```

Record both the git revision and the `config.json` output for every run. `config.json` captures the AGORA version string used to produce the run, while the git revision identifies the exact source snapshot.
