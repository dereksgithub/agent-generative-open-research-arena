/**
 * interventions.ts — Visual markers for policy activations.
 * Reads events.jsonl for intervention_applied events and shows
 * tinted overlays, icons, or zone highlights while active.
 */
import * as THREE from "three";
import type { SimEvent, ScenarioIntervention } from "./types";
import type { WorldObjects } from "./world";
import { clearRouteTint, clearTint, tintLocation, tintRoute } from "./world";

export interface InterventionVisual {
  name: string;
  startTick: number;
  duration: number | null; // null = permanent
  effects: Record<string, unknown>;
  active: boolean;
  color: number;
  strength: number;
  locationIds: string[];
  routeModes: string[];
}

export interface InterventionManager {
  visuals: InterventionVisual[];
  group: THREE.Group;
  setTick(tick: number): void;
}

export function createInterventionManager(
  events: SimEvent[],
  scenarioInterventions: ScenarioIntervention[],
  world: WorldObjects
): InterventionManager {
  const group = new THREE.Group();
  const interventionEvents = events.filter(
    (e) => e.event_type === "intervention_applied"
  );

  const visuals: InterventionVisual[] = interventionEvents.map((ev) => {
    const scenDef = scenarioInterventions.find(
      (si) => si.name === (ev.data.name as string)
    );
    const effects = (ev.data.effects as Record<string, unknown>) ?? {};
    const targets = deriveTargets(effects, world);

    return {
      name: (ev.data.name as string) || "unnamed",
      startTick: ev.tick,
      duration: (ev.data.duration as number | null) ?? scenDef?.duration ?? null,
      effects,
      active: false,
      color: targets.color,
      strength: 0,
      locationIds: targets.locationIds,
      routeModes: targets.routeModes,
    };
  });
  const markersByVisual = new Map<InterventionVisual, THREE.Mesh[]>();

  for (const visual of visuals) {
    const markers = visual.locationIds
      .map((locationId) => {
        const pos = world.locationPositions.get(locationId);
        if (!pos) return null;
        const marker = makeZoneMarker(visual.color);
        marker.position.set(pos.x, 0.04, pos.z);
        group.add(marker);
        return marker;
      })
      .filter((marker): marker is THREE.Mesh => marker !== null);
    markersByVisual.set(visual, markers);
  }

  function setTick(tick: number): void {
    // Clear all tints first
    for (const mesh of world.locationMeshes.values()) {
      clearTint(mesh);
    }
    for (const route of world.routeVisuals) {
      clearRouteTint(route);
    }
    for (const markers of markersByVisual.values()) {
      for (const marker of markers) {
        marker.visible = false;
      }
    }

    for (const vis of visuals) {
      const endTick =
        vis.duration != null ? vis.startTick + vis.duration : Infinity;
      vis.active = tick >= vis.startTick && tick < endTick;
      vis.strength = vis.active ? computeStrength(tick, endTick) : 0;

      if (vis.active) {
        for (const locationId of vis.locationIds) {
          const mesh = world.locationMeshes.get(locationId);
          if (!mesh) continue;
          tintLocation(mesh, vis.color, 0.18 + vis.strength * 0.22);
        }

        for (const route of world.routeVisuals) {
          if (vis.routeModes.includes(route.mode)) {
            tintRoute(route, vis.color, 0.45 + vis.strength * 0.4);
          }
        }

        const markers = markersByVisual.get(vis) ?? [];
        for (const marker of markers) {
          marker.visible = true;
          marker.scale.setScalar(1 + (1 - vis.strength) * 0.25);
          const mat = marker.material as THREE.MeshBasicMaterial;
          mat.opacity = 0.1 + vis.strength * 0.22;
        }
      }
    }
  }

  return { visuals, group, setTick };
}

function deriveTargets(
  effects: Record<string, unknown>,
  world: WorldObjects
): { color: number; locationIds: string[]; routeModes: string[] } {
  const driveCost = "drive_cost_multiplier" in effects;
  const walkCost = "walk_cost_multiplier" in effects;
  const transitCost = "transit_cost_multiplier" in effects;

  if (driveCost) {
    return {
      color: 0xff1744,
      locationIds: getLocationIdsByType(world, ["commercial"]),
      routeModes: ["drive"],
    };
  }

  if (walkCost || transitCost) {
    const healthTargets = getLocationIdsByType(world, ["healthcare", "public"]);
    return {
      color: 0x66bb6a,
      locationIds:
        healthTargets.length > 0
          ? healthTargets
          : [...world.locationMeshes.keys()],
      routeModes: [
        ...(walkCost ? ["walk"] : []),
        ...(transitCost ? ["transit"] : []),
      ],
    };
  }

  return {
    color: 0x7c4dff,
    locationIds: [...world.locationMeshes.keys()],
    routeModes: [],
  };
}

function getLocationIdsByType(world: WorldObjects, types: string[]): string[] {
  const targets = new Set(types);
  return [...world.locationMeshes.entries()]
    .filter(([, mesh]) => targets.has(String(mesh.userData.type)))
    .map(([id]) => id);
}

function computeStrength(tick: number, endTick: number): number {
  if (!Number.isFinite(endTick)) return 1;
  const remainingTicks = endTick - tick;
  if (remainingTicks <= 1) return 0.35;
  if (remainingTicks <= 2) return 0.6;
  return 1;
}

function makeZoneMarker(color: number): THREE.Mesh {
  const geometry = new THREE.RingGeometry(0.62, 0.9, 24);
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
  });
  const marker = new THREE.Mesh(geometry, material);
  marker.rotation.x = -Math.PI / 2;
  marker.visible = false;
  return marker;
}
