<p align="center">
  <img src="docs/assets/agora-banner.svg" alt="AGORA" width="720" />
</p>
 
<h3 align="center">Agent-Generative Open Research Arena</h3>
 
<p align="center">
  <em>Where agents meet, decisions emerge.</em>
</p>
 
<p align="center">
  <a href="#quickstart">Quickstart</a> · <a href="#paper">Paper</a> · <a href="https://agora-sim.org/demo">Live Demo</a> · <a href="https://agora-sim.org/docs">Docs</a> · <a href="#community">Community</a>
</p>
 
<p align="center">
  <img src="https://img.shields.io/badge/license-Apache_2.0-blue" alt="License" />
  <img src="https://img.shields.io/badge/engine-Three.js-black" alt="Three.js" />
  <img src="https://img.shields.io/badge/agents-LLM--powered-orange" alt="LLM Agents" />
  <img src="https://img.shields.io/badge/status-alpha-yellow" alt="Status" />
</p>
 
---
 
**AGORA** is an open-source, browser-native simulation framework where LLM-driven cognitive agents inhabit rich spatial environments — and _reason_ their way through them.
 
Unlike classical agent-based models where agents optimise a utility function over fixed choice dimensions, AGORA agents perceive, deliberate, and decide through language-grounded cognition. They hold memory, exhibit bounded rationality, respond to narrative policy framing, and — critically — can _explain_ why they made a choice.
 
The result is a general-purpose socio-spatial simulation engine that is **visual by default** and **reproducible by design**, making even fully synthesised populations suitable for serious, publishable research.
 
## Why AGORA?
 
