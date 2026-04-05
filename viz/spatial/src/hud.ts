/**
 * hud.ts — Heads-up display overlay.
 * Shows run info, active interventions, KPI values at current tick,
 * and agent action breakdown.
 */
import type { RunData } from "./types";
import type { InterventionVisual } from "./interventions";

export interface HUD {
  update(tick: number): void;
}

export function createHUD(
  container: HTMLElement,
  runData: RunData,
  interventionVisuals: InterventionVisual[]
): HUD {
  const hudEl = container.querySelector("#hud") as HTMLElement;
  if (!hudEl) return { update: () => {} };

  const { metadata, kpis, agentStates } = runData;

  // Static run info
  const infoEl = hudEl.querySelector("#hud-info") as HTMLElement;
  if (infoEl) {
    infoEl.innerHTML = `
      <span class="hud-field">${metadata.scenario_name}</span>
      <span class="hud-dim">run ${metadata.run_id}</span>
      <span class="hud-dim">seed ${metadata.seed} · ${metadata.total_agents} agents · ${metadata.decision_mode}</span>
    `;
  }

  const interventionsEl = hudEl.querySelector("#hud-interventions") as HTMLElement;
  const kpiEl = hudEl.querySelector("#hud-kpis") as HTMLElement;
  const agentsEl = hudEl.querySelector("#hud-agents") as HTMLElement;

  function update(tick: number): void {
    // Active interventions
    if (interventionsEl) {
      const active = interventionVisuals.filter((v) => v.active);
      if (active.length === 0) {
        interventionsEl.innerHTML =
          '<span class="hud-dim">No active interventions</span>';
      } else {
        interventionsEl.innerHTML = active
          .map(
            (v) =>
              `<span class="hud-tag hud-tag--intervention">${v.name}</span>`
          )
          .join(" ");
      }
    }

    // KPIs at current tick
    if (kpiEl && kpis?.kpis) {
      kpiEl.innerHTML = Object.values(kpis.kpis)
        .map((k) => {
          const val = k.per_tick?.[String(tick)] ?? 0;
          const formatted =
            k.metric === "ratio"
              ? (val * 100).toFixed(0) + "%"
              : String(Math.round(val));
          return `<div class="hud-kpi"><span class="hud-kpi-val">${formatted}</span><span class="hud-kpi-name">${k.name}</span></div>`;
        })
        .join("");
    }

    // Agent action breakdown
    if (agentsEl) {
      const tickStates = agentStates.filter((s) => s.tick === tick);
      const actions: Record<string, number> = {};
      const modes: Record<string, number> = {};
      for (const s of tickStates) {
        actions[s.action] = (actions[s.action] ?? 0) + 1;
        if (s.mode) modes[s.mode] = (modes[s.mode] ?? 0) + 1;
      }
      const actionStr = Object.entries(actions)
        .map(([a, c]) => `${a}: ${c}`)
        .join(" · ");
      const modeStr = Object.entries(modes)
        .map(([m, c]) => `${m}: ${c}`)
        .join(" · ");
      const agentCount = `${tickStates.length} agents`;
      agentsEl.innerHTML = `
        <span class="hud-field">${agentCount}</span>
        <span class="hud-dim">${actionStr}</span>
        ${modeStr ? `<span class="hud-dim">${modeStr}</span>` : ""}
      `;
    }
  }

  return { update };
}
