/**
 * playback.ts — Tick playback controller.
 * Play / Pause / Step / Speed / Scrubber bar.
 */

export type PlaybackCallback = (tick: number) => void;

export interface PlaybackOptions {
  tickUnit?: string;
}

export interface PlaybackController {
  currentTick: number;
  totalTicks: number;
  playing: boolean;
  speed: number;
  play(): void;
  pause(): void;
  toggle(): void;
  stepForward(): void;
  stepBackward(): void;
  setTick(tick: number): void;
  setSpeed(speed: number): void;
  update(dt: number): void;
  bindUI(container: HTMLElement): void;
}

export function createPlayback(
  totalTicks: number,
  onTick: PlaybackCallback,
  options: PlaybackOptions = {}
): PlaybackController {
  let currentTick = 0;
  let playing = false;
  let speed = 1;
  let accumulator = 0;
  const tickUnit = options.tickUnit?.trim();

  // UI elements (bound later)
  let tickLabel: HTMLElement | null = null;
  let scrubber: HTMLInputElement | null = null;
  let playBtn: HTMLButtonElement | null = null;
  let speedLabel: HTMLElement | null = null;

  function emitTick(): void {
    onTick(currentTick);
    if (tickLabel) {
      const unitSuffix = tickUnit ? ` · ${tickUnit}` : "";
      tickLabel.textContent = `Tick ${currentTick} / ${totalTicks - 1}${unitSuffix}`;
    }
    if (scrubber) scrubber.value = String(currentTick);
  }

  function play(): void {
    playing = true;
    if (playBtn) playBtn.textContent = "⏸";
  }

  function pause(): void {
    playing = false;
    if (playBtn) playBtn.textContent = "▶";
  }

  function toggle(): void {
    playing ? pause() : play();
  }

  function stepForward(): void {
    pause();
    if (currentTick < totalTicks - 1) {
      currentTick++;
      emitTick();
    }
  }

  function stepBackward(): void {
    pause();
    if (currentTick > 0) {
      currentTick--;
      emitTick();
    }
  }

  function setTick(tick: number): void {
    currentTick = Math.max(0, Math.min(totalTicks - 1, tick));
    emitTick();
  }

  function setSpeed(s: number): void {
    speed = s;
    if (speedLabel) speedLabel.textContent = `${speed}x`;
  }

  function update(dt: number): void {
    if (!playing) return;
    accumulator += dt * speed;
    const tickInterval = 0.8; // seconds per tick at 1x
    while (accumulator >= tickInterval) {
      accumulator -= tickInterval;
      if (currentTick < totalTicks - 1) {
        currentTick++;
        emitTick();
      } else {
        pause();
        break;
      }
    }
  }

  function bindUI(container: HTMLElement): void {
    const bar = container.querySelector("#playback-bar") as HTMLElement;
    if (!bar) return;

    playBtn = bar.querySelector("#btn-play") as HTMLButtonElement;
    const stepBackBtn = bar.querySelector("#btn-step-back") as HTMLButtonElement;
    const stepFwdBtn = bar.querySelector("#btn-step-fwd") as HTMLButtonElement;
    const speedDownBtn = bar.querySelector("#btn-speed-down") as HTMLButtonElement;
    const speedUpBtn = bar.querySelector("#btn-speed-up") as HTMLButtonElement;
    tickLabel = bar.querySelector("#tick-label") as HTMLElement;
    scrubber = bar.querySelector("#tick-scrubber") as HTMLInputElement;
    speedLabel = bar.querySelector("#speed-label") as HTMLElement;

    if (scrubber) {
      scrubber.min = "0";
      scrubber.max = String(totalTicks - 1);
      scrubber.value = "0";
      scrubber.addEventListener("input", () => {
        setTick(parseInt(scrubber!.value, 10));
      });
    }

    playBtn?.addEventListener("click", toggle);
    stepBackBtn?.addEventListener("click", stepBackward);
    stepFwdBtn?.addEventListener("click", stepForward);

    const speeds = [0.5, 1, 2, 5];
    speedDownBtn?.addEventListener("click", () => {
      const idx = speeds.indexOf(speed);
      if (idx > 0) setSpeed(speeds[idx - 1]);
    });
    speedUpBtn?.addEventListener("click", () => {
      const idx = speeds.indexOf(speed);
      if (idx < speeds.length - 1) setSpeed(speeds[idx + 1]);
    });

    emitTick();
  }

  return {
    get currentTick() { return currentTick; },
    get totalTicks() { return totalTicks; },
    get playing() { return playing; },
    get speed() { return speed; },
    play,
    pause,
    toggle,
    stepForward,
    stepBackward,
    setTick,
    setSpeed,
    update,
    bindUI,
  };
}
