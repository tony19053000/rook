// ROOK-057: the final-verification audit. Drives system Chrome over plain CDP (like e2e/capture-run.mjs), no extra deps.
//
//   node e2e/audit.mjs [base url, default $AUDIT_URL or http://localhost:3100] [--out DIR] [--skip-external] [--headers] [--allow-api-down]
//
// Checks, per route at 360/768/1440/1920 px: status, no horizontal scroll, no broken images, no console errors,
// a screenshot (--allow-api-down: ignore failed /api/v1 calls when no Roook server sits behind the web app); then link check, axe-core (serious/critical), a visible-text scan, and with --headers the security
// headers plus /robots.txt and /sitemap.xml. Exits 1 on any failure. Env: CHROME (default google-chrome).

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const AXE_SOURCE = readFileSync(createRequire(join(WEB, "package.json")).resolve("axe-core/axe.min.js"), "utf8");

const ROUTES = [
  "/", "/docs", "/docs/getting-started", "/docs/install", "/docs/rules", "/docs/counterexamples", "/docs/github-action",
  "/docs/data", "/security", "/pricing", "/roadmap", "/about", "/contact", "/privacy", "/terms", "/login", "/app",
  "/audit-no-such-page",
];
const NOT_FOUND = "/audit-no-such-page";
const WIDTHS = [360, 768, 1440, 1920];
const SCAN_WIDTH = 1440;

