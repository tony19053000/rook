// ROOK-038 browser check: load the web app in headless Chrome and fail on any console error, uncaught
// exception, CSP violation or failed request. Plain Node 22 (built-in WebSocket + the Chrome DevTools
// Protocol), no extra deps.
//
//   node e2e/console.mjs https://rook-weld-six.vercel.app          # the pages only (no run, no quota)
//   node e2e/console.mjs https://rook-weld-six.vercel.app --run    # also a guest demo run in the browser
//
// With --run it starts a demo run from the page (same-origin fetch, so the browser gets the first-party
// `rook_guest` cookie), opens /runs/<id> and waits until the run's summary is rendered, i.e. the event stream
// went through the same-origin proxy under the production CSP. Guest confirms answer themselves after their
// countdown; a menu ("What next?") is answered by clicking "report" (or its first option). A guest run uses one
// run of the day's demo quota.
//
// Env: CHROME (default: google-chrome / chromium on PATH), ROOK_CONSOLE_TIMEOUT_S (default 240, for --run).

import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PAGES = ["/", "/runs", "/counterexamples", "/rules", "/repositories", "/login"];
const DEMO = { repo: { kind: "demo", ref: "rook-demo/minishop" }, request: "find and fix a bug", options: { auto: false } };

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseArgs(argv) {
  const base = argv.find((a) => !a.startsWith("--"));
  if (!base || !/^https?:\/\/[^/\s]+\/?$/.test(base)) {
    console.error("usage: node e2e/console.mjs <web origin> [--run]");
    process.exit(2);
  }
  return { base: base.replace(/\/$/, ""), run: argv.includes("--run") };
}

async function launchChrome() {
  const dir = mkdtempSync(join(tmpdir(), "rook-chrome-"));
  const bin = process.env.CHROME || "google-chrome";
  const chrome = spawn(bin, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${dir}`, "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", "about:blank"], { stdio: "ignore" });
  const exited = new Promise((resolve) => chrome.once("exit", resolve));
  const cleanup = async () => {
    chrome.kill("SIGTERM"); // lets Chrome stop its helper processes, which still write to the profile
    await Promise.race([exited, sleep(5000)]);
    chrome.kill("SIGKILL");
    await sleep(300);
    try {
      rmSync(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    } catch {
      console.warn(`(could not remove the temp Chrome profile ${dir})`);
    }
  };
  for (let i = 0; i < 100; i++) {
    try {
      const [port] = readFileSync(join(dir, "DevToolsActivePort"), "utf8").split("\n");
      if (port) return { port: Number(port), cleanup };
    } catch {
      // not written yet
    }
    await sleep(100);
  }
  await cleanup();
  throw new Error(`Chrome did not start (${bin}); set CHROME to its path`);
}

async function openPage(port) {
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  let nextId = 0;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.id !== undefined && pending.has(data.id)) {
      const { resolve, reject } = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) reject(new Error(data.error.message));
      else resolve(data.result);
    } else if (data.method) {
      for (const listener of listeners) listener(data.method, data.params);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  return { send, on: (fn) => listeners.push(fn), close: () => ws.close() };
}

/** Collects every problem the page reports. */
function watch(page, problems) {
  page.on((method, params) => {
    if (method === "Runtime.consoleAPICalled" && (params.type === "error" || params.type === "assert")) {
      problems.push(`console.${params.type}: ${params.args.map((a) => a.value ?? a.description ?? "").join(" ")}`);
    } else if (method === "Runtime.exceptionThrown") {
      const d = params.exceptionDetails;
      problems.push(`uncaught: ${d.exception?.description ?? d.text}`);
    } else if (method === "Log.entryAdded" && params.entry.level === "error") {
      problems.push(`log (${params.entry.source}): ${params.entry.text}${params.entry.url ? ` ${params.entry.url}` : ""}`);
    } else if (method === "Network.loadingFailed" && !params.canceled) {
      problems.push(`request failed: ${params.errorText} ${params.blockedReason ?? ""}`.trim());
    }
  });
}

async function navigate(page, url) {
  await page.send("Page.navigate", { url });
  for (let i = 0; i < 150; i++) {
    const { result } = await page.send("Runtime.evaluate", { expression: "document.readyState" });
    if (result.value === "complete") break;
    await sleep(100);
  }
  await sleep(1500); // hydration and the first API calls
}

async function evaluate(page, expression) {
  const { result, exceptionDetails } = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function demoRun(page, base, timeoutS) {
  const body = JSON.stringify(DEMO);
  const created = await evaluate(page, `fetch("/api/v1/runs", {method: "POST", headers: {"content-type": "application/json"},
    body: ${JSON.stringify(body)}}).then(async (r) => ({status: r.status, body: await r.text()}))`);
  if (created.status !== 200) throw new Error(`POST /api/v1/runs: HTTP ${created.status} ${created.body.slice(0, 200)}`);
  const runId = JSON.parse(created.body).run_id;
  console.log(`run ${runId} started; following it at /runs/${runId}`);
  await navigate(page, `${base}/runs/${runId}`);
  const deadline = Date.now() + timeoutS * 1000;
  let seen = 0;
  while (Date.now() < deadline) {
    const state = await evaluate(page, `({summary: document.querySelector("[data-run-summary]")?.getAttribute("data-run-summary") ?? null,
      items: document.querySelectorAll("[data-item]").length})`);
    if (state.items !== seen) {
      seen = state.items;
      console.log(`  ${Math.round((timeoutS * 1000 - (deadline - Date.now())) / 1000)}s: ${seen} transcript items`);
    }
    if (state.summary !== null) return state.summary;
    // A menu ("What next?") waits for a person; answer it like one, preferring "report".
    const clicked = await evaluate(page, `(() => {
      const buttons = [...document.querySelectorAll("[role=group][data-question] button:not([disabled])")];
      const button = buttons.find((b) => /report/i.test(b.textContent)) ?? buttons[0];
      if (!button) return null;
      button.click();
      return button.textContent;
    })()`);
    if (clicked) console.log(`  answered a menu: ${clicked}`);
    await sleep(1000);
  }
  throw new Error(`the run did not finish in ${timeoutS}s (${seen} transcript items rendered)`);
}

async function main() {
  const { base, run } = parseArgs(process.argv.slice(2));
  const chrome = await launchChrome();
  const problems = [];
  try {
    const page = await openPage(chrome.port);
    watch(page, problems);
    await Promise.all(["Runtime.enable", "Log.enable", "Network.enable", "Page.enable"].map((m) => page.send(m)));
    for (const path of PAGES) {
      const before = problems.length;
      await navigate(page, base + path);
      const html = await evaluate(page, "document.documentElement.outerHTML.length");
      console.log(`${path}: ${html} bytes of DOM, ${problems.length - before} problem(s)`);
    }
    if (run) {
      const summary = await demoRun(page, base, Number(process.env.ROOK_CONSOLE_TIMEOUT_S || 240));
      console.log(`run finished: ${summary}`);
    }
    page.close();
  } finally {
    await chrome.cleanup();
  }
  if (problems.length > 0) {
    console.log(`FAIL ${problems.length} problem(s):`);
    for (const p of problems) console.log(`  - ${p}`);
    process.exit(1);
  }
  console.log("OK no console errors");
}

main().catch((err) => {
  console.error(`FAIL ${err.message}`);
  process.exit(1);
});
