# 06 · Public website: Rook

The public marketing site that sits in front of the existing web app, in the same Next.js project (`web/`). Tickets ROOK-043, ROOK-044 and ROOK-045 (doc 05, milestone M11) build it. This doc is the source of truth for its routes, design rules, copy rules and the **product facts** the copy may state.

---

## 1. Routes

| Route | What | Notes |
|---|---|---|
| `/` | Marketing home | Was the app home; the app moves to `/app` |
| `/docs` | How Rook works + getting started | The 6-step flow (§4), install, CLI commands, GitHub Action |
| `/security` | Trust: how data is handled + "What is not yet true" | |
| `/pricing` | Rendered from `content/pricing.ts` | No plans set → "Pricing will be published at launch" |
| `/privacy`, `/terms` | Legal drafts | Visible banner "Draft — pending legal review, not yet in effect" |
| `/login` | Sign-in page (restyled to the site look) | Keeps the Supabase PKCE return (`/login?code=…`): this URL is in the Supabase redirect allowlist, never move it |
| any unknown path | Branded 404 (`app/not-found.tsx`) | |
| `/app` | **The web app home** (was `/`) | Composer, repo picker, guest "Try an example" |
| `/runs`, `/runs/[id]`, `/rules`, `/counterexamples`, `/repositories`, `/github/setup`, `/dev/*` | Unchanged app routes | |

Route-move rules:
- Every in-app link or redirect that meant "the app home" (`href="/"`, `router.replace("/")` after sign-in, the sidebar brand and "New run") now points at `/app`. Sign-out sends the browser to `/` (the site).
- A GitHub App setup return that lands on `/` (`?installation_id=…&setup_action=…&state=…`, see `lib/github.ts` `isSetupReturn`) is redirected to `/github/setup` with the same query **in `middleware.ts`** (works without JS).
- `web/e2e/smoke.mjs` checks `/app` plus the site pages; doc 04 §3.2 is updated to the new route table.

## 2. Stack and constraints

- Next.js App Router, React 19, TypeScript strict, Tailwind v4 (already in `web/`). Add the **`motion`** package (`motion/react`), used only in the home page's client islands, ideally through `LazyMotion` + `m` + `domAnimation`.
- No 3D/WebGL. No analytics, trackers or third-party runtime scripts. Fonts are self-hosted by `next/font` (reuse the IBM Plex Sans/Mono already in `app/layout.tsx`).
- **CSP stays nonce-based** (03 §8). Next.js inlines its flight data as scripts, and with a nonce CSP they need the per-request nonce, so pages keep rendering per request (`dynamic = "force-dynamic"`). This is the "static where possible" limit: pages do no data fetching and are cheap to render, but they are not prerendered. Never weaken the CSP (no `'unsafe-inline'` scripts) to make a page static: the site shares an origin with the app, whose Supabase session lives in `localStorage`.
- No secrets in the client bundle: only `NEXT_PUBLIC_SUPABASE_URL` and the public anon key, as today.

## 3. Design

- Quality bar: Linear / Vercel / Resend. **Dark, technical** look, dark only on the site (the app keeps its own warm theme and light mode).
- A real design system: colour tokens, a type scale, spacing, a grid and reusable `Section`, `Card`, `Badge`, `Button` and `CodeBlock` components (under `web/components/site/`). Site tokens are scoped so they don't change the app's tokens.
- An SVG logo mark and wordmark for Rook, and a favicon (`app/icon.svg`, replacing the current one).
- A sticky translucent header with navigation and a **mobile menu built on native `<details>`** (works without JS); a **skip link** to `#main`; a full footer with **Product, Docs, Company and Legal** columns.
- Text contrast at least 4.5:1 (3:1 for large text and UI borders), visible focus rings, keyboard access, layout working from **360 px** wide with no horizontal scroll.

### Motion

- Animate `transform` and `opacity` only. No layout shift. The **server render is the complete, still page**: nothing is rendered hidden (opacity 0, offset) waiting for JS. So: no scroll-reveal entrances, and no page transitions.
- `globals.css` has a `prefers-reduced-motion: reduce` rule that sets `animation: none !important` and `transition: none !important` on everything, so the page is still even before JS loads. Under reduced motion there is no autoplay, no parallax and no smooth scrolling (JS checks `matchMedia` as well).
- Every page is complete with JS disabled: all text readable, all navigation working.

