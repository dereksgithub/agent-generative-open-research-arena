# Scenario Authoring

AGORA scenarios are YAML files that define the simulation world, agents, routes, policy interventions, and KPIs.

## Scenario structure

```yaml
# Required
name: my_scenario
description: A brief description of the scenario

# Optional metadata
id: my_scenario_v1          # auto-generated from name+version if omitted
domain: transport            # domain label (transport, policy, health, etc.)
version: "1"

# Simulation parameters
simulation:
  ticks: 24                  # number of simulation steps
  tick_unit: hour            # label for each tick (hour, day, week, etc.)
  seed: 42                   # default seed (overridable via CLI)

# World definition
locations: [...]
routes: [...]

# Agent definitions
agents: [...]

# Policy interventions (optional)
interventions: [...]

# Key performance indicators (optional)
kpis: [...]
```

## Locations

Locations are named places in the simulation world.

```yaml
locations:
  - id: suburbs_north        # unique identifier
    name: North Suburbs       # display name
    type: residential         # generic, residential, commercial, transit_stop
    x: 0.0                   # coordinates (for visualization)
    y: 2.0
    capacity: 500            # max occupants (optional, null = unlimited)
    resources:               # domain-specific resources
      parking_spaces: 120
      households: 300
```

## Routes

Routes connect locations and define travel options.

```yaml
routes:
  - from: suburbs_north
    to: town_centre
    mode: drive              # drive, transit, walk, or custom modes
    travel_time_minutes: 15
```

Routes are directional — define both directions if needed. Multiple routes with different modes between the same locations create mode choice.

## Agents

Agents are the cognitive entities in the simulation.

```yaml
agents:
  - id: alice
    name: Alice
    role: commuter           # used for targeted interventions and KPIs
    traits: [punctual, cost-sensitive]
    home_location: suburbs_north
    work_location: town_centre
    preferred_mode: drive

    # Optional enriched persona fields (used by LLM reasoning)
    age: 34
    income_bracket: medium   # low, medium, high
    household_size: 3
    values: [convenience, reliability]
    backstory: >
      Alice is a project manager who drops her child at school
      before heading to the office.

    # Optional explicit schedule overrides
    schedule:
      "9": "travel_to:town_centre"
      "15": "travel_to:suburbs_north"
```

### Agent behavior

In **heuristic mode** (default), agents follow a simple schedule:
- Ticks 7-9: travel to work location
- Ticks 17-19: travel to home location
- Other ticks: stay at current location
- Schedule entries override defaults

In **LLM mode**, agents receive their full persona, current perception, and available routes as a structured prompt. The LLM chooses an action with reasoning.

### Schedule format

Schedule keys are tick numbers (as strings). Values are goals:
- `"travel_to:<location_id>"` — travel to a specific location
- `"stay"` — remain at current location

## Policy interventions

Interventions inject policy changes at specific ticks.

```yaml
interventions:
  - tick: 7                  # when to activate (0-indexed)
    name: congestion_charge
    description: >
      A £5 congestion charge for driving during peak hours.
    effects:
      drive_cost_multiplier: 2.5   # makes driving 2.5x more expensive
    target_roles: []         # empty = affects all agents
    duration: null           # null = permanent, or number of ticks
```

### Effects

Effects modify route costs via multipliers:
- `drive_cost_multiplier: 2.0` — doubles driving cost
- `transit_cost_multiplier: 0.5` — halves transit cost

### Targeted interventions

Use `target_roles` to apply effects only to specific agent roles:

```yaml
interventions:
  - tick: 0
    name: student_discount
    description: Free transit for students
    effects:
      transit_cost_multiplier: 0.0
    target_roles: [student]
    duration: 5
```

## KPIs

Key performance indicators are evaluated from the run data.

```yaml
kpis:
  - id: drive_trips
    name: Driving Trips
    description: Total driving trips per tick
    metric: count            # count, ratio, mean, sum
    source: decisions        # decisions or agent_states
    filter:
      action: travel
      mode: drive
    unit: trips
```

### Metric types

| Metric | Description |
|--------|-------------|
| `count` | Number of matching records per tick |
| `ratio` | Matching / total records per tick |
| `mean` | Same as ratio (matching / total) |
| `sum` | Same as count |

### Filter keys

For `source: decisions`: `action`, `mode`, `target`
For `source: agent_states`: `role`, `action`, `location`, `mode`

## Validation

AGORA validates scenarios on load:
- All agent home/work locations must reference existing location IDs
- All route endpoints must reference existing location IDs
- Agent schedules with `travel_to:` must reference existing location IDs
- Intervention ticks must be within the simulation range
- No duplicate location or agent IDs

Invalid scenarios produce clear error messages:

```
Error: Invalid scenario 'bad.yaml':
  Agent 'alice' references unknown home location 'nowhere'
```

## Examples

See `scenarios/examples/` for working examples:
- `morning_commute.yaml` — transport with congestion charge
- `vaccine_uptake.yaml` — health policy scenario
