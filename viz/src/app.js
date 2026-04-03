/* AGORA Run Viewer — vanilla JS single-page application */

"use strict";

const state = {
  runs: [],
  selectedRun: null,
  runData: {},
  activeTab: "timeline",
  selectedAgent: null,
};

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

async function fetchText(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Fetch error ${resp.status}`);
  return resp.text();
}

function parseJsonl(text) {
  return text.trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
}

document.addEventListener("DOMContentLoaded", () => {
  loadRuns();
  bindEvents();
});

function bindEvents() {
  document.getElementById("btn-refresh").addEventListener("click", loadRuns);
  document.getElementById("btn-launch").addEventListener("click", toggleLaunchPanel);
  document.getElementById("btn-launch-go").addEventListener("click", launchRun);

  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
}

async function loadRuns() {
  try {
    const data = await api("/api/runs");
    state.runs = data.runs || [];
    renderRunList();
  } catch (e) {
    console.error("Failed to load runs:", e);
  }
}

function renderRunList() {
  const ul = document.getElementById("run-list");
  if (state.runs.length === 0) {
    ul.innerHTML = '<li class="run-meta" style="cursor:default">No runs found. Launch one or run <code>agora run</code>.</li>';
    return;
  }
  ul.innerHTML = state.runs.map(r => `
    <li data-path="${r.path}" class="${state.selectedRun?.path === r.path ? "active" : ""}">
      <div class="run-scenario">${r.scenario}</div>
      <div class="run-meta">
        ${r.timestamp} &middot; seed ${r.seed ?? "?"} &middot; ${r.total_decisions ?? "?"} decisions
        ${r.decision_mode ? " &middot; " + r.decision_mode : ""}
      </div>
    </li>
  `).join("");

  ul.querySelectorAll("li[data-path]").forEach(li => {
    li.addEventListener("click", () => selectRun(li.dataset.path));
  });
}

async function selectRun(path) {
  const run = state.runs.find(r => r.path === path);
  if (!run) return;
  state.selectedRun = run;
  renderRunList();

  document.getElementById("run-info").textContent =
    `${run.scenario} | run ${run.run_id || "?"} | seed ${run.seed ?? "?"} | ${run.total_ticks} ticks, ${run.total_agents} agents`;

  const base = `/api/runs/${path}`;
  try {
    const [metadata, decisions, aggregate, agentStates, narratives, kpis, events] =
      await Promise.allSettled([
        api(`${base}/metadata.json`),
        fetchText(`${base}/decisions.jsonl`).then(parseJsonl),
        fetchText(`${base}/aggregate.csv`),
        fetchText(`${base}/agent_states.jsonl`).then(parseJsonl),
        fetchText(`${base}/narratives.jsonl`).then(parseJsonl),
        api(`${base}/kpis.json`).catch(() => null),
        fetchText(`${base}/events.jsonl`).then(parseJsonl),
      ]);

    state.runData = {
      metadata: metadata.status === "fulfilled" ? metadata.value : {},
      decisions: decisions.status === "fulfilled" ? decisions.value : [],
      aggregate: aggregate.status === "fulfilled" ? parseCSV(aggregate.value) : [],
      agentStates: agentStates.status === "fulfilled" ? agentStates.value : [],
      narratives: narratives.status === "fulfilled" ? narratives.value : [],
      kpis: kpis.status === "fulfilled" ? kpis.value : null,
      events: events.status === "fulfilled" ? events.value : [],
    };

    document.getElementById("placeholder").classList.add("hidden");
    document.getElementById("panels").classList.remove("hidden");

    state.selectedAgent = null;
    renderAllPanels();
  } catch (e) {
    console.error("Failed to load run data:", e);
  }
}

function parseCSV(text) {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",");
  return lines.slice(1).map(line => {
    const vals = line.split(",");
    const obj = {};
    headers.forEach((h, i) => obj[h] = vals[i]);
    return obj;
  });
}

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === `tab-${tabName}`));
}

function renderAllPanels() {
  renderTimeline();
  renderAgents();
  renderDecisions();
  renderKPIs();
  renderExport();
}

function renderTimeline() {
  const { aggregate, metadata } = state.runData;
  const totalTicks = metadata.total_ticks || aggregate.length;
  const totalAgents = metadata.total_agents || 1;
  const interventions = state.runData.events.filter(e => e.event_type === "intervention_applied");

  const chart = document.getElementById("timeline-chart");
  let html = "";
  for (let tick = 0; tick < totalTicks; tick++) {
    const row = aggregate.find(r => r.tick == tick) || {};
    const travel = parseInt(row.travel_count) || 0;
    const stay = parseInt(row.stay_count) || 0;
    const total = travel + stay || totalAgents;
    const travelPct = (travel / total * 100).toFixed(1);
    const stayPct = (stay / total * 100).toFixed(1);
    const hasIntervention = interventions.some(iv => iv.tick === tick);

    html += `<div class="bar-row">
      <span class="bar-label">${tick}</span>
      <div class="bar-container">
        ${travel > 0 ? `<div class="bar-segment bar-travel" style="width:${travelPct}%" title="Travel: ${travel}"></div>` : ""}
        ${stay > 0 ? `<div class="bar-segment bar-stay" style="width:${stayPct}%" title="Stay: ${stay}"></div>` : ""}
        ${hasIntervention ? '<div class="bar-intervention" title="Intervention"></div>' : ""}
      </div>
    </div>`;
  }
  chart.innerHTML = html;

  document.getElementById("timeline-legend").innerHTML = `
    <div class="legend-item"><div class="legend-swatch" style="background:var(--accent)"></div> Travel</div>
    <div class="legend-item"><div class="legend-swatch" style="background:var(--surface-2);border:1px solid var(--border)"></div> Stay</div>
    <div class="legend-item"><div class="legend-swatch" style="background:var(--orange)"></div> Intervention</div>
  `;

  const markers = document.getElementById("intervention-markers");
  if (interventions.length === 0) {
    markers.innerHTML = "<h3>Interventions</h3><p style='font-size:12px;color:var(--text-dim)'>No interventions in this run.</p>";
  } else {
    markers.innerHTML = "<h3>Interventions</h3>" + interventions.map(iv => `
      <div class="intervention-item">
        <span class="intervention-tick">Tick ${iv.tick}</span> &middot;
        ${iv.data?.name || "unnamed"}
        ${iv.data?.effects ? ` (effects: ${JSON.stringify(iv.data.effects)})` : ""}
        ${iv.data?.duration ? ` [${iv.data.duration} ticks]` : ""}
      </div>
    `).join("");
  }
}

function renderAgents() {
  const { agentStates } = state.runData;
  const agents = [...new Set(agentStates.map(s => s.agent_id))];
  const selector = document.getElementById("agent-selector");
  selector.innerHTML = agents.map(a => {
    const name = agentStates.find(s => s.agent_id === a)?.agent_name || a;
    return `<button class="agent-chip ${state.selectedAgent === a ? "active" : ""}" data-agent="${a}">${name}</button>`;
  }).join("");

  selector.querySelectorAll(".agent-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      state.selectedAgent = chip.dataset.agent;
      renderAgents();
    });
  });

  const detail = document.getElementById("agent-detail");
  if (!state.selectedAgent) {
    detail.innerHTML = '<p style="font-size:12px;color:var(--text-dim)">Select an agent above to see their details.</p>';
    document.querySelector("#agent-states-table thead tr").innerHTML = "";
    document.querySelector("#agent-states-table tbody").innerHTML = "";
    return;
  }

  const agentRows = agentStates.filter(s => s.agent_id === state.selectedAgent);
  const first = agentRows[0] || {};
  detail.innerHTML = `
    <div class="agent-field"><span class="label">ID:</span> ${first.agent_id}</div>
    <div class="agent-field"><span class="label">Name:</span> ${first.agent_name || "?"}</div>
    <div class="agent-field"><span class="label">Role:</span> ${first.role || "?"}</div>
    <div class="agent-field"><span class="label">Traits:</span> ${(first.traits || []).join(", ")}</div>
  `;

  const headers = ["Tick", "Location", "Action", "Mode"];
  document.querySelector("#agent-states-table thead tr").innerHTML = headers.map(h => `<th>${h}</th>`).join("");
  document.querySelector("#agent-states-table tbody").innerHTML = agentRows.map(r => `
    <tr>
      <td>${r.tick}</td>
      <td>${r.location}</td>
      <td>${r.action}</td>
      <td>${r.mode || "-"}</td>
    </tr>
  `).join("");
}

function renderDecisions() {
  const { decisions } = state.runData;
  const agents = [...new Set(decisions.map(d => d.agent_id))].sort();
  const ticks = [...new Set(decisions.map(d => d.tick))].sort((a, b) => a - b);
  const actions = [...new Set(decisions.map(d => d.action))].sort();

  const fAgent = document.getElementById("filter-agent");
  const fTick = document.getElementById("filter-tick");
  const fAction = document.getElementById("filter-action");

  const prevAgent = fAgent.value;
  const prevTick = fTick.value;
  const prevAction = fAction.value;

  fAgent.innerHTML = '<option value="">All</option>' + agents.map(a => `<option value="${a}" ${a === prevAgent ? "selected" : ""}>${a}</option>`).join("");
  fTick.innerHTML = '<option value="">All</option>' + ticks.map(t => `<option value="${t}" ${String(t) === prevTick ? "selected" : ""}>${t}</option>`).join("");
  fAction.innerHTML = '<option value="">All</option>' + actions.map(a => `<option value="${a}" ${a === prevAction ? "selected" : ""}>${a}</option>`).join("");

  [fAgent, fTick, fAction].forEach(el => {
    el.onchange = () => renderDecisionList();
  });

  renderDecisionList();
}

function renderDecisionList() {
  const { decisions } = state.runData;
  const agentFilter = document.getElementById("filter-agent").value;
  const tickFilter = document.getElementById("filter-tick").value;
  const actionFilter = document.getElementById("filter-action").value;

  let filtered = decisions;
  if (agentFilter) filtered = filtered.filter(d => d.agent_id === agentFilter);
  if (tickFilter !== "") filtered = filtered.filter(d => d.tick == tickFilter);
  if (actionFilter) filtered = filtered.filter(d => d.action === actionFilter);

  const display = filtered.slice(0, 200);
  const list = document.getElementById("decision-list");

  list.innerHTML = display.map(d => {
    const meta = d.metadata || {};
    const isLLM = meta.decision_source === "llm";
    const llmInfo = isLLM
      ? `<span class="llm-badge">${meta.llm_provider}/${meta.llm_model} ${meta.llm_tokens || "?"}tok ${meta.llm_latency_ms || "?"}ms${meta.llm_cached ? " (cached)" : ""}</span>`
      : "";
    return `<div class="decision-card">
      <div class="decision-header">
        <span class="tick">T${d.tick}</span>
        <span class="agent">${d.agent_id}</span>
        <span class="action">${d.action} &rarr; ${d.target}</span>
        ${meta.mode ? `<span>${meta.mode}</span>` : ""}
      </div>
      <div class="decision-reasoning">${escapeHtml(d.reasoning || "")}</div>
      ${llmInfo ? `<div class="decision-meta">${llmInfo}</div>` : ""}
    </div>`;
  }).join("");

  if (filtered.length > 200) {
    list.innerHTML += `<p style="color:var(--text-dim);font-size:12px;padding:8px;">Showing 200 of ${filtered.length} decisions. Use filters to narrow.</p>`;
  }
}

function renderKPIs() {
  const kpiData = state.runData.kpis;
  const cards = document.getElementById("kpi-cards");
  const chartArea = document.getElementById("kpi-chart");

  if (!kpiData || !kpiData.kpis || Object.keys(kpiData.kpis).length === 0) {
    cards.innerHTML = '<p style="color:var(--text-dim);font-size:12px">No KPIs defined for this scenario.</p>';
    chartArea.innerHTML = "";
    return;
  }

  const kpis = kpiData.kpis;
  cards.innerHTML = Object.entries(kpis).map(([, k]) => `
    <div class="kpi-card">
      <div class="kpi-name">${k.name}</div>
      <div class="kpi-value">${formatKPI(k.overall, k.metric)}</div>
      <div class="kpi-unit">${k.unit} (${k.metric})</div>
      <div class="kpi-desc">${k.description || ""}</div>
    </div>
  `).join("");

  chartArea.innerHTML = Object.entries(kpis).map(([, k]) => {
    const perTick = k.per_tick || {};
    const values = Object.entries(perTick).sort((a, b) => Number(a[0]) - Number(b[0])).map(e => e[1]);
    const max = Math.max(...values, 0.001);
    const bars = values.map(v => `<div class="spark-bar" style="height:${(v / max * 100).toFixed(1)}%" title="${v}"></div>`).join("");
    return `<div class="kpi-sparkline">
      <h4>${k.name} (per tick)</h4>
      <div class="sparkline-row">${bars}</div>
    </div>`;
  }).join("");
}

function formatKPI(value, metric) {
  if (metric === "ratio") return (value * 100).toFixed(1) + "%";
  if (Number.isInteger(value)) return value.toString();
  return value.toFixed(2);
}

function renderExport() {
  const path = state.selectedRun?.path;
  if (!path) return;

  const files = [
    { name: "metadata.json", type: "JSON", desc: "Run summary and config" },
    { name: "decisions.jsonl", type: "JSONL", desc: "All agent decisions" },
    { name: "aggregate.csv", type: "CSV", desc: "Per-tick aggregate stats" },
    { name: "agent_states.jsonl", type: "JSONL", desc: "Per-tick agent snapshots" },
    { name: "narratives.jsonl", type: "JSONL", desc: "Decision reasoning traces" },
    { name: "kpis.json", type: "JSON", desc: "KPI evaluation results" },
    { name: "events.jsonl", type: "JSONL", desc: "Full simulation event log" },
    { name: "agent_summary.csv", type: "CSV", desc: "One row per agent" },
    { name: "config.json", type: "JSON", desc: "Resolved config snapshot" },
    { name: "scenario.yaml", type: "YAML", desc: "Original scenario file" },
  ];

  document.getElementById("export-links").innerHTML = files.map(f => `
    <a class="export-link" href="/api/runs/${path}/${f.name}" download="${f.name}">
      <div class="filename">${f.name}</div>
      <div class="filetype">${f.type} &mdash; ${f.desc}</div>
    </a>
  `).join("");
}

async function toggleLaunchPanel() {
  const panel = document.getElementById("launch-panel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden")) {
    try {
      const data = await api("/api/scenarios");
      const select = document.getElementById("launch-scenario");
      select.innerHTML = (data.scenarios || []).map(s =>
        `<option value="${s.path}">${s.name} (${s.filename})</option>`
      ).join("");
    } catch (e) {
      console.error("Failed to load scenarios:", e);
    }
  }
}

async function launchRun() {
  const scenarioPath = document.getElementById("launch-scenario").value;
  const seed = document.getElementById("launch-seed").value;
  const status = document.getElementById("launch-status");
  status.textContent = "Running...";

  try {
    const result = await api("/api/runs/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_path: scenarioPath, seed: seed || null }),
    });
    status.textContent = `Done! ${result.total_decisions} decisions.`;
    await loadRuns();
    if (result.run_path) selectRun(result.run_path);
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
