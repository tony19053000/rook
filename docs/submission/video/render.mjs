// Render rook-film.html to MP4: seek the GSAP timeline frame by frame in headless Chrome, pipe JPEGs to ffmpeg.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const [,, html, out, fpsArg, fromArg, toArg] = process.argv;
const FPS = Number(fpsArg || 30), FROM = Number(fromArg || 0);
const chrome = spawn("google-chrome", ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${mkdtempSync(join(tmpdir(), "rf-"))}`,
  "--no-first-run", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=1920,1080", "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const wsUrl = await new Promise(res => { let b = ""; chrome.stderr.on("data", d => { b += d; const m = b.match(/ws:\/\/\S+/); if (m) res(m[0]); }); });
const port = new URL(wsUrl).port;
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pending = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async expr => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: `file://${html}?render=1${process.env.NOCAP ? "&captions=0" : ""}` });
for (let i = 0; i < 100 && !(await evalJs("window.READY === true && !!window.seek")); i++) await new Promise(r => setTimeout(r, 200));
const TO = Number(toArg || await evalJs("window.DURATION"));
const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
  "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
const total = Math.round((TO - FROM) * FPS);
for (let f = 0; f < total; f++) {
  await evalJs(`seek(${(FROM + f / FPS).toFixed(4)})`);
  const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 92 });
  if (!ff.stdin.write(Buffer.from(shot.result.data, "base64"))) await new Promise(r => ff.stdin.once("drain", r));
  if (f % 150 === 0) console.log(`frame ${f}/${total}`);
}
ff.stdin.end(); await new Promise(r => ff.on("close", r)); chrome.kill(); console.log("done", out);
