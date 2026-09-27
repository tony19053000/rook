# Prompt for the next session: Rook video v2

Paste everything in the code block below into a fresh Claude Code session.

```
You are making the hackathon video for Rook (IBM Bob hackathon) in /home/aayush/Desktop/Counterexample. Deadline: 27 Sep 2026 20:30 IST, so work fast and render early. Keep answers to me short and simple.

WHAT EXISTS (read these first):
- docs/submission/video/rook-film.html: v1 of the motion video (a GSAP timeline on a 1920x1080 stage, 150 s, window.seek(t) for frame rendering, captions from the CAPS list).
- docs/submission/video/render.mjs: renders it to MP4 (headless google-chrome + CDP screenshots piped to ffmpeg). Usage: node render.mjs <abs html path> <out.mp4> 30 [from] [to]; NOCAP=1 for no captions. ~10 min per full render at 30 fps.
- ~/Videos/Rook-film-captions.mp4 and ~/Videos/Rook-film-clean.mp4: the v1 render.
- docs/submission/VIDEO_SCRIPT.md: a detailed shot list, style bible and master prompt (Parts B–D). Use it as the reference for scenes, facts, palette, type and motion.
- docs/submission/SUBMISSION_KIT.md: facts and links.

MY FEEDBACK ON v1 (fix all of this in v2):
1. It was good but not good enough: not detailed enough, not enough animation, not cool enough. It must look like premium motion-graphics editing, not slides.
2. More animation everywhere: continuous camera moves with parallax on 3 depth layers, kinetic typography (per-word/per-character entrances with stagger, blur-to-sharp), particle/shatter transitions, split-flap counters, glitch on "Rule broken", lock-on push-ins on proof moments, springy agent characters with blinking eyes, animated strokes for diagrams, light blooms and grain. Keep the pacing engaging: a new visual beat every ~0.5-1 s, long holds only on proof moments. Not too much text on screen at once.
3. The CLI is the hero. The demo part must be a REAL CLI run, not only an animation. Record a real run of `rook run` on shop-app and put that footage inside the video (in a floating terminal frame, sped up during waits, 1x on key moments, with motion-graphic overlays on top). The web app appears only briefly near the end.
4. Keep Rook's own identity (palette, Newsreader / IBM Plex Sans / IBM Plex Mono, the red rook glyph). No Anthropic/Claude branding.

HOW TO GET THE REAL CLI FOOTAGE:
- Follow VIDEO_SCRIPT.md Part A. The user runs it interactively in a full-screen terminal while ffmpeg records the screen (x11, display :0.0): clean clone of https://github.com/tony19053000/shop-app to ~/demo/shop-app, `source ~/.bob-key.env`, `export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH`, `uv run rook run ~/demo/shop-app --request "find refund and order bugs"`, approve ONLY the refund rule (refunded total <= order total), say yes to fix and PR. About 1–1.5 Bobcoins, 5–12 minutes. Never print BOB_API_KEY. If the run ends "not verified", use it honestly.
- Give the user the exact commands, then wait for ~/Videos/rook-cli-real.mp4. While waiting, build the motion-graphics scenes.
- Note in advance: with --auto Bob once approved a wrong rule on shop-app, so the run must be interactive. A known CLI bug: "vitest: executable file not found" in the local Docker sandbox's project tests. If it shows up, either note it honestly in the video or fix it first (small fix in the sandbox test command for Node: use node_modules/.bin), your call based on time.

FACTS (keep exact): 13 IBM Bob agents as Bob Shell custom modes; only the deterministic engine decides pass/fail; the bug is at src/routes/orders.js:264 (refund checked against order.total instead of order.total - order.refundedTotal); counterexample create_product → place_order → cancel_order → refund_order(100), refunded 200 on a 100 order; replayed 10/10; verify = exact replay, project tests, new regression test, fresh search; branch rook/fix-cx-001; apps run in a Docker sandbox; links rook-weld-six.vercel.app and github.com/tony19053000/rook; about 14 of 40 Bobcoins used.

OUTPUT:
- v2 source at docs/submission/video/rook-film-v2.html (build on v1 and its render.mjs; compositing the real footage can be done with ffmpeg overlays or a <video> element seeked per frame).
- Final MP4s: ~/Videos/Rook-video-v2.mp4 (with subtitles) and ~/Videos/Rook-video-v2-clean.mp4 (without), length 2:30–3:00, 1920x1080, 30 fps. Optional: mix in an MP3 the user drops in ~/Videos/.
- Render a 1 fps preview first and check a contact sheet once, then render the full video.
- Do not touch the product code except for a small CLI bug fix if you decide it is needed; do not deploy anything.
```
