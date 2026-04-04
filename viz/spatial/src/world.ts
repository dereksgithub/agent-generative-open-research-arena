/**
 * world.ts — Build city geometry from scenario locations and routes.
 * Top-down isometric view with colored tiles for zones and styled lines for routes.
 */
import * as THREE from "three";
import type { ScenarioLocation, ScenarioRoute } from "./types";

const BASE_TILE_EMISSIVE_INTENSITY = 0.15;

/** Color palette by location type */
const LOCATION_COLORS: Record<string, number> = {
  residential: 0x66bb6a, // green
  commercial: 0x42a5f5, // blue
  transit_stop: 0xffa726, // orange
  healthcare: 0x26c6da, // cyan
  public: 0xffd54f, // yellow
  industrial: 0xbdbdbd, // grey
  park: 0x81c784, // light green
};

const TILE_SIZE = 1.8;
const SCALE = 1.5; // world-unit multiplier for (x,y) coordinates

/** Route line styles by mode */
const ROUTE_STYLES: Record<
  string,
  {
    color: number;
    pattern: "solid" | "dashed" | "dotted";
    opacity: number;
    dashSize?: number;
    gapSize?: number;
  }
> = {
  drive: { color: 0x90a4ae, pattern: "solid", opacity: 0.65 },
  transit: {
    color: 0xffa726,
    pattern: "dashed",
    opacity: 0.7,
    dashSize: 0.28,
    gapSize: 0.14,
  },
  walk: {
    color: 0xa5d6a7,
    pattern: "dotted",
    opacity: 0.75,
    dashSize: 0.045,
    gapSize: 0.14,
  },
};

export interface RouteVisual {
  from: string;
  to: string;
  mode: string;
  line: THREE.Line;
  baseColor: number;
  baseOpacity: number;
}

export interface WorldObjects {
  group: THREE.Group;
  locationPositions: Map<string, THREE.Vector3>;
  locationMeshes: Map<string, THREE.Mesh>;
  routeVisuals: RouteVisual[];
}

export function buildWorld(
  locations: ScenarioLocation[],
  routes: ScenarioRoute[]
): WorldObjects {
  const group = new THREE.Group();
  const locationPositions = new Map<string, THREE.Vector3>();
  const locationMeshes = new Map<string, THREE.Mesh>();
  const routeVisuals: RouteVisual[] = [];

  // Location tiles — raised boxes with bright fills
  for (const loc of locations) {
    const color = LOCATION_COLORS[loc.type] ?? 0x9e9e9e;
    const geo = new THREE.BoxGeometry(TILE_SIZE, 0.25, TILE_SIZE);
    const mat = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.6,
      metalness: 0.05,
      emissive: color,
      emissiveIntensity: BASE_TILE_EMISSIVE_INTENSITY,
    });
    const mesh = new THREE.Mesh(geo, mat);
    const pos = new THREE.Vector3(loc.x * SCALE, 0.125, -loc.y * SCALE);
    mesh.position.copy(pos);
    mesh.userData = {
      locationId: loc.id,
      name: loc.name,
      type: loc.type,
      baseColor: color,
      baseEmissiveIntensity: BASE_TILE_EMISSIVE_INTENSITY,
    };
    group.add(mesh);

    locationPositions.set(loc.id, pos.clone());
    locationMeshes.set(loc.id, mesh);

    // Label (canvas texture sprite)
    const label = makeLabel(loc.name, color);
    label.position.set(pos.x, 0.5, pos.z);
    group.add(label);
  }

  // Route lines
  const drawnPairs = new Set<string>();
  for (const route of routes) {
    const pairKey = [route.from, route.to].sort().join("|") + "|" + route.mode;
    if (drawnPairs.has(pairKey)) continue;
    drawnPairs.add(pairKey);

    const fromPos = locationPositions.get(route.from);
    const toPos = locationPositions.get(route.to);
    if (!fromPos || !toPos) continue;

    const style = ROUTE_STYLES[route.mode] ?? ROUTE_STYLES.drive;
    const points = [
      new THREE.Vector3(fromPos.x, 0.02, fromPos.z),
      new THREE.Vector3(toPos.x, 0.02, toPos.z),
    ];
    const geo = new THREE.BufferGeometry().setFromPoints(points);

    let line: THREE.Line;
    if (style.pattern === "solid") {
      const mat = new THREE.LineBasicMaterial({
        color: style.color,
        transparent: true,
        opacity: style.opacity,
      });
      line = new THREE.Line(geo, mat);
    } else {
      const mat = new THREE.LineDashedMaterial({
        color: style.color,
        dashSize: style.dashSize ?? 0.2,
        gapSize: style.gapSize ?? 0.1,
        linewidth: 1,
        transparent: true,
        opacity: style.opacity,
      });
      line = new THREE.Line(geo, mat);
      line.computeLineDistances();
    }
    group.add(line);

    routeVisuals.push({
      from: route.from,
      to: route.to,
      mode: route.mode,
      line,
      baseColor: style.color,
      baseOpacity: style.opacity,
    });
  }

  return { group, locationPositions, locationMeshes, routeVisuals };
}

function makeLabel(text: string, tintColor: number): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  canvas.width = 256;
  canvas.height = 64;

  ctx.fillStyle = `#${tintColor.toString(16).padStart(6, "0")}`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.globalAlpha = 0.85;
  ctx.fillStyle = "#1a1a2e";
  ctx.fillRect(2, 2, canvas.width - 4, canvas.height - 4);
  ctx.globalAlpha = 1;

  ctx.font = "bold 24px monospace";
  ctx.fillStyle = "#e0e0e0";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(1.6, 0.4, 1);
  return sprite;
}

/**
 * Apply a visual tint to a location tile (for interventions).
 */
export function tintLocation(
  mesh: THREE.Mesh,
  color: number,
  intensity: number
): void {
  const mat = mesh.material as THREE.MeshStandardMaterial;
  mat.emissive.setHex(color);
  mat.emissiveIntensity = intensity;
}

export function clearTint(mesh: THREE.Mesh): void {
  const mat = mesh.material as THREE.MeshStandardMaterial;
  mat.emissive.setHex(mesh.userData.baseColor ?? 0x000000);
  mat.emissiveIntensity = mesh.userData.baseEmissiveIntensity ?? 0;
}

export function tintRoute(
  routeVisual: RouteVisual,
  color: number,
  opacity: number
): void {
  const mat = routeVisual.line.material as
    | THREE.LineBasicMaterial
    | THREE.LineDashedMaterial;
  mat.color.setHex(color);
  mat.opacity = opacity;
  mat.needsUpdate = true;
}

export function clearRouteTint(routeVisual: RouteVisual): void {
  const mat = routeVisual.line.material as
    | THREE.LineBasicMaterial
    | THREE.LineDashedMaterial;
  mat.color.setHex(routeVisual.baseColor);
  mat.opacity = routeVisual.baseOpacity;
  mat.needsUpdate = true;
}
