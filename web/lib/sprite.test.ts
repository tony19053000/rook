import { describe, expect, it } from "vitest";
import { AGENTS, agentInfo, MASCOT, workerName } from "./agents";
import { AGENT_IDS } from "./events";
import {
  BLINK_PERIOD,
  drawGrid,
  EYE_ROW,
  HEIGHT,
  pixels,
  poseAt,
  REST,
  SHAPES,
  shimmerLevels,
  WIDTH,
  type PixelContext,
  type Shape,
} from "./sprite";

// Generated from src/rook/cli/tui/widgets/characters.py, so the web and terminal sprites stay the same.
const GOLDEN: Record<Shape, string[]> = {
  circle: [
    ".....##.....",
    "...######...",
    "..########..",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    "..########..",
    "..########..",
    "...######...",
  ],
  small: [
    "............",
    "............",
    "............",
    "....####....",
    "...######...",
    "...######...",
    "..########..",
    "...######...",
    "...######...",
    "....####....",
  ],
  roundsq: [
    "............",
    "..########..",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    "..########..",
  ],
  tilted: [
    "............",
    "..######....",
    "..########..",
    "..#########.",
    "..#########.",
    ".#########..",
    ".#########..",
    ".#########..",
    "..########..",
    "......###...",
  ],
  triangle: [
    "............",
    ".....##.....",
    "....####....",
    "....####....",
    "...######...",
    "...######...",
    "..########..",
    ".##########.",
    ".##########.",
    ".##########.",
  ],
  cloud: [
    "............",
    "....####....",
    "...######...",
    "..########..",
    ".##########.",
    ".##########.",
    ".##########.",
    ".##########.",
    "..########..",
    "....####....",
  ],
  blob: [
    "............",
    ".....##.....",
    "..########..",
    ".##########.",
    ".##########.",
    "############",
    "############",
    ".##########.",
    "..########..",
    "...######...",
  ],
};

function mask(shape: Shape): string[] {
  return Array.from({ length: HEIGHT }, (_, y) =>
    Array.from({ length: WIDTH }, (_, x) => (SHAPES[shape](x, y) ? "#" : ".")).join(""),
  );
}

describe("sprite shapes (04 §1.3)", () => {
  it.each(Object.keys(GOLDEN) as Shape[])("%s matches the Python port pixel for pixel", (shape) => {
    expect(mask(shape)).toEqual(GOLDEN[shape]);
  });

  it("puts two 2px eyes at x = 4+look and 7+look on the eye row", () => {
    const look = { shape: "circle" as const, color: "#111111", eye: "#FFFFFF" };
    const er = EYE_ROW.circle;
    const grid = pixels(look, 1);
    for (const x of [5, 8]) {
      expect(grid[er]![x]).toBe("#FFFFFF");
      expect(grid[er + 1]![x]).toBe("#FFFFFF");
    }
    expect(grid[er]![4]).toBe("#111111");
    expect(grid[0]![0]).toBeNull();
  });

  it("blinking keeps only the bottom eye pixel", () => {
    const grid = pixels({ shape: "blob", color: "#111111", eye: "#FFFFFF" }, 0, true);
    const er = EYE_ROW.blob;
    expect(grid[er]![4]).toBe("#111111");
    expect(grid[er + 1]![4]).toBe("#FFFFFF");
  });

  it("drawGrid fills one rect per opaque pixel at the given scale", () => {
    const rects: [string, number, number, number, number][] = [];
    const ctx: PixelContext = {
      fillStyle: "",
      clearRect: () => {},
      fillRect(x, y, w, h) {
        rects.push([String(this.fillStyle), x, y, w, h]);
      },
    };
    const grid = pixels(AGENTS.scout);
    drawGrid(ctx, grid, 3);
    const opaque = grid.flat().filter((c) => c !== null).length;
    expect(rects).toHaveLength(opaque);
    expect(rects[0]).toEqual(["#10B99A", 6, 3, 3, 3]);
  });
});

describe("motion", () => {
  it("reduced motion always gives the rest pose", () => {
    for (let frame = 0; frame < 3 * BLINK_PERIOD; frame++) expect(poseAt(frame, 123, true)).toEqual(REST);
  });

  it("bounces, blinks and glances without reduced motion", () => {
    const poses = Array.from({ length: 200 }, (_, f) => poseAt(f, 0, false));
    expect(new Set(poses.map((p) => p.up))).toEqual(new Set([true, false]));
    expect(poses.some((p) => p.blink)).toBe(true);
    expect(new Set(poses.map((p) => p.look))).toEqual(new Set([-1, 0, 1]));
  });

  it("different seeds are out of sync", () => {
    const a = Array.from({ length: 100 }, (_, f) => JSON.stringify(poseAt(f, 0, false)));
    const b = Array.from({ length: 100 }, (_, f) => JSON.stringify(poseAt(f, 37, false)));
    expect(a).not.toEqual(b);
  });

  it("the shimmer wave moves across the text", () => {
    expect(shimmerLevels(8, 0)).toHaveLength(8);
    expect(shimmerLevels(8, 10)).not.toEqual(shimmerLevels(8, 14));
    expect(shimmerLevels(8, 10)).toContain("peak");
  });
});

describe("agent characters (04 §1.3 table)", () => {
  it("every agent id has a shape, color and verb", () => {
    for (const id of AGENT_IDS) {
      const info = AGENTS[id];
      expect(Object.keys(SHAPES)).toContain(info.shape);
      expect(info.color).toMatch(/^#[0-9A-F]{6}$/);
      expect(info.verb).not.toBe("");
    }
    expect(AGENTS.rule_critic).toMatchObject({ shape: "triangle", color: "#FF1493", name: "Rule Critic" });
    expect(AGENTS.guide).toMatchObject({ shape: "small", color: "#8E99A6" });
    expect(MASCOT).toMatchObject({ shape: "cloud", color: "#E0563F" });
  });

  it("an unknown id gets a readable, cleaned neutral character", () => {
    expect(agentInfo("new_agent\x1b[2J")).toMatchObject({ name: "New Agent[2J", shape: "circle", verb: "Working" });
    expect(workerName("fuzzer")).toBe("Fuzzer");
    expect(workerName("testrunner")).toBe("Test Runner");
  });
});
