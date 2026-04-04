/**
 * agents.ts — Agent sprites, movement animation, and speech bubbles.
 * Each agent is a colored circle sprite with a name label.
 * On tick change, agents lerp from previous to current location.
 */
import * as THREE from "three";
import type { AgentState, Decision } from "./types";

/** Color palette by agent role */
const ROLE_COLORS: Record<string, number> = {
  commuter: 0x42a5f5,
  student: 0xab47bc,
  retiree: 0xff7043,
  worker: 0x66bb6a,
  resident: 0x78909c,
};

const AGENT_Y = 0.45;
const AGENT_SCALE = 0.45;

export interface AgentSprite {
  id: string;
  name: string;
  role: string;
  group: THREE.Group;
  trail: THREE.Line;
  dot: THREE.Sprite;
  label: THREE.Sprite;
  bubble: THREE.Sprite | null;
  currentPos: THREE.Vector3;
  targetPos: THREE.Vector3;
  trailPoints: THREE.Vector3[];
  lerpT: number;
  initialized: boolean;
}

export interface AgentManager {
  sprites: Map<string, AgentSprite>;
  group: THREE.Group;
  update(dt: number): void;
  setTick(
    tick: number,
    agentStates: AgentState[],
    decisions: Decision[],
    locationPositions: Map<string, THREE.Vector3>
  ): void;
  showBubble(agentId: string, text: string): void;
  hideBubbles(): void;
  getHovered(raycaster: THREE.Raycaster): AgentSprite | null;
}

export function createAgentManager(): AgentManager {
  const sprites = new Map<string, AgentSprite>();
  const group = new THREE.Group();

  function getOrCreateSprite(state: AgentState): AgentSprite {
    if (sprites.has(state.agent_id)) return sprites.get(state.agent_id)!;

    const color = ROLE_COLORS[state.role] ?? 0x9e9e9e;
    const agentGroup = new THREE.Group();
    const trailGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3()]);
    const trailMat = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.2,
    });
    const trail = new THREE.Line(trailGeo, trailMat);
    group.add(trail);

    // Dot sprite
    const dotTex = makeDotTexture(color);
    const dotMat = new THREE.SpriteMaterial({ map: dotTex, transparent: true });
    const dot = new THREE.Sprite(dotMat);
    dot.scale.set(AGENT_SCALE, AGENT_SCALE, 1);
    dot.position.y = AGENT_Y;
    agentGroup.add(dot);

    // Name label
    const labelTex = makeTextTexture(state.agent_name, "#ffffff", 18);
    const labelMat = new THREE.SpriteMaterial({
      map: labelTex,
      transparent: true,
    });
    const label = new THREE.Sprite(labelMat);
    label.scale.set(0.7, 0.2, 1);
    label.position.y = AGENT_Y + 0.28;
    agentGroup.add(label);

    group.add(agentGroup);

    const sprite: AgentSprite = {
      id: state.agent_id,
      name: state.agent_name,
      role: state.role,
      group: agentGroup,
      trail,
      dot,
      label,
      bubble: null,
      currentPos: new THREE.Vector3(),
      targetPos: new THREE.Vector3(),
      trailPoints: [],
      lerpT: 1,
      initialized: false,
    };
    sprites.set(state.agent_id, sprite);
    return sprite;
  }

  function setTick(
    tick: number,
    agentStates: AgentState[],
    decisions: Decision[],
    locationPositions: Map<string, THREE.Vector3>
  ): void {
    const tickStates = agentStates.filter((s) => s.tick === tick);

    // Offset agents at the same location so they don't overlap
    const locationAgents = new Map<string, number>();

    for (const state of tickStates) {
      const sprite = getOrCreateSprite(state);
      const locPos = locationPositions.get(state.location);
      if (!locPos) continue;

      const count = locationAgents.get(state.location) ?? 0;
      locationAgents.set(state.location, count + 1);

      // Fan out agents around the location center
      const angle = (count * Math.PI * 2) / 5 + Math.PI / 4;
      const radius = 0.35;
      const offset = new THREE.Vector3(
        Math.cos(angle) * radius,
        0,
        Math.sin(angle) * radius
      );
      const nextPos = locPos.clone().add(offset);

      if (!sprite.initialized) {
        sprite.group.position.copy(nextPos);
        sprite.currentPos.copy(nextPos);
        sprite.targetPos.copy(nextPos);
        sprite.lerpT = 1;
        sprite.initialized = true;
      } else {
        sprite.currentPos.copy(sprite.group.position);
        sprite.targetPos.copy(nextPos);
        sprite.lerpT = 0;
      }

      pushTrailPoint(sprite, nextPos);
    }

    // Hide bubble on tick change
    hideBubbles();
  }

  function update(dt: number): void {
    for (const sprite of sprites.values()) {
      if (sprite.lerpT < 1) {
        sprite.lerpT = Math.min(1, sprite.lerpT + dt * 3);
        sprite.group.position.lerpVectors(
          sprite.currentPos,
          sprite.targetPos,
          easeOutCubic(sprite.lerpT)
        );
      }
    }
  }

  function showBubble(agentId: string, text: string): void {
    const sprite = sprites.get(agentId);
    if (!sprite) return;

    // Remove existing bubble
    if (sprite.bubble) {
      sprite.group.remove(sprite.bubble);
      sprite.bubble = null;
    }

    const truncated = text.length > 120 ? text.slice(0, 117) + "..." : text;
    const tex = makeBubbleTexture(truncated);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
    const bubble = new THREE.Sprite(mat);
    bubble.scale.set(2.2, 0.7, 1);
    bubble.position.y = AGENT_Y + 0.7;
    sprite.group.add(bubble);
    sprite.bubble = bubble;
  }

  function hideBubbles(): void {
    for (const sprite of sprites.values()) {
      if (sprite.bubble) {
        sprite.group.remove(sprite.bubble);
        sprite.bubble = null;
      }
    }
  }

  function getHovered(raycaster: THREE.Raycaster): AgentSprite | null {
    const dots = [...sprites.values()].map((s) => s.dot);
    const intersects = raycaster.intersectObjects(dots);
    if (intersects.length === 0) return null;
    const hit = intersects[0].object;
    for (const sprite of sprites.values()) {
      if (sprite.dot === hit) return sprite;
    }
    return null;
  }

  return { sprites, group, update, setTick, showBubble, hideBubbles, getHovered };
}