For two decades, frameworks like [MATSim](https://matsim.org), [SUMO](https://eclipse.dev/sumo/), and [NetLogo](https://ccl.northwestern.edu/netlogo/) have powered agent-based research across transport, public health, urban planning, and beyond. They remain excellent tools. But their agents are mathematical constructs: utility maximisers navigating predefined choice sets. When a novel policy is introduced — a congestion charge, a pandemic lockdown, a platform economy disruption — these agents can only respond within the behavioural envelope their modellers hard-coded.
 
AGORA takes a different approach:
 
| | Classical ABM (MATSim, SUMO, NetLogo) | AGORA |
|---|---|---|
| **Agent cognition** | Utility functions, logit models | LLM-grounded reasoning with memory |
| **Behavioural scope** | Pre-specified choice dimensions | Open-ended: agents reason about _novel_ situations |
| **Scenario definition** | XML/config files, code extensions | Natural language + structured YAML |
| **Visualisation** | Post-hoc analysis, separate tools | Real-time 3D (Three.js), browser-native |
| **Accessibility** | Java/Python install, steep learning curve | Open a URL. Run a simulation. |
| **Qualitative insight** | Aggregate KPIs only | Agent-level decision narratives exportable as data |
| **Reproducibility** | Seed-based, deterministic | Seed-based + LLM temperature control + decision logs |
| **Extensibility** | Language-specific plugins (Java/Python) | Scenario packs (YAML + prompt templates) |
 
AGORA does not replace these tools — it extends the frontier of what agent-based simulation can study.
 
## Application Domains
 
AGORA is domain-agnostic by design. The same engine supports:
 
🚗 **Transport & Mobility** — Mode choice, EV charging behaviour, congestion pricing response, demand-responsive transit. Import MATSim network and population files directly.
 
🏙️ **Urban Planning & Land Use** — High street economics, housing market dynamics, gentrification cascades, pedestrianisation impact studies.
 
🏥 **Public Health & Epidemiology** — Pandemic response under heterogeneous compliance, vaccine allocation equity, health-seeking behaviour in spatial contexts.
 
⚡ **Energy & Infrastructure** — Charging network placement, grid demand simulation, distributed energy resource adoption under policy incentives.
 
🛒 **Consumer Behaviour & Market Design** — Platform marketplace dynamics, surge pricing response, retail footfall under spatial interventions.
 
🚨 **Emergency Management** — Evacuation modelling with cognitively diverse agents, disaster communication effectiveness, shelter allocation under uncertainty.
 
📊 **Computational Social Science** — Opinion dynamics, institutional trust erosion, policy preference formation, inter-group cooperation experiments.
 
## Architecture
 
```
┌─────────────────────────────────────────────────────────────────┐
│                    Browser / Three.js Frontend                  │
│         Real-time 3D visualisation · Multiplayer interaction    │
├─────────────────────────────────────────────────────────────────┤
│                    Multiplayer & Interactive Layer               │
│      Human-in-the-loop · Stakeholder workshops · Gaming mode   │
├─────────────────────────────────────────────────────────────────┤
│                    Scenario & Policy Engine                      │
│        YAML/NL scenario definitions · Timed interventions       │
├──────────────────────┬──────────────────────────────────────────┤
│  Agent Cognition     │        Environment Simulation            │
│  Engine              │                                          │
│                      │  Transport network · Land use            │
│  Persona + Memory    │  Energy grid · Economic activity         │
│  Perceive → Reason   │  Social network graph                   │
│  → Decide → Act      │                                          │
│                      │  Modular: swap city datasets,            │
│  Tiered inference:   │  import MATSim .xml, OSM, GTFS          │
│  Local SLM (95%)     │                                          │
│  Frontier LLM (5%)   │                                          │
├──────────────────────┴──────────────────────────────────────────┤
│                 Observation & Analytics Layer                    │
│    Real-time dashboards · Decision narrative logs               │
│    Configurable KPIs · Exportable datasets (CSV, Parquet)       │
└─────────────────────────────────────────────────────────────────┘
```
 
## Quickstart
 
No install required. Clone and run:
 
```bash
git clone https://github.com/agora-sim/agora.git
cd agora
npm install
npm run dev
```
 
Open `http://localhost:3000` — a small-town transport scenario loads in your browser with 200 cognitive agents. Inject a policy shock from the control panel and watch behaviour shift in real time.
 
**Or try the hosted demo →** [agora-sim.org/demo](https://agora-sim.org/demo)
 
## For MATSim Users
 
AGORA can ingest MATSim network and population XML files:
 
```bash
agora import --matsim-network ./berlin-network.xml \
             --matsim-plans ./berlin-plans.xml \
             --output ./scenarios/berlin/
```
 
Your existing city models become AGORA scenarios. Agent plans are converted into persona definitions with cognitive capabilities layered on top.
 
## Reproducibility
 
Synthesised data and LLM-driven agents raise valid concerns about reproducibility. AGORA addresses this head-on:
 
- **Deterministic seeding** — Every simulation run is seeded. Same seed, same agent order, same environment state.
- **Temperature-controlled inference** — LLM temperature is a first-class simulation parameter, logged and versioned.
- **Full decision audit trail** — Every agent decision is logged with its reasoning chain, input context, and selected action. These logs are exportable as structured data for qualitative and quantitative analysis.
- **Cognitive fidelity dial** — Researchers choose where on the cost–realism spectrum to operate. At minimum fidelity, agents use cached heuristic responses (fast, cheap, reproducible). At maximum fidelity, every decision is a live LLM call (rich, expensive, stochastic but logged).
 
This means AGORA outputs are not black boxes — they are auditable, publishable, and debatable.
 
## Roadmap
 
- [x] Core agent cognition loop (perceive → reason → decide → act)
- [x] Three.js spatial visualisation engine
- [x] YAML scenario definition format
- [ ] MATSim network/plans importer
- [ ] Tiered inference (local SLM + frontier LLM routing)
- [ ] Multiplayer interaction layer
- [ ] Pre-built scenario packs (transport, public health, housing)
- [ ] Decision narrative → structured dataset exporter
- [ ] Hosted cloud simulation platform
 
## Citing AGORA
 
If you use AGORA in your research, please cite:
 
```bibtex
@software{agora2026,
  title     = {AGORA: Agent-Generative Open Research Arena},
  author    = {[Author]},
  year      = {2026},
  url       = {https://github.com/agora-sim/agora},
  note      = {Open-source LLM-driven cognitive agent simulation framework}
}
```
 
A foundational paper is in preparation. Details will be posted here upon submission.
 
## Community
 
- **Discussions** — [GitHub Discussions](https://github.com/agora-sim/agora/discussions) for questions, ideas, and scenario sharing
- **Discord** — Real-time chat for developers and researchers _(link coming soon)_
- **Mailing list** — Low-frequency announcements for releases and events
 
We welcome contributions: new scenario packs, domain-specific KPI modules, visualisation enhancements, and inference optimisations. See [CONTRIBUTING.md](CONTRIBUTING.md).
 
## License
 
Apache 2.0 — Use it, extend it, publish with it. See [LICENSE](LICENSE).
 
---
 
<p align="center">
  <em>AGORA: Simulation where agents think, not just optimise.</em>
</p>
