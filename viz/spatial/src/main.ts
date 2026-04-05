/**
 * main.ts — Scene setup, camera, renderer, tick loop.
 * Entry point for the AGORA spatial viewer.
 *
 * Works identically for heuristic and LLM runs — both produce the
 * same output file format; only the reasoning text differs.
 */
import * as THREE from "three";
import { loadRunData, listRuns } from "./data-loader";
import { buildWorld } from "./world";
import { createAgentManager } from "./agents";
import { createPlayback } from "./playback";
import { createInterventionManager } from "./interventions";
import { createHUD } from "./hud";
import type { RunData, RunListEntry } from "./types";

const loadingEl = document.getElementById("loading")!;

function showStatus(msg: string): void {
  loadingEl.textContent = msg;
  loadingEl.classList.remove("hidden");
  console.log("[spatial]", msg);
}

async function autoDetectRun(): Promise<string | null> {
  const runs = await listRuns();
  const firstReadyRun = runs.find((run) => run.ready !== false);
  if (firstReadyRun) return firstReadyRun.path;
  return null;
}

async function showRunPicker(): Promise<string> {
  const runs = await listRuns();

  const picker = document.getElementById("run-picker")!;
  picker.classList.remove("hidden");
  loadingEl.classList.add("hidden");

  const list = document.getElementById("run-list-picker")!;
  const hint = picker.querySelector(".picker-hint") as HTMLElement;
  const manualInput = document.getElementById("run-path-input") as HTMLInputElement;
  const goBtn = document.getElementById("btn-go") as HTMLButtonElement;

  if (runs.length > 0) {
    const readyRuns = runs.filter((run) => run.ready !== false);
    hint.textContent = readyRuns.length > 0
      ? "Select a simulation run to visualise:"
      : "No complete runs found yet. Broken runs are shown below for reference.";
    list.innerHTML = runs.map(renderRunOption).join("");
  } else {
    hint.innerHTML = "Select a simulation run to visualise:";
    list.innerHTML =
      '<p class="picker-hint">No runs found. Start the viz server (<code>agora viz</code>) or enter a run path manually.</p>';
  }

  return new Promise((resolve) => {
    list.addEventListener("click", (e) => {
      const btn = (e.target as HTMLElement).closest(".run-option") as HTMLElement | null;
      if (btn?.dataset.path && btn.dataset.ready === "true") {
        picker.classList.add("hidden");
        resolve(btn.dataset.path);
      }
    });
    goBtn.addEventListener("click", () => {
      const val = manualInput.value.trim();
      if (val) {
        picker.classList.add("hidden");
        resolve(val);
      }
    });
    manualInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") goBtn.click();
    });
  });
}