## 4. Product facts (the only claims the copy may make)

Copy lives only in `web/content/*.ts`. Every claim must be true of the current code, written exactly as strong as the code. No invented metrics, customers, logos, testimonials, quotes, ratings or prices. If a fact you want isn't below, verify it in the code (cite the file in your report) or leave it out.

**Name and one-liner.** Rook (CLI command `rook`). *Rook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.* Built on IBM Bob. Tagline options from the PRD: "Find the smallest sequence that breaks your software, before your users do." / "Bob finds the rules. The engine tries to break them. Proof decides."

**Who it's for.** Backend developers and teams whose HTTP APIs hold money, stock, permissions or state machines (e-commerce, billing, wallets, SaaS). Also teams reviewing AI-written code. This is a target audience, never "used by".

**How it works, 6 steps** (one shared list in `content/flow.ts`, used by the home walkthrough and `/docs`):
1. **Understand.** Bob agents read the repo (Scout), start the app in a sandbox (Mechanic: Docker on the CLI) and turn its HTTP API into actions and state readers (Mapper).
2. **Rules.** The Lawmaker proposes business rules (invariants) with evidence from the code; the Rule Critic rejects weak ones; **you approve them**. They're saved in `rook/rook.yaml` in your repo.
3. **Search.** The deterministic engine runs seeded, reproducible sequences of valid actions against the **real running app** and checks every approved rule after every step with a safe expression evaluator (no `eval`). Strategist weights and Test Designer scenarios steer it. Concurrent steps catch races.
4. **Shrink and prove.** A failing sequence is shrunk to a minimal one (delta debugging on steps, then values), replayed on the real app (10 times by default: `engine/replayer.py` `DEFAULT_REPLAYS = 10`; it reports flaky results) and saved as a counterexample JSON plus a regression test.
5. **Diagnose and fix.** The Detective finds the root cause and the Diagnosis Reviewer checks it against the evidence. After you approve, the Surgeon writes the fix (only in a workspace copy, only in the approved files) and the Fix Reviewer checks it.
6. **Verify and ship.** The fix counts only if four engine checks pass: exact replay, your project's tests, the generated regression test, and a fresh search with a new seed (default budget 20,000 sequences, `engine/verifier.py`). Then the fix ships on a `rook/fix-*` branch: for a GitHub repo, a pull request with the steps, diagnosis, fix, test and results; for a local folder, a local branch (`src/rook/cli/runs.py`).

**Bob.** 13 Bob agents as Bob Shell custom modes (a Coordinator + 12 specialists: Scout, Mechanic, Mapper, Lawmaker, Rule Critic, Test Designer, Strategist, Detective, Diagnosis Reviewer, Surgeon, Fix Reviewer, Guide), `src/rook/agents/registry.py`. The Coordinator picks next steps inside rails enforced in code. The Guide answers questions from live run data. Bob is the only AI in Rook. Recorded (replay) mode replays saved real Bob answers, always labelled "recorded".

