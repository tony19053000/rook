// The agent sprite system (04 §1.3, CONTRACT): shape masks, eyes and motion on a 12 x 10 pixel grid.
// A port of the mockup JS and src/rook/cli/tui/widgets/characters.py + sprite.py. Everything here is a pure
// function of (shape, colors, frame, seed, reduced motion); drawing it on a canvas is AgentSprite's job.

export const WIDTH = 12;
export const HEIGHT = 10;

export type Shape = "circle" | "small" | "roundsq" | "tilted" | "triangle" | "cloud" | "blob";

export const FPS = 12;
export const BOUNCE_FRAMES = 9; // ~0.75 s at 12 fps
export const BLINK_PERIOD = 70;
export const BLINK_FRAMES = 4;
export const GLANCE_FRAMES = 22; // ~1.8 s per glance step
export const GLANCE_CYCLE = [0, 0, 1, 1, 0, 0, -1, -1] as const;
/** The web bounce: the sprite moves up 3px (04 §1.3). */
export const BOUNCE_PX = 3;

function rot(dx: number, dy: number, deg: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  return [dx * Math.cos(a) - dy * Math.sin(a), dx * Math.sin(a) + dy * Math.cos(a)];
}

const CLOUD: readonly (readonly [number, number, number])[] = [
  [3.4, 5.6, 3.1],
  [7.6, 5.6, 3.1],
  [5.5, 3.4, 3.1],
  [5.5, 6.4, 3.2],
];

export const SHAPES: Record<Shape, (x: number, y: number) => boolean> = {
  circle: (x, y) => (x - 5.5) ** 2 + (y - 4.8) ** 2 <= 4.9 ** 2,
  small: (x, y) => (x - 5.5) ** 2 + (y - 6) ** 2 <= 3.6 ** 2,
  roundsq: (x, y) => {
    const dx = Math.abs(x - 5.5);
    const dy = Math.abs(y - 4.8);
    return dx <= 5 && dy <= 4.6 && dx + dy <= 8.2;
  },
  tilted: (x, y) => {
    const [px, py] = rot(x - 5.5, y - 4.8, -14);
    const dx = Math.abs(px);
    const dy = Math.abs(py);
    return dx <= 4.4 && dy <= 4.1 && dx + dy <= 7.4;
  },
  triangle: (x, y) => {
    const dx = Math.abs(x - 5.5);
    return y >= 0 && dx <= (y + 0.6) * 0.62 && !(y >= 9 && dx > 4.6);
  },
  cloud: (x, y) => CLOUD.some(([cx, cy, r]) => (x - cx) ** 2 + (y - cy) ** 2 <= r * r),
  blob: (x, y) => ((x - 5.5) / 5.6) ** 2 + ((y - 5.2) / 4.3) ** 2 <= 1,
};

export const EYE_ROW: Record<Shape, number> = { circle: 3, small: 5, roundsq: 3, tilted: 3, triangle: 6, cloud: 4, blob: 4 };

export interface Look {
  shape: Shape;
  color: string;
  eye: string;
}

/** A pixel grid: rows of CSS colors, null = transparent. */
export type Grid = (string | null)[][];

/** The 12 x 10 grid. Eyes are 2 px tall at x = 4+look and 7+look; blinking keeps only the bottom pixel. */
export function pixels({ shape, color, eye }: Look, look = 0, blink = false): Grid {
  const inside = SHAPES[shape];
  const eyeRow = EYE_ROW[shape];
  const grid: Grid = [];
  for (let y = 0; y < HEIGHT; y++) {
    const row: (string | null)[] = [];
    for (let x = 0; x < WIDTH; x++) {
      const isEyeCol = x === 4 + look || x === 7 + look;
      const isEyeRow = blink ? y === eyeRow + 1 : y === eyeRow || y === eyeRow + 1;
      row.push(!inside(x, y) ? null : isEyeCol && isEyeRow ? eye : color);
    }
    grid.push(row);
  }
  return grid;
}

export interface Pose {
  up: boolean;
  blink: boolean;
  look: number;
}

export const REST: Pose = Object.freeze({ up: false, blink: false, look: 0 });

/** The pose at a frame. With reduced motion it is always REST: no bounce, blink or glance. */
export function poseAt(frame: number, seed: number, reduced: boolean): Pose {
  if (reduced) return REST;
  const phase = frame + seed;
  return {
    up: Math.floor(phase / BOUNCE_FRAMES) % 2 === 0,
    blink: phase % BLINK_PERIOD < BLINK_FRAMES,
    look: GLANCE_CYCLE[Math.floor(phase / GLANCE_FRAMES) % GLANCE_CYCLE.length]!,
  };
}

/** A random phase so two agents on screen never move in sync. */
export function newSeed(): number {
  return Math.floor(Math.random() * BLINK_PERIOD * BOUNCE_FRAMES);
}

export type ShimmerLevel = "peak" | "near" | "base";

/**
 * The highlight wave over the verb text: one level per character. The web colors are the mockup's
 * (peak = agent color, bold; near = agent color; base = muted), so it reads on both themes.
 */
export function shimmerLevels(length: number, frame: number): ShimmerLevel[] {
  const pos = ((frame * 0.5) % (length + 10)) - 5;
  return Array.from({ length }, (_, i) => {
    const d = Math.abs(i - pos);
    return d < 1.5 ? "peak" : d < 3.2 ? "near" : "base";
  });
}

/** The subset of CanvasRenderingContext2D the sprite needs (so it can be tested with a fake). */
export interface PixelContext {
  clearRect(x: number, y: number, w: number, h: number): void;
  fillRect(x: number, y: number, w: number, h: number): void;
  fillStyle: string | CanvasGradient | CanvasPattern;
}

/** Paint a grid at `scale` device pixels per sprite pixel. */
export function drawGrid(ctx: PixelContext, grid: Grid, scale: number): void {
  ctx.clearRect(0, 0, WIDTH * scale, HEIGHT * scale);
  grid.forEach((row, y) =>
    row.forEach((color, x) => {
      if (color === null) return;
      ctx.fillStyle = color;
      ctx.fillRect(x * scale, y * scale, scale, scale);
    }),
  );
}
