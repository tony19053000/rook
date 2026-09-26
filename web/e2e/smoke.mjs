// ROOK-036 E2E smoke test: the web app's happy path against a real local Rook server in Bob *replay* mode.
//
//   cd web && npm run test:e2e
//
// What it does (plain Node 22, no browser, no extra deps):
//  1. builds a throwaway demo setup in a temp dir: the minishop fixture as the allowlisted demo repo
//     `rook-demo/minishop`, and the committed Bob recordings (tests/fixtures/recordings/*_minishop) as the
//     replay folder (`$HOME/.rook/recordings` of the server process);
//  2. starts the FastAPI server (`uvicorn rook.server.app:app`) with ROOK_BOB_MODE=replay. Its env is built
//     from scratch: no BOB_API_KEY is passed and ROOK_BOB_BIN points at a path that does not exist, so a live
//     `bob run` is impossible (0 Bobcoins);
//  3. builds the web app with ROOK_API_PROXY_TARGET = that server (skip with ROOK_E2E_SKIP_BUILD=1 when .next
//     was already built for the same port) and starts `next start`;
//  4. through the Next origin only (pages + the /api/v1 rewrite): GETs the pages, lists the repos, starts a
//     run on the demo repo, reads its SSE stream (answering questions like a user would) until run.finished,
//     then checks the run is listed by GET /runs with the same status.
// Child processes are killed and the temp dir removed on success, failure or Ctrl-C.
//
// Expected outcome: the run goes PREPARE -> ... -> SAVE on real replayed Bob output and the real engine (it finds
// and saves the refund counterexample), then ends `failed` at DIAGNOSE. The Detective's prompt holds the demo
// app's sandbox logs (ports, timings), which differ from the recording's in-process run, so its recording
// misses; that is a replay limit, not a web bug. The smoke test checks the web path (pages, proxy, SSE,
// answers, recents), so any terminal status is accepted as long as GET /runs agrees with run.finished.
//
// Env: ROOK_E2E_API_PORT (default 8765), ROOK_E2E_PYTHON (default ../.venv/bin/python, i.e. after `uv sync`),
// ROOK_E2E_TIMEOUT_S (default 300), ROOK_E2E_SKIP_BUILD=1, ROOK_E2E_KEEP=1 (after the checks, keep both servers
// up for the manual in-browser check of docs/04_FRONTEND_SPEC.md §3.8; Ctrl-C stops them and cleans up).

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(WEB, "..");
const FIXTURES = join(ROOT, "tests", "fixtures");
const RECORDINGS = ["understand", "rules", "design", "diagnose", "surgeon", "session"].map((p) => `${p}_minishop`);
const DEMO_REF = "rook-demo/minishop";
const DEMO_COMMIT = createHash("sha1").update("rook-e2e-minishop").digest("hex");
const REQUEST = "find and fix a bug";
const TERMINAL = new Set(["done", "failed", "cancelled"]);

const API_PORT = Number(process.env.ROOK_E2E_API_PORT ?? 8765);
const PYTHON = process.env.ROOK_E2E_PYTHON ?? join(ROOT, ".venv", "bin", "python");
const TIMEOUT_MS = Number(process.env.ROOK_E2E_TIMEOUT_S ?? 300) * 1000;

const children = [];
let scratch = "";
let checks = 0;

function log(msg) {
  console.log(`[e2e] ${msg}`);
}

function ok(msg) {
  checks += 1;
  console.log(`[e2e] PASS ${msg}`);
}

function check(condition, msg) {
  if (!condition) throw new Error(`FAIL ${msg}`);
  ok(msg);
}

// --- processes ---

function start(name, cmd, args, opts) {
  // detached: the child leads its own process group, so cleanup also kills what it spawned (e.g. the demo app).
  const child = spawn(cmd, args, { ...opts, detached: true, stdio: ["ignore", "pipe", "pipe"] });
  const tail = [];
  const keep = (chunk) => {
    tail.push(...chunk.toString().split("\n").filter(Boolean));
    tail.splice(0, Math.max(0, tail.length - 40));
  };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  const entry = { name, child, tail, exited: false };
  child.on("exit", () => (entry.exited = true));
  children.push(entry);
  return entry;
}

function run(name, cmd, args, opts) {
  return new Promise((resolvePromise, reject) => {
    const entry = start(name, cmd, args, opts);
    entry.child.on("exit", (code) =>
      code === 0 ? resolvePromise() : reject(new Error(`${name} exited ${code}:\n${entry.tail.join("\n")}`)),
    );
  });
}

function cleanup() {
  for (const { child, exited } of children) {
    if (exited || child.pid === undefined) continue;
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      // already gone
    }
  }
  if (scratch !== "") rmSync(scratch, { recursive: true, force: true });
  scratch = "";
}

process.on("SIGINT", () => {
  cleanup();
  process.exit(130);
});
process.on("SIGTERM", () => {
  cleanup();
  process.exit(143);
});

function freePort() {
  return new Promise((resolvePromise, reject) => {
    const srv = createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolvePromise(port));
    });
  });
}

