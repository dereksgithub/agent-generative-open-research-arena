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
  const [scenarioText, metadata, statesText, decisionsText, eventsText, kpis] =
    await Promise.all([
      fetchFileText(runPath, "scenario.yaml"),
      fetchFileJson(runPath, "metadata.json") as Promise<Metadata>,
      fetchFileText(runPath, "agent_states.jsonl"),
      fetchFileText(runPath, "decisions.jsonl"),
      fetchFileText(runPath, "events.jsonl").catch(() => ""),
      fetchFileJsonOptional(runPath, "kpis.json") as Promise<KPIData | null>,
    ]);

  const scenario = jsYaml.load(scenarioText) as Scenario;
  const agentStates = statesText ? parseJsonl<AgentState>(statesText) : [];
  const decisions = decisionsText ? parseJsonl<Decision>(decisionsText) : [];
  const events = eventsText ? parseJsonl<SimEvent>(eventsText) : [];

  return { scenario, metadata, agentStates, decisions, events, kpis };
}

/**
 * List available runs. Returns paths like ["demo_commute/20260404_152322"].
 * Tries the API first; returns empty array if unavailable.
 */
export async function listRuns(): Promise<Array<{ path: string; scenario: string; timestamp: string }>> {
  const resp = await tryFetch("/api/runs");
  if (resp) {
    const data = await resp.json();
    return data.runs ?? [];
  }
  return [];
}
