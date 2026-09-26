import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EVENT_TYPES, PHASES, WORKERS, parseEvent, parseEventJson } from "./events";
import { minishopRun } from "./fixtures/minishop";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");

/** The `| \`type\` |` rows of the event table in 02 §9. */
function docEventTypes(): string[] {
  const doc = read("docs/02_ARCHITECTURE.md");
  const section = doc.slice(doc.indexOf("## 9. Event stream"), doc.indexOf("## 10."));
  return [...section.matchAll(/^\| `([a-z._]+)` \|/gm)].map((m) => m[1]!);
}

/** The strings of a `Name = Literal[...]` in src/rook/core/events.py. */
function pythonLiteral(name: string): string[] {
  const src = read("src/rook/core/events.py");
  const match = new RegExp(`^${name} = Literal\\[([\\s\\S]*?)\\]`, "m").exec(src);
  if (match === null) throw new Error(`${name} not found`);
  return [...match[1]!.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
}

describe("event contract", () => {
  it("has exactly the event types of 02 §9", () => {
    expect([...EVENT_TYPES].sort()).toEqual(docEventTypes().sort());
  });

  it("matches the Python models (types, phases, workers)", () => {
    expect([...EVENT_TYPES].sort()).toEqual(pythonLiteral("EventType").sort());
    expect([...PHASES]).toEqual(pythonLiteral("Phase"));
    expect([...WORKERS]).toEqual(pythonLiteral("Worker"));
  });
});

describe("parseEvent", () => {
  const good = { v: 1, seq: 3, ts: "2026-09-26T08:10:00.123Z", run_id: "r_1", type: "log", data: { level: "info", text: "hi" } };

  it("accepts every event of the recorded log", () => {
    expect(minishopRun).toHaveLength(369);
    expect(minishopRun.map((e) => e.seq)).toEqual(minishopRun.map((_, i) => i + 1));
  });

  it("accepts a v1 envelope", () => {
    expect(parseEvent(good)).toEqual(good);
    expect(parseEventJson(JSON.stringify(good))).toEqual(good);
  });

  it.each([
    ["another version", { ...good, v: 2 }],
    ["a zero seq", { ...good, seq: 0 }],
    ["a fractional seq", { ...good, seq: 1.5 }],
    ["a string seq", { ...good, seq: "3" }],
    ["an unknown type", { ...good, type: "agent.exploded" }],
    ["no run id", { ...good, run_id: undefined }],
    ["array data", { ...good, data: [] }],
    ["not an object", [good]],
  ])("rejects %s", (_, value) => {
    expect(parseEvent(value)).toBeNull();
  });

  it("returns null on invalid JSON", () => {
    expect(parseEventJson("{nope")).toBeNull();
  });
});
