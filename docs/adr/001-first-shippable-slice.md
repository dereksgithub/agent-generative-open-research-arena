# ADR-001: First Shippable Slice

**Status:** Accepted  
**Date:** 2026-04-02

## Context

AGORA's README described a browser-native, multiplayer, Three.js-powered simulation platform. The actual codebase contained only an LLM provider client and empty package stubs. Shipping the full vision first would delay any usable release indefinitely.

We need to decide the smallest useful system boundary that lets a researcher install, run, and inspect a simulation.

## Decision

The first shippable slice is:

**Engine library + local CLI + file-based scenarios + file-based outputs.**

Specifically:

- **One domain:** transport micro-simulation (mode choice under policy intervention).
- **One execution mode:** local batch run from CLI (`agora run <scenario.yaml>`).
- **One scenario format:** YAML validated by Pydantic models.
- **One output format:** JSONL decision traces + CSV aggregates + JSON metadata.
- **One agent mode:** heuristic (deterministic, no LLM calls required). LLM-backed mode is a later addition that wraps the same lifecycle.

### What is excluded from this slice

- Browser frontend / Three.js visualization
- Hosted cloud platform
- MATSim import
- Multiplayer / human-in-the-loop
- LLM-driven agent reasoning (client exists, not wired in yet)

### System boundary

```
User
  |
  v
agora run <scenario.yaml> --seed 42 --no-llm
  |
  v
[ Scenario Loader ] ---> [ Simulation Engine ] ---> [ Output Writer ]
     (YAML+Pydantic)      (tick loop, agents)       (JSONL, CSV, JSON)
```

## Consequences

- Researchers can install with `pip install -e .` and run a documented example immediately.
- The heuristic agent path is fully deterministic and reproducible (same seed = same output).
- The scenario schema is the contract between researchers and the engine — it must be stable and versioned before expanding.
- LLM integration will layer on top of the same perceive-deliberate-decide-act lifecycle without changing the scenario format or output structure.
- Visualization, hosting, and import features are deferred to later phases and should not block this slice.