**Surfaces.** The `rook` CLI (interactive Claude Code-style terminal session with agent characters; plus `rook run --ci`, `replay`, `explain`, `verify`, `init`, `serve`, `login`), the web app, and a GitHub Action (`action.yml`: runs `rook run --ci --auto` on pull requests, keeps one `rook-report.md` comment updated, fails the job if an approved rule breaks (exit 1) or the run doesn't finish (exit 2)).

**Install.** `uv tool install git+https://github.com/tony19053000/rook`. Needs Python 3.12+, Docker, and IBM Bob Shell with your own `BOB_API_KEY` for live runs. **Not on PyPI yet.** Repo: https://github.com/tony19053000/rook (MIT licence).

**Targets.** Any backend with an HTTP API, in any language; the demo apps are Node.js (shop-app), Python/FastAPI (billing-service) and Go (wallet-api).

**What Rook refuses to do (guarantees), each enforced in code:**
- Let an AI decide pass or fail. Only the deterministic engine marks a rule broken or a fix verified.
- Execute AI-generated code. Rules go through a safe expression evaluator; actions are declarative HTTP templates; no `eval`/`exec` of model output.
- Change your code without your approval. Only the Surgeon edits, only in a workspace copy, only the approved files (the diff is path-checked and reverted otherwise). `--auto` skips the questions, but the fix still lands on its own branch for review (a PR for a GitHub repo).
- Push to your default branch. Fixes land on a `rook/fix-<id>` branch: a PR for a GitHub repo, a local branch for a local folder.
- Call anything but your sandboxed app. The engine only sends requests to the sandbox's host and port, follows no redirects elsewhere, 10 s timeout, 1 MB response cap.
- Hand your secrets to the app or the logs. The sandbox gets none of Rook's environment; a redaction filter scrubs keys and tokens from events and logs.
- Run arbitrary repos for guests on the hosted site. Guests run only allowlisted demo repos pinned by commit SHA.

**Where Rook is today (honest scope):**
- A hackathon-stage project (IBM Bob 2.0 Hackathon, Sep 2026). No paid plans, no billing, no team accounts, no SSO.
- The hosted site's guest demo offers **shop-app** only, with **recorded** Bob answers (labelled "recorded"); billing-service and wallet-api are pinned on the server but not offered (the Mapper can't yet set up their dependent actions). Guests get 3 runs a day.
- Signed-in users with the GitHub App linked can run their own GitHub repos on the hosted server only when the server enables it (`/me` `can_run_github`), one such run at a time server-wide, 5 per user per day, live Bob with a coin budget. Otherwise the CLI runs your repos on your machine.
- HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.
- Not on PyPI; install from GitHub. Live runs need Docker and your own IBM Bob key.
- In the web app, editing a single rule, replaying a counterexample and downloading the test are not built yet.

**Sign-in.** Google through **Supabase Auth** (PKCE), the existing `lib/session.ts` (`signInWithGoogle`, `completeSignIn`, `signOut`). Never a second auth path. The session lives in `localStorage` key `rook-auth`; sign-out is local to the browser.

**Data the app actually processes** (for `/privacy` and `/security`; verify anything else before stating it):
- Google sign-in via Supabase: Supabase holds the account (email, name and profile data from Google). The browser keeps the Supabase session in `localStorage` (`rook-auth`).
- Rook server database (SQLite, `src/rook/store/db.py`): runs (owner id or guest key, repo kind and ref, status, timestamps, Bob coins), each run's event log (redacted; includes the request text typed into the composer and chat), counterexamples, and for users who link GitHub a `users` row (Supabase user id, email, GitHub installation id, created time). Guest quota rows keyed by the guest cookie id and by **client IP address**, per day (`server/routes/runs.py`). In-memory per-IP rate limiting.
- Cookies: `rook_guest` (signed, httpOnly, SameSite=Lax; identifies a guest browser for the demo quota) and `rook_login` (signed, 10 minutes, only during CLI sign-in). `localStorage`: `rook-auth`, `rook.sidebar.collapsed`.
- GitHub (only if you connect it): the installation id, your installation's repo list as GitHub reports it, short-lived installation tokens kept in memory. For a hosted GitHub run, the repo is cloned into a server workspace.
- IBM Bob: in live runs, repo content and run data go to IBM Bob as prompts. The guest demo uses recorded answers.
- Hosting: the web on Vercel, the API on AWS EC2 behind Caddy. No automatic deletion of runs is implemented.
- No analytics, ads or tracking scripts on the site or the app.

**Security facts** (for `/security`, from doc 03): Docker sandbox hardening (non-root, `--cap-drop ALL`, `no-new-privileges`, pids/memory/CPU limits, only the workspace copy mounted, ports on 127.0.0.1, internal network at run time); Bob runs read-only except the Mechanic (`.rook-sandbox/`) and the Surgeon (approved paths), no command/browser/MCP tools, repo text marked untrusted, strict JSON schemas; secrets only on the host, never in git, logs, events or the web bundle; GitHub App with minimum permissions (Contents RW, Pull requests RW, Metadata R), webhooks HMAC-verified, per-repo installation tokens; every run route checks the owner and answers 404 to others; rate limits and guest quotas; CSP with a per-request nonce plus the other headers in 03 §8.

**What is not yet true (security, honest):** no third-party audit or penetration test, no certifications; on the hosted server the container that starts sandboxes has the Docker socket, which is root-equivalent on the host if the server itself had a remote-code-execution bug (accepted for the hackathon; the long-term fix is a separate runner host); prompt injection from repo text is bounded by tool permissions and engine checks, not eliminated; offline settings for allowlisted demo test commands are best effort; no automatic data deletion or self-serve account deletion yet.

