# Scenario Schema Reference

AGORA scenarios are YAML files validated against the `ScenarioSpec` Pydantic model. This document describes every field a scenario author can use.

Version: `1` (schema version tracked in each scenario file)

## Top-level fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | No | auto-generated | Stable scenario identifier. If omitted, derived as `{slugified-name}-v{version}`. |
| `name` | string | **Yes** | — | Short machine-friendly name (used in output paths). |
| `description` | string | No | `""` | Human-readable description of the scenario. |
| `domain` | string | No | `"transport"` | Research domain (e.g. `transport`, `public_health`, `urban_planning`). |
| `version` | string | No | `"1"` | Schema/scenario version for compatibility tracking. |
| `simulation` | SimulationConfig | No | see below | Simulation parameters. |
| `locations` | list[Location] | No | `[]` | Named places in the simulated world. |
| `routes` | list[Route] | No | `[]` | Connections between locations. |
| `agents` | list[PersonaDefinition] | No | `[]` | Agent persona templates. |
| `interventions` | list[PolicyIntervention] | No | `[]` | Timed policy changes. |
| `kpis` | list[KPIDefinition] | No | `[]` | Key performance indicators to evaluate. |

## SimulationConfig

| Field | Type | Default | Description |
|---|---|---|---|
| `ticks` | int | `24` | Number of simulation ticks to execute. |
| `tick_unit` | string | `"hour"` | Semantic label for each tick (e.g. `hour`, `day`, `step`). |
| `seed` | int \| null | `null` | Default random seed. Can be overridden via `--seed` CLI flag. |

## Location

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | **Yes** | — | Unique identifier referenced by routes and agents. |
| `name` | string | **Yes** | — | Human-readable name. |
| `type` | string | No | `"generic"` | Category (e.g. `residential`, `commercial`, `healthcare`, `transit_stop`). |
| `capacity` | int \| null | No | `null` | Max occupants. `null` = unlimited. Must be >= 0. |
| `x` | float | No | `0.0` | X coordinate for spatial layout. |
| `y` | float | No | `0.0` | Y coordinate for spatial layout. |
| `resources` | dict[str, float] | No | `{}` | Domain-specific resources (e.g. `parking_spaces: 120`, `vaccine_doses: 500`). |

## Route

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `from` | string | **Yes** | — | Origin location ID. |
| `to` | string | **Yes** | — | Destination location ID. |
| `mode` | string | No | `"walk"` | Travel mode (e.g. `walk`, `drive`, `transit`). |
| `travel_time_minutes` | float | No | `10.0` | Base travel time. Must be > 0. Modified at runtime by intervention effects. |

## PersonaDefinition

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | **Yes** | — | Unique agent identifier. |
| `name` | string | **Yes** | — | Display name. |
| `role` | string | No | `""` | Role label (e.g. `commuter`, `student`, `parent`, `retiree`). |
| `traits` | list[string] | No | `[]` | Personality traits (e.g. `cost-sensitive`, `eco-conscious`). |
| `home_location` | string | No | `""` | Starting/home location ID. Must exist in `locations`. |
| `work_location` | string | No | `""` | Primary destination location ID. Must exist in `locations`. |
| `preferred_mode` | string | No | `"walk"` | Default travel mode preference. |
| `schedule` | dict[str, str] | No | `{}` | Tick-to-goal mapping (e.g. `"8": "travel_to:office"`). |
| `age` | int \| null | No | `null` | Agent age (0-150). |
| `income_bracket` | string | No | `""` | Income level (e.g. `low`, `medium`, `high`). |
| `household_size` | int \| null | No | `null` | Number of household members (>= 1). |
| `values` | list[string] | No | `[]` | Personal values (e.g. `sustainability`, `family-safety`). |
| `backstory` | string | No | `""` | Free-text background for LLM-backed reasoning prompts. |
| `attributes` | dict[str, float] | No | `{}` | Domain-specific numeric attributes. |