// Text rules (the look of lib/copyRules.ts, standalone).
const TEXT_RULES = [
  { name: "[placeholder]", pattern: /\[\s*(?:\.\.\.|…)\s*\]|\[(?:[A-Z][^\]\n]*|[^\]\n]*\b(?:email|name|jurisdiction|date|address|company|legal|tbd|todo|placeholder|insert)\b[^\]\n]*)\]/ },
  { name: "testimonial", pattern: /\btestimonials?\b/i },
  { name: "trusted by", pattern: /\btrusted by\b/i },
  { name: "the word demo", pattern: /\bdemos?\b(?!\.local\b)/i },
  { name: "hackathon (only allowed on /about)", pattern: /\bhackathons?\b/i, exceptPath: "/about" },
  { name: "secret: BOB_API_KEY value", pattern: /BOB_API_KEY\s*[=:]\s*["']?(?!<|\$|your|xxx|\.\.\.|\*|…|\s)[A-Za-z0-9_-]{12,}/ },
  { name: "secret: ghp_ token", pattern: /\bghp_[A-Za-z0-9]{10,}/ },
  { name: "secret: private key block", pattern: /-----BEGIN/ },
  { name: "secret: JWT-like", pattern: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/ },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const opts = { base: process.env.AUDIT_URL || "http://localhost:3100", out: "", skipExternal: false, headers: false, apiDown: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--skip-external") opts.skipExternal = true;
    else if (a === "--headers") opts.headers = true;
    else if (a === "--allow-api-down") opts.apiDown = true;
    else if (a === "--out") opts.out = argv[++i];
    else if (/^https?:\/\//.test(a)) opts.base = a;
    else {
      console.error("usage: node e2e/audit.mjs [base url] [--out DIR] [--skip-external] [--headers] [--allow-api-down]");
      process.exit(2);
    }
  }
  opts.base = opts.base.replace(/\/$/, "");
  opts.out = resolve(opts.out || join(tmpdir(), `rook-audit-${Date.now()}`));
  return opts;
}

async function launchChrome() {
  const dir = mkdtempSync(join(tmpdir(), "rook-audit-chrome-"));
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
  const listeners = [];
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.id === undefined) {
      for (const l of listeners) l(data.method, data.params);
      return;
    }
    const p = pending.get(data.id);
    if (!p) return;
    pending.delete(data.id);
    if (data.error) p.reject(new Error(data.error.message));
    else p.r(data.result);
  };
  const send = (method, params = {}) =>
    new Promise((r, reject) => {
      const id = ++nextId;
      pending.set(id, { r, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  return { send, on: (fn) => listeners.push(fn), close: () => ws.close() };
}

async function evaluate(page, expression) {
  const { result, exceptionDetails } = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

/** Navigate and wait for load plus a settle time; returns the main document status and console errors. */
function makeVisitor(page) {
  let current = null;
  page.on((method, p) => current?.(method, p));
  return async (url) => {
    const state = { status: 0, errors: [] };
    let loaded;
    const loadedP = new Promise((r) => (loaded = r));
    current = (method, p) => {
      if (method === "Network.responseReceived" && p.type === "Document" && !state.status) state.status = p.response.status;
      else if (method === "Runtime.exceptionThrown") state.errors.push(p.exceptionDetails.exception?.description ?? p.exceptionDetails.text);
      else if (method === "Runtime.consoleAPICalled" && p.type === "error") state.errors.push(p.args.map((a) => a.value ?? a.description ?? "").join(" "));
      else if (method === "Log.entryAdded" && p.entry.level === "error") state.errors.push(`${p.entry.text} ${p.entry.url ?? ""}`.trim());
      else if (method === "Page.loadEventFired") loaded();
    };
    await page.send("Page.navigate", { url });
    await Promise.race([loadedP, sleep(30000)]);
    await sleep(700);
    await evaluate(page, `(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo({ top: y, behavior: "instant" }); await new Promise(r => setTimeout(r, 150)); } window.scrollTo({ top: 0, behavior: "instant" }); })()`);
    await sleep(500);
    current = null;
    return state;
  };
}

const PAGE_FACTS = `(async () => {
  // Force lazy images to load (a clipped one may never enter the viewport), then give them up to 8 s to finish.
  const visible = () => [...document.images].filter((im) => im.getClientRects().length > 0);
  for (const im of visible()) im.loading = "eager";
  for (let i = 0; i < 40 && visible().some((im) => !im.complete); i++) await new Promise((r) => setTimeout(r, 200));
  return {
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
  brokenImages: visible().filter((i) => !i.complete || i.naturalWidth === 0).map((i) => (i.currentSrc || i.src) + " (complete=" + i.complete + ", natural=" + i.naturalWidth + ", loading=" + i.loading + ", shown=" + (i.getBoundingClientRect().width > 0) + ")"),
  text: document.body.innerText,
  hrefs: [...document.querySelectorAll("a[href]")].map((a) => ({ raw: a.getAttribute("href"), abs: a.href })),
  ids: [...document.querySelectorAll("[id]")].map((e) => e.id),
  };
})()`;

const fails = { render: [], links: [], axe: [], text: [], headers: [] };
const fail = (check, where, msg) => fails[check].push({ where, msg });

async function fetchRetry(url, init, tries = 3) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      return await fetch(url, { redirect: "follow", signal: globalThis.AbortSignal.timeout(20000), ...init });
    } catch (err) {
      last = err;
      await sleep(800 * (i + 1));
    }
  }
  throw last;
}

async function checkLink(url, external) {
  try {
    let res = await fetchRetry(url, { method: "HEAD", headers: { "user-agent": "rook-audit/1" } });
    // Some hosts reject HEAD or block bots on it; confirm with GET before failing.
    if (res.status >= 400) res = await fetchRetry(url, { method: "GET", headers: { "user-agent": "rook-audit/1" } });
    return res.status < 400 ? null : `HTTP ${res.status}`;
  } catch (err) {
    return `${external ? "unreachable" : "error"}: ${err.cause?.code ?? err.message}`;
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  mkdirSync(opts.out, { recursive: true });
  console.log(`Roook audit of ${opts.base}  (screenshots: ${opts.out})`);
  const chrome = await launchChrome();
  const pageData = new Map(); // path -> { hrefs, ids }
  let axeSeen = new Set();
  try {
    const page = await openPage(chrome.port);
    await page.send("Page.enable");
    await page.send("Runtime.enable");
    await page.send("Network.enable");
    await page.send("Log.enable");
    const visit = makeVisitor(page);

    for (const route of ROUTES) {
      for (const width of WIDTHS) {
        const where = `${route} @${width}`;
        await page.send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 640 });
        let state;
        try {
          state = await visit(`${opts.base}${route}`);
        } catch (err) {
          fail("render", where, `navigation failed: ${err.message}`);
          continue;
        }
        const wantStatus = route === NOT_FOUND ? 404 : 200;
        if (state.status !== wantStatus) fail("render", where, `status ${state.status}, expected ${wantStatus}`);
        const facts = await evaluate(page, PAGE_FACTS);
        if (facts.scrollWidth > facts.clientWidth) fail("render", where, `horizontal scroll (${facts.scrollWidth} > ${facts.clientWidth})`);
        for (const src of facts.brokenImages) fail("render", where, `broken image ${src}`);
        const ignorable = (e) => (route === NOT_FOUND && e.includes(route)) || (opts.apiDown && e.includes("/api/v1/"));
        for (const e of new Set(state.errors.filter((e) => !ignorable(e)))) fail("render", where, `console error: ${e.slice(0, 200)}`);
        const shot = await page.send("Page.captureScreenshot", { format: "png" });
        writeFileSync(join(opts.out, `${route === "/" ? "home" : route.slice(1).replace(/\//g, "_")}-${width}.png`), Buffer.from(shot.data, "base64"));

        // axe at every width; a violation is reported once per route+rule.
        await evaluate(page, AXE_SOURCE);
        const axe = await evaluate(page, `axe.run(document, { resultTypes: ["violations"] }).then((r) => r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ") + " :: " + (n.failureSummary || "").split("\\n").slice(0, 2).join(" ").slice(0, 160)) })))`);
        for (const v of axe) {
          const key = `${route}|${v.id}`;
          if (axeSeen.has(key)) continue;
          axeSeen.add(key);
          fail("axe", where, `${v.impact} ${v.id}: ${v.help}\n        ${v.nodes.join("\n        ")}`);
        }

        if (width === SCAN_WIDTH) {
          pageData.set(route, { hrefs: facts.hrefs, ids: new Set(facts.ids) });
          for (const rule of TEXT_RULES) {
            if (rule.exceptPath === route) continue;
            const m = facts.text.match(rule.pattern);
            if (m) fail("text", route, `${rule.name}: "${m[0].slice(0, 80)}"`);
          }
        }
      }
      console.log(`  rendered ${route}`);
    }
    page.close();
  } finally {
    await chrome.cleanup();
  }

  // Link check.
  const baseOrigin = new URL(opts.base).origin;
  const seen = new Map(); // abs url (no hash) -> { pages: Set }
  const anchors = []; // { from, url, hash }
  for (const [route, { hrefs }] of pageData) {
    for (const { raw, abs } of hrefs) {
      if (!raw || raw.startsWith("javascript:") || raw.startsWith("tel:")) continue;
      if (raw.startsWith("mailto:")) {
        const addr = decodeURIComponent(raw.slice(7).split("?")[0]);
        if (!/^[^\s@,]+@[^\s@,]+\.[^\s@,]{2,}$/.test(addr) || /example\.(com|org)$|your|placeholder/i.test(addr)) fail("links", route, `bad mailto address "${raw}"`);
        continue;
      }
      let u;
      try {
        u = new URL(abs);
      } catch {
        fail("links", route, `unparseable href "${raw}"`);
        continue;
      }
      if (!/^https?:$/.test(u.protocol)) continue;
      if (route === NOT_FOUND && u.pathname === NOT_FOUND) continue;
      const hash = u.hash.slice(1);
      u.hash = "";
      const key = u.href;
      if (!seen.has(key)) seen.set(key, new Set());
      seen.get(key).add(route);
      if (hash) anchors.push({ from: route, url: key, hash: decodeURIComponent(hash) });
    }
  }
  const targets = [...seen.keys()];
  console.log(`  checking ${targets.length} distinct links`);
  const queue = [...targets];
  await Promise.all(Array.from({ length: 8 }, async () => {
    while (queue.length) {
      const url = queue.pop();
      const external = new URL(url).origin !== baseOrigin;
      if (external && opts.skipExternal) continue;
      const err = await checkLink(url, external);
      if (err) fail("links", [...seen.get(url)].join(", "), `${url} -> ${err}`);
    }
  }));
  // Anchor targets: use the audited page's ids, else fetch the HTML.
  const htmlIds = new Map();
  for (const a of anchors) {
    if (new URL(a.url).origin !== baseOrigin) continue;
    const path = new URL(a.url).pathname.replace(/(.)\/$/, "$1");
    let ids = pageData.get(path)?.ids;
    if (!ids) {
      if (!htmlIds.has(a.url)) {
        try {
          const html = await (await fetchRetry(a.url, {})).text();
          htmlIds.set(a.url, new Set([...html.matchAll(/\b(?:id|name)="([^"]+)"/g)].map((m) => m[1])));
        } catch {
          htmlIds.set(a.url, new Set());
        }
      }
      ids = htmlIds.get(a.url);
    }
    if (a.hash && a.hash !== "top" && !ids.has(a.hash)) fail("links", a.from, `anchor #${a.hash} missing on ${path}`);
  }

  if (opts.headers) await checkHeaders(opts.base);

  // Summary.
  const labels = {
    render: "Render (status, scroll, images, console)",
    links: "Links",
    axe: "axe-core (serious/critical)",
    text: "Visible text scan",
    headers: opts.headers ? "Headers, robots, sitemap" : null,
  };
  let total = 0;
  console.log("\n=== SUMMARY ===");
  for (const [key, label] of Object.entries(labels)) {
    if (!label) continue;
    const list = fails[key];
    total += list.length;
    console.log(`${list.length ? "FAIL" : "PASS"}  ${label}${list.length ? `: ${list.length}` : ""}`);
    for (const f of list) console.log(`   - [${f.where}] ${f.msg}`);
  }
  if (opts.skipExternal) console.log("(external links skipped)");
  if (!opts.headers) console.log("(headers check not run; pass --headers)");
  process.exit(total ? 1 : 0);
}

async function checkHeaders(base) {
  const res = await fetchRetry(`${base}/`, { method: "GET" });
  const h = res.headers;
  const csp = h.get("content-security-policy") ?? "";
  if (!/'nonce-[^']+'/.test(csp)) fail("headers", "/", `content-security-policy missing or without a nonce (${csp ? csp.slice(0, 80) : "absent"})`);
  if (!h.get("strict-transport-security")) fail("headers", "/", "strict-transport-security missing");
  if ((h.get("x-content-type-options") ?? "").toLowerCase() !== "nosniff") fail("headers", "/", "x-content-type-options: nosniff missing");
  if (!h.get("x-frame-options") && !/frame-ancestors/.test(csp)) fail("headers", "/", "neither x-frame-options nor CSP frame-ancestors");
  if (!h.get("referrer-policy")) fail("headers", "/", "referrer-policy missing");
  if (!base.startsWith("https://")) fail("headers", "/", "not served over https");
  for (const p of ["/robots.txt", "/sitemap.xml"]) {
    const r = await fetchRetry(`${base}${p}`, { method: "GET" });
    if (r.status !== 200) fail("headers", p, `HTTP ${r.status}, expected 200`);
  }
}

main().catch((err) => {
  console.error(`FAIL ${err.stack ?? err.message}`);
  process.exit(1);
});