## 5. Pages

1. **Home** (`/`): a cinematic hero with layered, scroll-driven parallax (background grid, glow, product figure; the hero text never moves) → an animated product walkthrough (§6) → Features → "What Rook refuses to do" → "Where Rook is today" → FAQ (native `<details>`) → closing call to action.
2. **Docs** (`/docs`): the full 6-step flow, then getting started (install, first run, CLI commands, the GitHub Action).
3. **Security** (`/security`): data handling, sandboxing, AI boundaries, secrets, auth, then "What is not yet true".
4. **Pricing** (`/pricing`): `content/pricing.ts` exports the plans list (empty today). The page and anything else that mentions pricing derive the status from that one export; with no plans it shows "Pricing will be published at launch". Never a number.
5. **Privacy** and **Terms**: drafts, with the banner and visible placeholders `[Company legal name]`, `[contact email]`, `[jurisdiction]`. Privacy describes only §4 "Data the app actually processes".
6. **Sign-in** (`/login`) and a branded **404**.

CTAs: "Try the demo" → `/app`. "Sign in" → `/login`. Signed-in visitors see **"Open workspace"** → `/app` instead (a client-side hint read from `localStorage` `rook-auth` without loading the auth library; the server render shows the signed-out CTAs).

## 6. Walkthrough (home)

- One frame at a time, no scrollbar, autoplays; clicking a step in the list on the left slides to that frame (transform). A small pause/play control. Steps are the 6 from `content/flow.ts`.
- Frames are built from the app's **real UI components** (`AgentRow`, `EngineRow`, `RulesCard`, `SearchCard`, `CounterexampleCard`, `FixCard`, `VerifyCard`, …) fed with **sample data** in `content/walkthrough.ts`, modelled on the recorded shop-app/minishop run (e.g. buy ₹100 → refund ₹60 → refund ₹50; paid ₹100, refunded ₹110; replayed 10/10).
- Frames are inert: the `inert` attribute, no network, no real actions (the default read-only `RunActionsContext`), and each is labelled **"Product illustration — not a live run"**. Only the active frame is exposed; the others are `inert` and `aria-hidden`.
- Under reduced motion: no autoplay, no slide animation (an instant switch). With JS off: frame 1 shows and every step's text is readable in the list.

## 7. Sign-in

- Sign in only on a click, never on page load. States: **idle**, **opening** (button disabled, "Opening Google…"), **failed** (the reason and a Retry button), **not configured** (`SIGN_IN_AVAILABLE` false: a plain message and a link to try the demo, no dead button). Returning from Google with `?code=` completes the sign-in the user already started, then goes to `/app`.
- With JS off: a `<noscript>` note that sign-in needs JavaScript; the rest of the page still renders.
- The app keeps its account menu with **Sign out** (`components/Sidebar.tsx`).

## 8. Metadata and performance

- Per-page title (template `%s · Rook`), description, Open Graph and Twitter cards (`summary_large_image` with an OG image), theme colour.
- `motion` is imported only by the home page's client islands. Header, footer and the inner pages are server components (the header's signed-in hint is the only client island they need).

## 9. Tests (Vitest + React Testing Library, jsdom per file)

- Each page renders with correct landmarks (`banner`, `main`, `contentinfo`, `navigation`) and heading order (one `h1`, no skipped levels).
- No social-proof or invented-number patterns anywhere in `content/*.ts` or the rendered pages ("trusted by", "customers", "testimonial", percentages, "10x", "1,000+", prices per month, star ratings, …).
- Pricing shows the launch notice while no plans are set.
- The legal drafts show their banner and placeholders.
- Under reduced motion the page is complete and still (no autoplay, no parallax transforms; the CSS rule exists).
- Sign-in is never called without a click.
- The walkthrough makes no network calls and only one frame is visible.
- The skip link targets `#main` and the 404 page renders.
- Deliberately break each rule once, confirm a test fails, then restore the code (list each break in the report).
- `npm run typecheck`, `npm run lint` (ESLint flat config: TypeScript, React hooks, Next, jsx-a11y), `npm run test` and `npm run build` all pass.