### Schedule format

Schedule keys are tick numbers as strings. Values are goal strings:
- `"travel_to:<location_id>"` — travel to the named location
- `"stay"` — remain in place

If no schedule entry exists for a tick, the agent uses default heuristics (travel to work in morning, home in evening).

## PolicyIntervention

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `tick` | int | **Yes** | — | Tick at which the intervention activates. Must be >= 0 and < `simulation.ticks`. |
| `name` | string | **Yes** | — | Machine-friendly intervention name. |
| `description` | string | **Yes** | — | What the intervention represents. |
| `effects` | dict[str, float] | No | `{}` | Key-value effects on the world. See below. |
| `target_roles` | list[string] | No | `[]` | Agent roles affected. Empty = all agents. |
| `duration` | int \| null | No | `null` | How many ticks the intervention lasts. `null` = permanent. |

### Effect keys

Effects modify route travel costs via multipliers. The format is `<mode>_cost_multiplier`:

- `drive_cost_multiplier: 2.5` — makes driving 2.5x more expensive
- `walk_cost_multiplier: 0.7` — makes walking 30% cheaper (e.g. improved paths)
- `transit_cost_multiplier: 0.5` — halves transit cost (e.g. free transit policy)

When `target_roles` is provided, the effect applies only to agents whose `role`
matches one of the listed roles. When `duration` is provided, the intervention
expires after that many ticks.

## KPIDefinition

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | **Yes** | — | Unique KPI identifier. |
| `name` | string | **Yes** | — | Human-readable name. |
| `description` | string | No | `""` | What this KPI measures. |
| `metric` | string | **Yes** | — | Aggregation method: `count`, `ratio`, `mean`, `sum`. |
| `source` | string | **Yes** | — | Data source: `decisions` or `agent_states`. |
| `filter` | dict[str, str] | No | `{}` | Filter criteria. See below. |
| `unit` | string | No | `""` | Display unit (e.g. `trips`, `agents`, `%`). |

### Filter keys

For `source: decisions`:
- `action` — match by action type (e.g. `travel`, `stay`)
- `mode` — match by transport mode in decision metadata
- `target` — match by target location ID

For `source: agent_states`:
- `role` — match agents by role
- `action` — match state rows by action taken that tick
- `location` — match state rows by location at that tick
- `mode` — match state rows by mode used on that tick

## Validation rules

The schema validator enforces:

1. No duplicate location IDs.
2. No duplicate agent IDs.
3. All agent `home_location` and `work_location` values must reference existing locations.
4. All `travel_to:<loc>` entries in agent schedules must reference existing locations.
5. All route `from`/`to` values must reference existing locations.
6. Intervention ticks must be within the simulation tick range.
7. KPI `metric` must be one of `count`, `ratio`, `mean`, `sum`.
8. KPI `source` must be one of `decisions`, `agent_states`.

Validation errors are raised at load time with specific messages identifying the problem.

## Output files

After `agora run`, the output directory contains:

| File | Format | Description |
|---|---|---|
| `scenario.yaml` | YAML | Copy of the input scenario. |
| `config.json` | JSON | Resolved config including effective seed and version. |
| `decisions.jsonl` | JSONL | Every agent decision with tick, action, target, reasoning. |
| `events.jsonl` | JSONL | Full lifecycle event log with stable IDs. |
| `aggregate.csv` | CSV | Per-tick counts of travel vs. stay. |
| `metadata.json` | JSON | Run metadata (run_id, scenario_id, seed, decision_mode). |
| `agent_states.jsonl` | JSONL | Per-tick agent state snapshots. |
| `narratives.jsonl` | JSONL | Decision reasoning records for qualitative analysis. |
| `agent_summary.csv` | CSV | One row per agent with trip/stay counts and mode usage. |
| `kpis.json` | JSON | Evaluated KPI values (overall and per-tick). Only present if KPIs are defined. |
