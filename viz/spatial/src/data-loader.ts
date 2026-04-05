/**
 * data-loader.ts — Load run output files.
 *
 * Strategy:
 * 1. Try the AGORA viz server API (proxy at /api/runs/...).
 * 2. If the API is unreachable, fall back to loading files directly from
 *    the Vite dev server, which serves ../../runs/ via the fs.allow config.
 */
import jsYaml from "js-yaml";
import type {
  RunData,
  RunListEntry,
  Scenario,
  Metadata,
  AgentState,
  Decision,
  SimEvent,
  KPIData,
} from "./types";

declare const __PROJECT_ROOT__: string;

function parseJsonl<T>(text: string): T[] {
  return text
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as T);
}

async function tryFetch(url: string): Promise<Response | null> {
  try {
    const resp = await fetch(url);
    if (resp.ok) return resp;
  } catch {
    // network error or server not running
  }
  return null;
}

async function fetchFileText(runPath: string, filename: string): Promise<string> {
  const projectRoot =
    typeof __PROJECT_ROOT__ === "string" ? __PROJECT_ROOT__ : "";

  // Try API first
  const apiResp = await tryFetch(`/api/runs/${runPath}/${filename}`);
  if (apiResp) return apiResp.text();

  // Fall back to direct file path (Vite serves ../../runs/ via fs.allow)
  const directResp = await tryFetch(`/../../runs/${runPath}/${filename}`);
  if (directResp) return directResp.text();

  // Try relative path from project root
  if (projectRoot) {
    const fsPath = encodeURI(`${projectRoot}/runs/${runPath}/${filename}`);
    const altResp = await tryFetch(`/@fs${fsPath}`);
    if (altResp) return altResp.text();
  }

  throw new Error(`Could not load ${filename} for run ${runPath}`);
}

async function fetchFileJson(runPath: string, filename: string): Promise<any> {
  const text = await fetchFileText(runPath, filename);
  return JSON.parse(text);
}

async function fetchFileJsonOptional(runPath: string, filename: string): Promise<any | null> {
  try {
    return await fetchFileJson(runPath, filename);
  } catch {
    return null;
  }
}

/**
 * Load all data for a run given its path (e.g. "demo_commute/20260404_152322").
 */
export async function loadRunData(runPath: string): Promise<RunData> {
  const [scenarioText, rawMetadata, statesText, decisionsText, eventsText, kpis] =
    await Promise.all([
      fetchFileText(runPath, "scenario.yaml"),
      fetchFileJsonOptional(runPath, "metadata.json"),
      fetchFileText(runPath, "agent_states.jsonl"),
      fetchFileText(runPath, "decisions.jsonl"),
      fetchFileText(runPath, "events.jsonl").catch(() => ""),
      fetchFileJsonOptional(runPath, "kpis.json") as Promise<KPIData | null>,
    ]);

  const scenario = jsYaml.load(scenarioText) as Scenario;
  const agentStates = statesText ? parseJsonl<AgentState>(statesText) : [];
  const decisions = decisionsText ? parseJsonl<Decision>(decisionsText) : [];
  const events = eventsText ? parseJsonl<SimEvent>(eventsText) : [];
  const metadata = normalizeMetadata(
    rawMetadata as Partial<Metadata> | null,
    runPath,
    scenario,
    decisions,
    agentStates
  );

  return { scenario, metadata, agentStates, decisions, events, kpis };
}

/**
 * List available runs. Returns paths like ["demo_commute/20260404_152322"].
 * Tries the API first; returns empty array if unavailable.
 */
export async function listRuns(): Promise<RunListEntry[]> {
  const resp = await tryFetch("/api/runs");
  if (resp) {
    const data = await resp.json();
    return data.runs ?? [];
  }
  return [];
}

function normalizeMetadata(
  rawMetadata: Partial<Metadata> | null,
  runPath: string,
  scenario: Scenario,
  decisions: Decision[],
  agentStates: AgentState[]
): Metadata {
  const metadata = rawMetadata ?? {};
  const inferredAgents = new Set(agentStates.map((state) => state.agent_id)).size
    || scenario.agents?.length
    || 0;
  const inferredTicks = maxTick([
    ...decisions.map((decision) => decision.tick),
    ...agentStates.map((state) => state.tick),
  ]) + 1;

  return {
    agora_version: String(metadata.agora_version ?? "unknown"),
    run_id: String(metadata.run_id ?? runPath.split("/").at(-1) ?? runPath),
    scenario_id: String(metadata.scenario_id ?? scenario.id ?? scenario.name ?? "unknown"),
    scenario_name: String(metadata.scenario_name ?? scenario.name ?? "unknown"),
    domain: String(metadata.domain ?? scenario.domain ?? "unknown"),
    decision_mode: String(metadata.decision_mode ?? "unknown"),
    total_ticks: toNumber(
      metadata.total_ticks,
      toNumber(scenario.simulation?.ticks, inferredTicks)
    ),
    total_agents: toNumber(metadata.total_agents, inferredAgents),
    total_decisions: toNumber(metadata.total_decisions, decisions.length),
    seed: toNumber(
      metadata.seed,
      toNumber(scenario.simulation?.seed, 0)
    ),
  };
}

function toNumber(value: unknown, fallback: number): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function maxTick(values: number[]): number {
  return values.length > 0 ? Math.max(...values) : -1;
}