async function waitFor(url, entry, ms = 60_000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (entry.exited) throw new Error(`${entry.name} exited early:\n${entry.tail.join("\n")}`);
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`${entry.name} did not answer ${url} within ${ms / 1000} s:\n${entry.tail.join("\n")}`);
}

// --- setup ---

function demoSetup() {
  scratch = mkdtempSync(join(tmpdir(), "rook-e2e-"));
  const app = join(scratch, "demo", "minishop");
  mkdirSync(app, { recursive: true });
  // The recordings were made on this exact file set (the Scout's prompt holds a digest of the workspace).
  for (const file of ["app.py", "test_minishop_app.py"]) cpSync(join(FIXTURES, "minishop", file), join(app, file));
  const recordings = join(scratch, "home", ".rook", "recordings");
  mkdirSync(recordings, { recursive: true });
  for (const folder of RECORDINGS) {
    for (const file of readdirSync(join(FIXTURES, "recordings", folder))) {
      cpSync(join(FIXTURES, "recordings", folder, file), join(recordings, file));
    }
  }
  writeFileSync(
    join(scratch, "allowlist.yaml"),
    [
      "entries:",
      `  - repo: ${DEMO_REF}`,
      `    commit: '${DEMO_COMMIT}'`,
      "    app_dir: demo/minishop",
      "    start: ['{python}', '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '{port}']",
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(scratch, "demos.yaml"),
    `repos:\n  - {ref: ${DEMO_REF}, commit: '${DEMO_COMMIT}', name: minishop, language: Python}\n`,
  );
}

function serverEnv(webOrigin) {
  // From scratch on purpose: never the caller's env (it may hold BOB_API_KEY).
  return {
    PATH: "/usr/local/bin:/usr/bin:/bin",
    HOME: join(scratch, "home"),
    LANG: "C.UTF-8",
    ROOK_BOB_MODE: "replay",
    ROOK_BOB_BIN: join(scratch, "no-bob-here"),
    ROOK_DB_PATH: join(scratch, "server.db"),
    ROOK_WORKSPACES: join(scratch, "workspaces"),
    ROOK_DEMO_REPOS: join(scratch, "demos.yaml"),
    ROOK_ALLOWLIST: join(scratch, "allowlist.yaml"),
    ROOK_WEB_ORIGINS: webOrigin,
  };
}

function webEnv(extra) {
  const env = { ...process.env, NEXT_TELEMETRY_DISABLED: "1", ...extra };
  delete env.BOB_API_KEY;
  delete env.NEXT_PUBLIC_API_URL; // the browser must use the same-origin /api/v1 rewrite
  return env;
}

// --- the web origin, like a browser (one cookie jar) ---

function client(origin) {
  let cookie = "";
  return async function call(path, init = {}) {
    const headers = { ...(init.headers ?? {}), ...(cookie ? { cookie } : {}) };
    const res = await fetch(origin + path, { ...init, headers, redirect: "manual" });
    const set = res.headers.getSetCookie().find((c) => c.startsWith("rook_guest="));
    if (set) cookie = set.split(";")[0];
    return res;
  };
}

async function json(res, what) {
  if (!res.ok) throw new Error(`FAIL ${what}: HTTP ${res.status} ${await res.text()}`);
  return res.json();
}

/** Answers a question the way a demo user would (approve the refund rule, apply the fix). */
function answerFor(question) {
  switch (question.kind) {
    case "approve_rules": {
      const rules = question.payload?.rules ?? [];
      const refund = rules.filter((r) => r.accepted && r.check.includes("refund") && r.check.includes("paid"));
      return refund.length > 0 ? refund.map((r) => r.id) : "all";
    }
    case "fix":
    case "pr":
      return "yes";
    case "menu": // a failed agent: end with a report instead of retrying (see the header note)
      return (question.options.find((o) => o.id === "report") ?? question.options[0])?.id;
    default:
      return question.options[0]?.id ?? "yes";
  }
}

async function streamRun(call, runId) {
  const res = await call(`/api/v1/runs/${runId}/events`, { headers: { accept: "text/event-stream" } });
  check(res.ok && (res.headers.get("content-type") ?? "").startsWith("text/event-stream"),
    "GET /api/v1/runs/<id>/events streams text/event-stream through the proxy");
  const decoder = new TextDecoder();
  const types = new Map();
  const reader = res.body.getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("\n");
      if (data === "") continue; // a ping comment
      const event = JSON.parse(data);
      types.set(event.type, (types.get(event.type) ?? 0) + 1);
      if (event.type === "run.phase") log(`phase ${event.data.phase}`);
      if (event.type === "agent.finished" && !event.data.ok) log(`agent ${event.data.agent} failed: ${event.data.summary}`);
      if (event.type === "question.asked") {
        const answer = answerFor(event.data);
        log(`question ${event.data.kind}: "${event.data.text.slice(0, 70)}" -> ${JSON.stringify(answer)}`);
        const reply = await json(
          await call(`/api/v1/runs/${runId}/answers`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ question_id: event.data.question_id, answer }),
          }),
          "POST /answers",
        );
        check(reply.ok === true, `POST /api/v1/runs/<id>/answers accepted the ${event.data.kind} answer`);
      }
      if (event.type === "run.finished") {
        await reader.cancel();
        return { finished: event.data, types };
      }
    }
  }
  throw new Error("FAIL the event stream ended without run.finished");
}

