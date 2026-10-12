// ROOK-054: capture the home page's product screenshots from the RUNNING web app (06 §4 "Recorded vs live").
// Starts a guest example run in headless Chrome, waits until the fix is verified, then saves two WebP files
// of the finished run page: the counterexample and fix cards at a desktop width, the verify card at a phone
// width. Plain Node 22 and the Chrome DevTools Protocol (the helpers of e2e/console.mjs), no extra deps.
//
//   node e2e/capture-run.mjs http://localhost:3100 [out dir, default public/screenshots]
//
// The origin must serve the web app with /api/v1 proxied to a Rook server in Bob *replay* mode, so the run's
// Bob answers are the committed recordings (0 Bobcoins) and the engine runs live against the minishop app:
// e.g. `ROOK_E2E_KEEP=1 npm run test:e2e` keeps such a pair up, or `rook serve` with ROOK_BOB_MODE=replay
// plus `ROOK_API_PROXY_TARGET=<server> next build && next start -p 3100`. Never point it at a live-mode server.
// A guest run uses one run of the day's guest quota.
//
// Env: CHROME (default: google-chrome), ROOK_CAPTURE_TIMEOUT_S (default 300).

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** The files the home page shows (content/home.ts `runScreenshot` points at them). */
export const SHOTS = [
  { file: "run-desktop.webp", width: 1440, height: 1000, scale: 1.5, card: "counterexample" },
  { file: "run-mobile.webp", width: 390, height: 844, scale: 2, card: "verify" },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const [base, out] = argv;
  if (!base || !/^https?:\/\/[^/\s]+\/?$/.test(base)) {
    console.error("usage: node e2e/capture-run.mjs <web origin> [out dir]");
    process.exit(2);
  }
  return { base: base.replace(/\/$/, ""), out: resolve(out ?? join(WEB, "public", "screenshots")) };
}

async function launchChrome() {
  const dir = mkdtempSync(join(tmpdir(), "rook-chrome-"));
  const bin = process.env.CHROME || "google-chrome";
  const chrome = spawn(bin, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${dir}`, "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
  const exited = new Promise((r) => chrome.once("exit", r));
  const cleanup = async () => {
    chrome.kill("SIGTERM");
    await Promise.race([exited, sleep(5000)]);
    chrome.kill("SIGKILL");
    await sleep(300);
    rmSync(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
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
  const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r, reject) => {
    ws.onopen = r;
    ws.onerror = reject;
  });
  let nextId = 0;
  const pending = new Map();
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.id === undefined || !pending.has(data.id)) return;
    const { r, reject } = pending.get(data.id);
    pending.delete(data.id);
    if (data.error) reject(new Error(data.error.message));
    else r(data.result);
  };
  const send = (method, params = {}) =>
    new Promise((r, reject) => {
      const id = ++nextId;
      pending.set(id, { r, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  return { send, close: () => ws.close() };
}

async function evaluate(page, expression) {
  const { result, exceptionDetails } = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function until(page, expression, timeoutS, what) {
  const deadline = Date.now() + timeoutS * 1000;
  while (Date.now() < deadline) {
    const value = await evaluate(page, expression);
    if (value) return value;
    await sleep(1000);
  }
  throw new Error(`timed out after ${timeoutS}s waiting for ${what}`);
}

async function main() {
  const { base, out } = parseArgs(process.argv.slice(2));
  const timeoutS = Number(process.env.ROOK_CAPTURE_TIMEOUT_S || 300);
  const chrome = await launchChrome();
  try {
    const page = await openPage(chrome.port);
    await page.send("Page.enable");
    // The app's dark theme (it sits on the dark site) and no motion, so no sprite is caught mid-frame.
    await page.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-color-scheme", value: "dark" }, { name: "prefers-reduced-motion", value: "reduce" }],
    });
    await page.send("Page.navigate", { url: `${base}/app` });
    await until(page, `document.readyState === "complete" && !!document.querySelector("[data-try-example]:not([disabled])")`, 60, "the app home");
    const status = await evaluate(page, `fetch("/api/v1/health").then((r) => r.json())`);
    if (status?.bob_mode !== "replay") throw new Error(`the server must be in replay mode, not ${status?.bob_mode}`);
    await evaluate(page, `document.querySelector("[data-try-example]").click()`);
    const url = await until(page, `location.pathname.startsWith("/runs/") && location.href`, 60, "the run page");
    console.log(`run started: ${url}`);
    // Guest confirms answer themselves after their countdown; the run ends done, with the fix verified.
    await until(page, `!!document.querySelector('[data-verified]:not([data-verified="false"])') && !!document.querySelector('[data-run-summary="done"]')`, timeoutS, "a verified fix");
    await sleep(1500);
    mkdirSync(out, { recursive: true });
    for (const shot of SHOTS) {
      await page.send("Emulation.setDeviceMetricsOverride", {
        width: shot.width, height: shot.height, deviceScaleFactor: shot.scale, mobile: shot.width < 640,
      });
      await sleep(800);
      // The transcript scrolls inside its own container: bring the card to the top of it.
      await evaluate(page, `(() => {
        const card = document.querySelector('[data-card="${shot.card}"]');
        let box = card.parentElement;
        while (box && !(box.scrollHeight > box.clientHeight && getComputedStyle(box).overflowY !== "visible")) box = box.parentElement;
        box.scrollTop += card.getBoundingClientRect().top - box.getBoundingClientRect().top - 4;
      })()`);
      await sleep(500);
      const { data } = await page.send("Page.captureScreenshot", { format: "webp", quality: 82 });
      const path = join(out, shot.file);
      writeFileSync(path, Buffer.from(data, "base64"));
      console.log(`saved ${path} (${shot.width}x${shot.height} @${shot.scale}x, ${Math.round(Buffer.from(data, "base64").length / 1024)} KB)`);
    }
    page.close();
  } finally {
    await chrome.cleanup();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    console.error(`FAIL ${err.message}`);
    process.exit(1);
  });
}
