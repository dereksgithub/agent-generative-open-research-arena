# Quickstart

This guide walks you through running your first AGORA simulation in under five minutes.

## Prerequisites

```bash
# Activate the project virtual environment
source .venv/bin/activate

# Install spatial viewer dependencies (one-time)
cd viz/spatial && npm install && cd ../..
```

## 1. Run the example scenario (heuristic — no API key)

AGORA ships with example scenarios in `scenarios/examples/`. Run the morning commute scenario:

```bash
agora run scenarios/examples/morning_commute.yaml --seed 42
```

This runs a 24-tick transport simulation with 5 agents navigating a commute under a congestion charge policy. All decisions use deterministic heuristics — no LLM calls, no API key needed.

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

**KPIs**: `kpis.json` contains scenario-defined key performance indicators:

```json
{
  "kpis": {
    "transit_share": {
      "name": "Transit Mode Share",
      "overall": 0.15,
      "per_tick": {"7": 1.0, "8": 0.4}
    }
  }
}
```

## 4. Launch the visualization

AGORA includes two viewers — a **data dashboard** and a **spatial viewer**.

### Data dashboard

```bash
agora viz
```

Opens a browser-based run viewer for timelines, agent states, decision traces, and KPI charts.

### Spatial viewer (Three.js)

The spatial viewer renders runs as an animated top-down city map with agent sprites, route lines, speech bubbles, and intervention overlays.

```bash
# Terminal 1 — start the viz server (serves run data via API)
agora viz --no-browser

# Terminal 2 — start the spatial viewer dev server
cd viz/spatial && npm run dev
```

Open `http://localhost:5174` — it will auto-detect the latest run. Controls:

| Key | Action |
|-----|--------|
| Space | Play / Pause |
| Left / Right | Step backward / forward |
| Scroll | Zoom |
| Drag | Pan |
| Click agent | Show speech bubble (decision reasoning) |
| R | Reset camera |

## 5. Create agents from persona files

Instead of editing YAML directly, you can define each agent as a standalone `.md` file. This is especially useful for LLM-backed runs where the backstory, behaviour principles, and memories shape each agent's reasoning.

### Persona file format

Create one `.md` file per agent in a folder (e.g. `personas/demo/`):

```markdown
# Alice Chen

## Identity
- **Role:** commuter
- **Age:** 34
- **Income:** medium
- **Household size:** 3

## Home & Work
- **Home location:** suburbs_north
- **Work location:** town_centre
- **Preferred mode:** drive

## Traits
- punctual
- cost-sensitive

## Values
- convenience
- reliability

## Behaviour Principles
- Always prioritise arriving on time.
- Will switch from driving to transit only when cost > 2x normal.
- Keeps a mental budget: any commute over £10/day feels wasteful.

## Memory Seeds
- Last month the bus was 20 minutes late twice in one week.
- Her daughter's school is on the route to work, so transit adds a detour.

## Backstory
Alice is a project manager who drops her child at school before work.
She drives because northern transit links are unreliable before 8 AM.
```

The `## Behaviour Principles` and `## Memory Seeds` sections are folded into the backstory field and sent to the LLM as part of the agent's persona prompt. For heuristic runs, the structured fields (role, traits, preferred_mode) still drive decisions.

### Assemble personas into a scenario

```bash
python3 scripts/assemble_personas.py personas/demo/ \
  --template scenarios/templates/commute_base.yaml \
  --output scenarios/generated/demo_commute.yaml
```

The assembler reads all `.md` files in the folder and injects them as agents into the scenario template. The template defines the world (locations, routes, interventions, KPIs) — the personas define who lives in it.

## 6. Run with LLM-backed reasoning

LLM mode sends each agent's full persona, current situation, and available choices to an LLM. The agent's response determines their action each tick.

### Set up your API key

```bash
cp .env.example .env
# Edit .env — fill in the key for your provider
```

Supported providers: `openai`, `anthropic`, `minimax`, `deepseek`, `mistral`, `gemini`, `qwen`, `kimi`, `local` (Ollama/vLLM).

### Run with a provider

```bash
# MiniMax
agora run scenarios/generated/demo_commute.yaml --seed 42 --llm --llm-provider minimax

# OpenAI
agora run scenarios/generated/demo_commute.yaml --seed 42 --llm --llm-provider openai

# Anthropic
agora run scenarios/generated/demo_commute.yaml --seed 42 --llm --llm-provider anthropic
```

LLM mode logs every prompt and response to `events.jsonl` for audit. If the LLM fails (bad key, rate limit, parse error), the agent falls back to heuristic decisions for that tick — the run never crashes. The `metadata.json` file records which mode was used and LLM accounting (tokens, latency, cache hits).

### One-command demo

The demo script assembles personas, runs the simulation, and launches both viewers:

```bash
# With LLM (default: MiniMax)
./scripts/run-demo.sh

# With a different provider
./scripts/run-demo.sh --provider openai

# Heuristic only (no API key needed)
./scripts/run-demo.sh --no-llm
```

## 7. Reproduce a run

Heuristic runs are fully deterministic — same seed produces identical outputs:

```bash
agora run scenarios/examples/morning_commute.yaml --seed 42 --output-dir runs/verify
diff <(cat runs/morning_commute/<first>/decisions.jsonl) <(cat runs/verify/decisions.jsonl)
# No differences
```

LLM runs are non-deterministic (model temperature, server-side sampling), but the prompt cache can replay identical requests. Set `--llm-cache-dir` to share a cache across runs.

## Next steps

- [Scenario Authoring](scenario-authoring.md) — create your own scenarios and world layouts
- [Model Configuration](model-configuration.md) — configure LLM providers, temperature, token limits
- [Reproducibility](reproducibility.md) — understand seed behavior and determinism
