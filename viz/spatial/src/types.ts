/** Shared types for the AGORA spatial viewer */

export interface ScenarioLocation {
  id: string;
  name: string;
  type: string; // residential, commercial, transit_stop, etc.
  x: number;
  y: number;
  resources?: Record<string, number>;
}

export interface ScenarioRoute {
  from: string;
  to: string;
  mode: string; // drive, transit, walk
  travel_time_minutes: number;
}

export interface ScenarioIntervention {
  tick: number;
  name: string;
  description: string;
  effects: Record<string, number>;
  duration?: number | null;
  target_roles?: string[];
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  domain: string;
  simulation: { ticks: number; tick_unit: string; seed: number };
  locations: ScenarioLocation[];
  routes: ScenarioRoute[];
  agents: ScenarioAgent[];
  interventions: ScenarioIntervention[];
  kpis: ScenarioKPI[];
}

export interface ScenarioAgent {
  id: string;
  name: string;
  role: string;
  traits: string[];
  home_location: string;
  work_location?: string;
  preferred_mode?: string;
}

export interface ScenarioKPI {
  id: string;
  name: string;
  description: string;
  metric: string;
  unit: string;
}

export interface AgentState {
  run_id: string;
  tick: number;
  agent_id: string;
  agent_name: string;
  role: string;
  location: string;
  action: string;
  mode: string;
  traits: string[];
}

export interface Decision {
  tick: number;
  agent_id: string;
  action: string;
  target: string;
  reasoning: string;
  metadata: Record<string, unknown>;
}

export interface SimEvent {
  event_id: number;
  run_id: string;
  tick: number;
  event_type: string;
  agent_id: string | null;
  data: Record<string, unknown>;
}

export interface KPIData {
  run_id: string;
  scenario_id: string;
  kpis: Record<
    string,
    {
      name: string;
      description: string;
      metric: string;
      unit: string;
      overall: number;
      per_tick: Record<string, number>;
    }
  >;
}

export interface Metadata {
  agora_version: string;
  run_id: string;
  scenario_id: string;
  scenario_name: string;
  domain: string;
  decision_mode: string;
  total_ticks: number;
  total_agents: number;
  total_decisions: number;
  seed: number;
}

/** All loaded data for a single run */
export interface RunData {
  scenario: Scenario;
  metadata: Metadata;
  agentStates: AgentState[];
  decisions: Decision[];
  events: SimEvent[];
  kpis: KPIData | null;
}