// --- main ---

async function main() {
  if (!existsSync(PYTHON)) throw new Error(`no Python at ${PYTHON}: run \`uv sync\` in the repo root first`);
  demoSetup();
  const webPort = await freePort();
  const web = `http://127.0.0.1:${webPort}`;
  const api = `http://127.0.0.1:${API_PORT}`;

  log(`server (replay mode, 0 coins) on ${api}`);
  const server = start("server", PYTHON, ["-m", "uvicorn", "rook.server.app:app", "--host", "127.0.0.1",
    "--port", String(API_PORT)], { cwd: scratch, env: serverEnv(web) });
  await waitFor(`${api}/api/v1/health`, server);

  if (process.env.ROOK_E2E_SKIP_BUILD === "1") {
    log("skipping next build (ROOK_E2E_SKIP_BUILD=1)");
  } else {
    log(`next build with ROOK_API_PROXY_TARGET=${api}`);
    await run("next build", process.execPath, [join(WEB, "node_modules", "next", "dist", "bin", "next"), "build"],
      { cwd: WEB, env: webEnv({ ROOK_API_PROXY_TARGET: api }) });
  }
  log(`next start on ${web}`);
  const next = start("next start", process.execPath, [join(WEB, "node_modules", "next", "dist", "bin", "next"),
    "start", "-H", "127.0.0.1", "-p", String(webPort)], { cwd: WEB, env: webEnv({ ROOK_API_PROXY_TARGET: api }) });
  await waitFor(`${web}/login`, next);

  const call = client(web);
  for (const page of ["/", "/runs", "/login", "/repositories"]) {
    const res = await call(page);
    check(res.status === 200, `GET ${page} -> 200`);
  }

  const health = await json(await call("/api/v1/health"), "GET /api/v1/health");
  check(typeof health === "object" && health !== null, "GET /api/v1/health through the Next proxy");
  const repos = await json(await call("/api/v1/repos"), "GET /api/v1/repos");
  check(repos.some((r) => r.kind === "demo" && r.ref === DEMO_REF), `GET /api/v1/repos lists the demo ${DEMO_REF}`);

  const created = await json(
    await call("/api/v1/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo: { kind: "demo", ref: DEMO_REF }, request: REQUEST, options: { auto: false } }),
    }),
    "POST /api/v1/runs",
  );
  check(typeof created.run_id === "string" && created.run_id !== "", `POST /api/v1/runs -> ${created.run_id}`);

  const { finished, types } = await streamRun(call, created.run_id);
  check(TERMINAL.has(finished.status), `run.finished with status "${finished.status}": ${finished.summary}`);
  log(`events: ${[...types].map(([t, n]) => `${t}×${n}`).join(", ")}`);
  check(types.has("counterexample.saved"), "the engine found, shrank and saved a counterexample (streamed)");
  const detail = await json(await call(`/api/v1/runs/${created.run_id}`), "GET /api/v1/runs/<id>");
  check(detail.run.coins === 0, "the run spent 0 Bobcoins (replay)");
  check(detail.counterexamples.length > 0, `GET /api/v1/runs/<id> lists ${detail.counterexamples.length} counterexample(s)`);

  const page = await call(`/runs/${created.run_id}`);
  check(page.status === 200, `GET /runs/${created.run_id} -> 200`);
  const runs = await json(await call("/api/v1/runs"), "GET /api/v1/runs");
  const listed = runs.find((r) => r.id === created.run_id);
  check(listed !== undefined, "GET /api/v1/runs lists the new run (the recents)");
  check(listed.status === finished.status, `the listed run has status "${listed.status}" (= run.finished)`);
  return web;
}

const timer = setTimeout(() => {
  console.error(`[e2e] FAIL timed out after ${TIMEOUT_MS / 1000} s`);
  cleanup();
  process.exit(1);
}, TIMEOUT_MS);

try {
  const web = await main();
  log(`OK: ${checks} checks passed`);
  process.exitCode = 0;
  if (process.env.ROOK_E2E_KEEP === "1") {
    clearTimeout(timer);
    log(`servers kept up: open ${web} in a browser (Ctrl-C to stop)`);
    await new Promise(() => setInterval(() => {}, 1 << 30)); // until SIGINT/SIGTERM, whose handlers clean up
  }
} catch (err) {
  console.error(`[e2e] ${err instanceof Error ? err.message : err}`);
  for (const { name, tail } of children) {
    if (tail.length > 0) console.error(`--- last output of ${name} ---\n${tail.slice(-15).join("\n")}`);
  }
  process.exitCode = 1;
} finally {
  clearTimeout(timer);
  cleanup();
}