async function main(): Promise<void> {
  const canvas = document.getElementById("viewer") as HTMLCanvasElement;
  const uiContainer = document.getElementById("ui-overlay") as HTMLElement;

  // --- Determine which run to load ---
  let runPath = location.hash.slice(1);

  if (!runPath) {
    showStatus("Connecting to AGORA viz server...");
    const detected = await autoDetectRun();
    if (detected) {
      runPath = detected;
      location.hash = runPath;
    } else {
      runPath = await showRunPicker();
      location.hash = runPath;
    }
  }

  showStatus(`Loading run: ${runPath}`);

  let runData: RunData;
  try {
    runData = await loadRunData(runPath);
  } catch (e) {
    showStatus(
      `Failed to load run "${runPath}".\n\n` +
        `Make sure the viz server is running:\n` +
        `  source .venv/bin/activate && agora viz\n\n` +
        `Error: ${e}`
    );
    return;
  }

  // --- Validate ---
  const locs = runData.scenario?.locations ?? [];
  const states = runData.agentStates ?? [];
  const mode = runData.metadata?.decision_mode ?? "unknown";

  console.log("[spatial] Run loaded:", {
    scenario: runData.scenario?.name,
    mode,
    locations: locs.length,
    agents: runData.metadata?.total_agents,
    ticks: runData.metadata?.total_ticks,
    agentStates: states.length,
    decisions: runData.decisions?.length,
    events: runData.events?.length,
  });

  if (locs.length === 0) {
    showStatus("Run loaded but scenario has no locations. Check the run output.");
    return;
  }

  if (states.length === 0) {
    showStatus("Run loaded but has no agent state data. The simulation may have produced no ticks.");
    return;
  }

  loadingEl.classList.add("hidden");
  canvas.classList.remove("hidden");
  uiContainer.classList.remove("hidden");

  // --- Three.js setup ---
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x1a1a2e);

  const scene = new THREE.Scene();

  // --- Build world geometry first so we can frame the camera ---
  const world = buildWorld(locs, runData.scenario.routes ?? []);
  scene.add(world.group);

  // Compute world bounds from location positions
  const positions = [...world.locationPositions.values()];
  const bbox = new THREE.Box3();
  for (const p of positions) bbox.expandByPoint(p);
  const center = new THREE.Vector3();
  bbox.getCenter(center);
  const size = new THREE.Vector3();
  bbox.getSize(size);
  const worldSpan = Math.max(size.x, size.z, 4) + 4; // padding

  console.log("[spatial] World bounds:", {
    center: { x: center.x.toFixed(1), z: center.z.toFixed(1) },
    span: worldSpan.toFixed(1),
    locationCount: positions.length,
  });

  // --- Orthographic camera auto-framed to world ---
  const aspect = window.innerWidth / window.innerHeight;
  let frustumSize = worldSpan;
  const camera = new THREE.OrthographicCamera(
    (-frustumSize * aspect) / 2,
    (frustumSize * aspect) / 2,
    frustumSize / 2,
    -frustumSize / 2,
    0.1,
    200
  );
  // Top-down with slight isometric tilt
  camera.position.set(center.x, 20, center.z + 8);
  camera.lookAt(center.x, 0, center.z);

  // Lighting
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(center.x + 5, 15, center.z - 5);
  scene.add(dirLight);

  // --- Grid helper for visual grounding ---
  const grid = new THREE.GridHelper(worldSpan * 1.5, 20, 0x2a2a4e, 0x222244);
  grid.position.set(center.x, 0, center.z);
  scene.add(grid);

  // --- Agents ---
  const agentMgr = createAgentManager();
  scene.add(agentMgr.group);

  // --- Interventions ---
  const interventionMgr = createInterventionManager(
    runData.events ?? [],
    runData.scenario.interventions ?? [],
    world
  );
  scene.add(interventionMgr.group);

  const totalTicks = runData.metadata?.total_ticks || 24;
  const tickUnit = runData.scenario.simulation?.tick_unit ?? "tick";

  // --- HUD ---
  const hud = createHUD(uiContainer, runData, interventionMgr.visuals);

  let hoveredAgentId: string | null = null;
  let pinnedAgentId: string | null = null;

  // --- Playback ---
  const playback = createPlayback(totalTicks, (tick) => {
    agentMgr.setTick(tick, states, runData.decisions ?? [], world.locationPositions);
    interventionMgr.setTick(tick);
    hud.update(tick);
    renderAgentBubble(pinnedAgentId ?? hoveredAgentId);
  }, { tickUnit });
  playback.bindUI(uiContainer);

  // --- Set initial tick ---
  playback.setTick(0);
  console.log("[spatial] Scene ready. Tick 0 set.");

  // --- Mouse interaction for speech bubbles ---
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  function pickAgentUnderPointer(): string | null {
    raycaster.setFromCamera(mouse, camera);
    return agentMgr.getHovered(raycaster)?.id ?? null;
  }

  function renderAgentBubble(agentId: string | null): void {
    if (!agentId) {
      agentMgr.hideBubbles();
      return;
    }

    const sprite = agentMgr.sprites.get(agentId);
    if (!sprite) {
      agentMgr.hideBubbles();
      return;
    }

    const decision = (runData.decisions ?? []).find(
      (d) => d.agent_id === agentId && d.tick === playback.currentTick
    );
    const reasoning =
      typeof decision?.reasoning === "string" && decision.reasoning.trim()
        ? decision.reasoning
        : "(no reasoning recorded)";
    const text = decision
      ? `${sprite.name}: ${reasoning}`
      : `${sprite.name}: (no decision this tick)`;
    agentMgr.showBubble(agentId, text);
  }

  canvas.addEventListener("mousemove", (e) => {
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    if (!isDragging && !pinnedAgentId) {
      const nextHover = pickAgentUnderPointer();
      if (nextHover !== hoveredAgentId) {
        hoveredAgentId = nextHover;
        renderAgentBubble(hoveredAgentId);
      }
    }
  });

  canvas.addEventListener("click", () => {
    const hitId = pickAgentUnderPointer();
    if (hitId) {
      pinnedAgentId = pinnedAgentId === hitId ? null : hitId;
      renderAgentBubble(pinnedAgentId ?? hoveredAgentId);
    } else {
      pinnedAgentId = null;
      hoveredAgentId = null;
      renderAgentBubble(null);
    }
  });

  // --- Pan / zoom ---
  let isDragging = false;
  let dragStart = { x: 0, y: 0 };
  let camStart = { x: camera.position.x, z: camera.position.z };
  let targetStart = { x: center.x, z: center.z };
  const cameraTarget = new THREE.Vector3(center.x, 0, center.z);

  canvas.addEventListener("mousedown", (e) => {
    if (e.button === 0) {
      isDragging = true;
      dragStart = { x: e.clientX, y: e.clientY };
      camStart = { x: camera.position.x, z: camera.position.z };
      targetStart = { x: cameraTarget.x, z: cameraTarget.z };
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const scale = frustumSize / window.innerHeight / camera.zoom;
    const offsetX = (e.clientX - dragStart.x) * scale;
    const offsetZ = (e.clientY - dragStart.y) * scale;
    camera.position.x = camStart.x - offsetX;
    camera.position.z = camStart.z - offsetZ;
    cameraTarget.x = targetStart.x - offsetX;
    cameraTarget.z = targetStart.z - offsetZ;
    camera.lookAt(cameraTarget);
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
  });

  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      camera.zoom = Math.max(0.2, Math.min(8, camera.zoom * factor));
      camera.updateProjectionMatrix();
    },
    { passive: false }
  );

  // --- Keyboard ---
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space") {
      e.preventDefault();
      playback.toggle();
    } else if (e.code === "ArrowRight") {
      playback.stepForward();
    } else if (e.code === "ArrowLeft") {
      playback.stepBackward();
    } else if (e.code === "KeyR") {
      // Reset camera
      camera.position.set(center.x, 20, center.z + 8);
      cameraTarget.set(center.x, 0, center.z);
      camera.lookAt(cameraTarget);
      camera.zoom = 1;
      camera.updateProjectionMatrix();
    }
  });

  // --- Resize ---
  window.addEventListener("resize", () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const a = w / h;
    camera.left = (-frustumSize * a) / 2;
    camera.right = (frustumSize * a) / 2;
    camera.top = frustumSize / 2;
    camera.bottom = -frustumSize / 2;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });

  // --- Render loop ---
  const clock = new THREE.Clock();

  function animate(): void {
    requestAnimationFrame(animate);
    const dt = clock.getDelta();
    playback.update(dt);
    agentMgr.update(dt);
    renderer.render(scene, camera);
  }

  animate();
}

main().catch((err) => {
  console.error("[spatial] Fatal:", err);
  showStatus(`Fatal error: ${err}`);
});

function renderRunOption(run: RunListEntry): string {
  const ready = run.ready !== false;
  const issueText = Array.isArray(run.issues) ? run.issues.join(" · ") : "";
  return `
    <button
      class="run-option ${ready ? "" : "run-option--invalid"}"
      data-path="${ready ? run.path : ""}"
      data-ready="${ready}"
      ${ready ? "" : "disabled"}
    >
      <span class="run-option__title">
        ${escapeHtml(run.scenario)}
        <span class="run-ts">${escapeHtml(run.timestamp)}</span>
      </span>
      ${ready ? "" : `<span class="run-option__issue">${escapeHtml(issueText || "Incomplete run artifacts")}</span>`}
    </button>
  `;
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
