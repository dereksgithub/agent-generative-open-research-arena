# Quickstart

This guide walks you through running your first AGORA simulation in under five minutes.

## 1. Run the example scenario

AGORA ships with example scenarios in `scenarios/examples/`. Run the morning commute scenario:

```bash
agora run scenarios/examples/morning_commute.yaml --seed 42
```

This runs a 24-tick transport simulation with 5 agents navigating a commute under a congestion charge policy.

## 2. Inspect the output

The run produces a timestamped output directory under `runs/morning_commute/`:

```
runs/morning_commute/<timestamp>/
├── scenario.yaml        # Copy of the input scenario
├── config.json          # Resolved config (scenario + seed + version)
├── decisions.jsonl      # One decision per agent per tick
├── aggregate.csv        # Per-tick summary statistics
├── events.jsonl         # Full structured event log
├── metadata.json        # Run metadata (seed, run_id, counts)
├── agent_states.jsonl   # Per-tick agent state snapshots
├── narratives.jsonl     # Agent decision reasoning
├── agent_summary.csv    # Per-agent aggregate stats
└── kpis.json            # Evaluated KPI values
```

## 3. Explore the results

**Decisions**: Each line in `decisions.jsonl` is one agent decision:

```json
{"tick": 8, "agent_id": "alice", "action": "travel", "target": "town_centre", "reasoning": "I want to reach town_centre. Choosing transit based on my preferences and current conditions. Active policies affect costs: {'drive': 2.5}.", "metadata": {"mode": "transit"}}
```

**Aggregates**: `aggregate.csv` shows per-tick travel vs. stay counts:

```csv
tick,travel_count,stay_count,total_agents
7,5,0,5
8,5,0,5
```

**KPIs**: `kpis.json` contains scenario-defined key performance indicators:

```json
{
  "kpis": {
    "transit_share": {
      "name": "Transit Mode Share",
      "overall": 0.2917,
      "per_tick": {"7": 1.0, "8": 1.0}
    }
  }
}
```

## 4. Reproduce the run

AGORA is deterministic for heuristic (non-LLM) runs. The same seed produces identical outputs:

```bash
agora run scenarios/examples/morning_commute.yaml --seed 42 --output-dir runs/verify
diff <(cat runs/morning_commute/<first>/decisions.jsonl) <(cat runs/verify/decisions.jsonl)
# No differences
```

## 5. Try LLM-backed reasoning

To use an LLM for agent decisions (requires an API key):

```bash
export OPENAI_API_KEY="sk-..."
agora run scenarios/examples/morning_commute.yaml --seed 42 --llm
```

LLM mode adds richer reasoning in decision narratives and logs all prompts/responses for audit. It falls back to heuristic mode on failures.

## 6. Launch the visualization

```bash
agora viz
```

This opens a browser-based run viewer where you can inspect timelines, agent states, and decision traces.

## Next steps

- [Scenario Authoring](scenario-authoring.md) — create your own scenarios
- [Model Configuration](model-configuration.md) — configure LLM providers
- [Reproducibility](reproducibility.md) — understand seed behavior and determinism
