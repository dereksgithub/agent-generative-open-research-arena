# Research Limitations

AGORA is a research tool for exploring agent-based social simulations with LLM-backed reasoning. This document explicitly states what AGORA can and cannot claim, and where human review is required.

## What AGORA can claim

1. **Structured scenario execution**: AGORA faithfully executes the scenario as defined — agents follow their schedules, interventions apply at specified ticks, and outputs conform to documented contracts.

2. **Deterministic heuristic mode**: Given the same scenario, seed, and AGORA version, heuristic-mode runs produce identical outputs. This is verified by golden-run fixture tests in CI.

3. **Auditable LLM interactions**: Every LLM prompt, response, token count, and latency is logged. Researchers can inspect exactly what the model was asked and what it produced.

4. **Structured output formats**: All outputs use stable, documented schemas (JSONL, CSV, JSON) suitable for downstream analysis.

## What AGORA cannot claim

### Agent behavior validity

- **Heuristic agents are not realistic**: The default heuristic strategy uses simple schedule-based rules (go to work in the morning, go home in the evening). It does not model real human decision-making.

- **LLM agents are not validated behavioral models**: LLM responses reflect the model's training data, not empirical observations of real populations. An LLM-backed agent named "Alice the commuter" does not behave like a real commuter — it behaves like a language model prompted to role-play as one.

- **No calibration against real data**: AGORA scenarios are not calibrated against observed travel patterns, census data, or behavioral surveys. Outputs should not be treated as predictions of real-world outcomes.

### Simulation fidelity

- **Simplified world model**: The simulation uses a tick-based discrete model with location-route graphs. It does not model continuous space, queuing, congestion dynamics, network effects, or emergent traffic patterns.

- **No agent-agent interaction**: Agents make independent decisions based on their own perception. They do not communicate, coordinate, or compete for resources (beyond location capacity limits).

- **Flat intervention model**: Policy interventions are modeled as cost multipliers. Real-world policies have complex, non-linear, and delayed effects that this model does not capture.

- **No learning or adaptation**: Agents do not learn from experience within a run. Each decision is based on the current tick's perception and the agent's fixed persona. Memory is limited to a short-term record with no behavioral impact.

### LLM-specific limitations

- **Non-deterministic**: LLM responses vary between calls even with the same prompt and temperature. Prompt caching mitigates this within a run but not across model versions.

- **Prompt sensitivity**: Small changes to the prompt contract, agent backstory, or world description can produce significantly different decisions. Results are not robust to prompt perturbation.

- **Model bias**: LLM agents inherit biases from their training data. Agents with certain demographic profiles may exhibit stereotypical behavior patterns that reflect training data rather than real-world diversity.

- **No reasoning guarantees**: The "reasoning" field in LLM decisions is post-hoc rationalization by the model, not a faithful account of an internal decision process.

- **Provider variability**: Different LLM providers and models produce different results for the same prompt. Cross-provider comparisons are not meaningful without controlling for this variable.

## Where human review is required

### Before publishing results

- **Scenario design review**: Verify that the scenario's locations, routes, agents, and interventions are a reasonable (if simplified) representation of the domain being studied.

- **Decision trace inspection**: Read a sample of agent decisions and reasoning to check for nonsensical, repetitive, or stereotypical outputs.

- **KPI interpretation**: KPIs are computed mechanically from decision counts. Their meaning depends entirely on the scenario design. A "transit mode share of 80%" means 80% of decisions were labeled "transit" — not that 80% of a real population would take transit.

- **Intervention effect validation**: Check that intervention effects are directionally correct and that agents respond in ways that are at least plausible.

### When comparing runs

- **Control for model version**: If comparing LLM-backed runs over time, note that model updates from the provider can change behavior.

- **Control for prompt changes**: Any change to the prompt contract (system prompt, user prompt template) invalidates comparisons with prior runs.

- **Statistical significance**: A single run is one sample. Draw conclusions only from multiple runs with varied seeds and report the distribution, not a single outcome.

### When extending AGORA

- **New domains**: AGORA's default agent behavior (travel/stay decisions) is transport-oriented. Adapting to other domains (health, policy, economic) requires careful schema extension and validation.

- **New strategies**: Custom decision strategies should be tested for determinism (if expected) and validated against known behavior patterns before use in research.

## Recommended citation disclaimer

If using AGORA in published research, we recommend including a statement such as:

> Results were generated using AGORA v0.1.0, an agent-based simulation framework with [heuristic/LLM-backed] decision-making. Agent behaviors are modeled, not empirically calibrated. Outputs should be interpreted as illustrative scenarios, not predictions. See AGORA's research limitations documentation for details.

## Summary

| Claim | Status |
|-------|--------|
| Deterministic heuristic execution | Verified (CI-tested) |
| Stable output formats | Verified (contract-tested) |
| Auditable LLM interactions | Verified (event-logged) |
| Realistic agent behavior | **Not claimed** |
| Predictive accuracy | **Not claimed** |
| Calibration against real data | **Not claimed** |
| Robustness to prompt changes | **Not claimed** |
| Bias-free LLM responses | **Not claimed** |