// --- Canvas texture helpers ---

function makeDotTexture(color: number): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  ctx.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.stroke();
  return new THREE.CanvasTexture(canvas);
}

function makeTextTexture(
  text: string,
  color: string,
  fontSize: number
): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.font = `bold ${fontSize}px monospace`;
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  return new THREE.CanvasTexture(canvas);
}

function makeBubbleTexture(text: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 160;
  const ctx = canvas.getContext("2d")!;

  // Background
  ctx.fillStyle = "rgba(30, 30, 50, 0.92)";
  roundRect(ctx, 4, 4, canvas.width - 8, canvas.height - 8, 16);
  ctx.fill();
  ctx.strokeStyle = "#7c4dff";
  ctx.lineWidth = 2;
  roundRect(ctx, 4, 4, canvas.width - 8, canvas.height - 8, 16);
  ctx.stroke();

  // Text (word-wrap)
  ctx.font = "14px monospace";
  ctx.fillStyle = "#e0e0e0";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  wrapText(ctx, text, 16, 16, canvas.width - 32, 18);

  return new THREE.CanvasTexture(canvas);
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number
): void {
  const words = text.split(" ");
  let line = "";
  let curY = y;
  for (const word of words) {
    const test = line + word + " ";
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line.trim(), x, curY);
      line = word + " ";
      curY += lineHeight;
    } else {
      line = test;
    }
  }
  ctx.fillText(line.trim(), x, curY);
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function pushTrailPoint(sprite: AgentSprite, position: THREE.Vector3): void {
  const last = sprite.trailPoints[sprite.trailPoints.length - 1];
  if (last && last.distanceToSquared(position) < 0.0001) {
    return;
  }

  sprite.trailPoints.push(new THREE.Vector3(position.x, 0.08, position.z));
  if (sprite.trailPoints.length > 6) {
    sprite.trailPoints.shift();
  }

  sprite.trail.geometry.dispose();
  sprite.trail.geometry = new THREE.BufferGeometry().setFromPoints(
    sprite.trailPoints.length > 1
      ? sprite.trailPoints
      : [sprite.trailPoints[0], sprite.trailPoints[0]]
  );
}
