# 06 · Public website: Rook

The public marketing site that sits in front of the existing web app, in the same Next.js project (`web/`). Tickets ROOK-043 to ROOK-048 (doc 05, milestone M11) built it; M12 (ROOK-049 to ROOK-057, launch readiness) reworks it for an early-access launch. This doc is the source of truth for its routes, design rules, copy rules and the **product facts** the copy may state.

---

## 1. Routes

| Route | What | Notes |
|---|---|---|
| `/` | Marketing home | Was the app home; the app moves to `/app` |
| `/docs` | Docs overview: the 6-step flow and links to the guides | |
| `/docs/getting-started` | Short guide: install, first run, what you see (M12) | |
| `/docs/install` | Detailed install: supported environments, dependencies, Bob credentials, limitations (M12) | |
| `/docs/rules` | The approved-rules workflow and an example `rook/rook.yaml` (M12) | The example is a real file from the repo, not invented |
| `/docs/counterexamples` | Minimal counterexamples, replay consistency and verified fixes, with the refund-bug example (M12) | |
| `/docs/github-action` | The GitHub Action and the pull-request workflow (M12) | |
| `/docs/data` | IBM Bob credentials and exactly when repo data is sent to IBM Bob (M12) | |
| `/security` | Trust: how data is handled + "What is not yet true" | |
| `/pricing` | Early access and open source (M12) | Free ways to use Rook today; hosted plans not priced; never a number |
| `/roadmap` | Shipped, limited and planned (M12) | From §4 facts only |
| `/about` | What Roook does, the founder and the project story (M12, ROOK-060) | §4 "Operator and contact" |
| `/contact` | Contact and early-access interest (M12) | The email, founder and website; `mailto:` links with a prefilled subject + GitHub Issues; no form backend |
| `/privacy`, `/terms` | Privacy policy and terms, in effect (M12) | Name the operator ("Aayush Kumar, operating Roook"), the site URL, the contact email and India; no placeholders, no draft banner, no company form or postal address |
| `/sitemap.xml`, `/robots.txt` | `app/sitemap.ts`, `app/robots.ts` (M12) | Site pages only; app routes (`/app`, `/runs`, …) and `/dev/*` disallowed |
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
- No 3D/WebGL. No analytics, trackers or third-party runtime scripts. Fonts are self-hosted by `next/font` (the three families already in `app/fonts.ts`: Newsreader for headings, IBM Plex Sans for text and UI, IBM Plex Mono for labels and data).
- **CSP stays nonce-based** (03 §8). Next.js inlines its flight data as scripts, and with a nonce CSP they need the per-request nonce, so pages keep rendering per request (`dynamic = "force-dynamic"`). This is the "static where possible" limit: pages do no data fetching and are cheap to render, but they are not prerendered. Never weaken the CSP (no `'unsafe-inline'` scripts) to make a page static: the site shares an origin with the app, whose Supabase session lives in `localStorage`.
- No secrets in the client bundle: only `NEXT_PUBLIC_SUPABASE_URL` and the public anon key, as today.

## 3. Design

- Quality bar: Linear / Vercel / Resend. **Dark, technical** look, dark only on the site (the app keeps its own warm theme and light mode).
- Look (ROOK-058): warm near-black neutrals (so the app screenshots and walkthrough frames sit in the page), hairline borders, serif headings like the app's own, mono labels. Colour carries meaning: the primary button is the page's ink on its background; the coral accent is for the mark, small marks and the "rule broken" state; green is what the engine verified; blue marks IBM Bob's steps. Wide sections are separated by hairlines; long-form pages (security, legal, about, guides) are one readable column with a hairline between sections; guides have the docs navigation in a left rail and the table of contents in a right rail on wide screens.
- A real design system: colour tokens, a type scale, spacing, a grid and reusable `Section`, `Card`, `Badge`, `Button` and `CodeBlock` components (under `web/components/site/`). Site tokens are scoped so they don't change the app's tokens.
- An SVG logo mark and wordmark for Rook, and a favicon (`app/icon.svg`, replacing the current one).
- A sticky translucent header with navigation and a **mobile menu built on native `<details>`** (works without JS); a **skip link** to `#main`; a full footer with **Product, Docs, Company and Legal** columns.
- Layout widths: the header bar spans the full viewport (logo at the left padding, CTAs at the right padding); page content sits in a container up to about 1440 px (`max-w-[90rem]`) whose side padding grows on large screens, and grids, the hero figure and the walkthrough use that width. Paragraphs, leads, lists and FAQ answers keep a readable measure (`max-w-2xl`/`max-w-3xl`); long-form pages (security, legal, 404, sign-in) use the narrow column.
- Text contrast at least 4.5:1 (3:1 for large text and UI borders), visible focus rings, keyboard access, layout working from **360 px** wide with no horizontal scroll.

### Motion

- Animate `transform` and `opacity` only. No layout shift. The **server render is the complete, still page**: nothing is rendered hidden (opacity 0, offset) waiting for JS. So: no scroll-reveal entrances, and no page transitions.
- `globals.css` has a `prefers-reduced-motion: reduce` rule that sets `animation: none !important` and `transition: none !important` on everything, so the page is still even before JS loads. Under reduced motion there is no autoplay, no parallax and no smooth scrolling (JS checks `matchMedia` as well).
- Every page is complete with JS disabled: all text readable, all navigation working.

## 4. Product facts (the only claims the copy may make)

Copy lives only in `web/content/*.ts`. Every claim must be true of the current code, written exactly as strong as the code. No invented metrics, customers, logos, testimonials, quotes, ratings or prices. If a fact you want isn't below, verify it in the code (cite the file in your report) or leave it out.

**Name and one-liner.** Roook (the display name since 12 Oct 2026; older parts of this doc still say Rook; CLI command `rook`). *Roook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.* Built on IBM Bob. Tagline options from the PRD: "Find the smallest sequence that breaks your software, before your users do." / "Bob finds the rules. The engine tries to break them. Proof decides."

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

**Positioning (M12).** Rook is an **early-access, open-source** developer tool. The site never presents it as a hackathon entry: the hackathon appears only in the About page's project story ("Rook started at the IBM Bob 2.0 Hackathon in September 2026"). IBM Bob is acknowledged ("Built on IBM Bob", in the footer, About, docs and the FAQ), but headlines and leads talk about Rook's own value: finding, proving and fixing business-rule bugs. The primary CTA stays **"Try Rook"** (no visible "demo", ROOK-048); the secondary CTA is **"Read the docs"** (→ `/docs/getting-started`) plus a GitHub link.

**Operator and contact (M12, updated ROOK-060).** Roook is an **independent, founder-led, early-stage startup**, founded and run by **Aayush Kumar — Founder, Roook**, an individual based in **India**. It is **not incorporated as a company**: no registration, no postal address, no cofounders, no employees, no clients, no revenue, no investors or funding; never imply any, and never invent the founder's credentials or work history. Contact, support and privacy requests: **aayush@roook.dev** (one constant, `CONTACT_EMAIL` in `content/site.ts`; the mailbox is hosted by Zoho Mail). No other mailbox, phone number or address appears on the site. Bugs and feature requests: GitHub Issues on the repo. Legal pages: operator "Aayush Kumar, operating Roook" (an individual, India); governing law: the laws of India.

**Site URL (ROOK-060).** `SITE_URL` in `content/site.ts` = `https://www.roook.dev`, the canonical production origin (`roook.dev` redirects to it). `metadataBase`, canonical links, the sitemap, robots, the structured data and OG URLs all derive from it. The Vercel address `https://rook-weld-six.vercel.app` still serves the same deployment and stays in the sign-in redirect allowlist; it is not shown in the copy.

**Recorded vs live.** A run with recorded Bob answers is always labelled **"Recorded example run"** with a one-line explanation (Bob's answers are replayed from a saved real run; the engine still runs live against the real app). A run with live Bob calls is labelled **"Live run"**. Never blur the two.

**Where Rook is today (honest scope):**
- Early access. No paid plans, no billing, no team accounts, no SSO.
- The hosted site's guest runs offer two example repos, **shop-app** (Node.js) and **minishop** (Python, Rook's own small test shop), with **recorded** Bob answers (labelled "Recorded example run"; `deploy/demos/demos.yaml`). A live guest run of shop-app on 12 Oct took about 2 min: found the refund rule broken, shrank it to 4 steps, replayed 10/10, fixed and verified 4/4 (hosted fresh-search budget is smaller than the CLI default: 395 sequences in that run); billing-service and wallet-api are pinned on the server but not offered (the Mapper can't yet set up their dependent actions). Guests get 3 runs a day.
- **Hosted runs of your own repos are turned off** on the hosted server (ROOK-050: no Docker socket on the server until a separate runner host exists). Signed-in users can link the GitHub App and see their repos; Rook shows the CLI command to run a repo on their own machine.
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
- Hosting: the web on Vercel, the API on AWS EC2 (US West, Oregon) behind Caddy.
- Deletion and retention (ROOK-051): the owner can delete a run (its events and counterexamples too); a signed-in user can delete all their Rook server data (runs and the GitHub link) from the account menu; runs older than 30 days and guest quota rows older than 2 days are deleted automatically. The Supabase sign-in account itself is deleted on request by email (the Rook server can't delete it).
- No analytics, ads or tracking scripts on the site or the app.

**Security facts** (for `/security`, from doc 03): Docker sandbox hardening (non-root, `--cap-drop ALL`, `no-new-privileges`, pids/memory/CPU limits, only the workspace copy mounted, ports on 127.0.0.1, internal network at run time); Bob runs read-only except the Mechanic (`.rook-sandbox/`) and the Surgeon (approved paths), no command/browser/MCP tools, repo text marked untrusted, strict JSON schemas; secrets only on the host, never in git, logs, events or the web bundle; GitHub App with minimum permissions (Contents RW, Pull requests RW, Metadata R), webhooks HMAC-verified, per-repo installation tokens; every run route checks the owner and answers 404 to others; rate limits and guest quotas; CSP with a per-request nonce plus the other headers in 03 §8.

**What is not yet true (security, honest):** no third-party audit or penetration test, no certifications; hosted runs of your own repos are off because starting sandboxes from the server needs the Docker socket, which is root-equivalent on the host (the server no longer mounts it, ROOK-050; turning hosted runs back on needs a separate runner host); prompt injection from repo text is bounded by tool permissions and engine checks, not eliminated; offline settings for allowlisted demo test commands are best effort; the Supabase sign-in account is deleted by email request, not self-serve.

## 5. Pages

1. **Home** (`/`, reworked in ROOK-054): a problem-first hero with layered, scroll-driven parallax (background grid, glow, and a **real screenshot** of a recorded minishop run, labelled "Recorded example run"; the hero text never moves) → the refund-bug story (rule, 4-step minimal sequence, replay, diagnosis, fix, 4 checks; `content/story.ts`, every value checked against the recorded run) → the 6-step diagram (an `<ol>`) → an animated product walkthrough (§6) → Features → "What Rook refuses to do" → "Where Rook is today" → FAQ (native `<details>`) → closing call to action.
2. **Docs** (`/docs`): the full 6-step flow, then getting started (install, first run, CLI commands, the GitHub Action).
3. **Security** (`/security`): data handling, sandboxing, AI boundaries, secrets, auth, then "What is not yet true".
4. **Pricing** (`/pricing`, M12): "Early access and open source". Three ways to use Rook, each with what it costs **today** in words, never a number: (1) **Try Rook on this site**: free, no account, recorded example runs of the example repos, 3 a day; (2) **The CLI on your machine**: free and open source (MIT), your own Docker and IBM Bob key (any IBM Bob usage cost is between you and IBM); (3) **Hosted runs of your own repos**: not offered yet, planned, no price set. Then a short "Interested in hosted Rook?" → `/contact`. `content/pricing.ts` keeps the `plans` export (empty) so a future price list has one source.
5. **Privacy** and **Terms** (M12): in effect from their "Last updated" date, operator, email and India named, no placeholders and no draft banner. Privacy describes only §4 "Data the app actually processes": what is collected, where it is stored, who receives it (Supabase, Vercel, AWS, GitHub, IBM Bob), how long it is kept, and how to delete it. Terms: open-source licence for the code, the hosted site as-is during early access, acceptable use (only repos you may test), no warranty, liability limited as far as Indian law allows.
6. **Sign-in** (`/login`) and a branded **404**.
7. **About** (`/about`): what Roook does (finds, reproduces, verifies; only the engine decides), a founder card ("Aayush Kumar — Founder, Roook", a short introduction, the email and the website; §4 "Operator and contact"), why it exists, the project story (started at the IBM Bob 2.0 Hackathon, Sep 2026; an independent product since), and where it stands (founder-led, not incorporated, no employees or funding, free in early access).
8. **Roadmap** (`/roadmap`): three lists, **Shipped**, **Limited** and **Planned**, from §4 only. Planned items carry no dates.
9. **Contact** (`/contact`): the email, the founder and the website at the top; the email (general, early access, privacy) as `mailto:` links with prefilled subjects, GitHub Issues for bugs, and what to expect (one person reads it; no response-time promise).
10. **Docs guides** (`/docs/*`, §1): each a long-form page with a table of contents; commands copied from the real CLI (`uv run rook --help`) and files from the repo; known limitations stated plainly.

CTAs: "Try Rook" → `/app` (primary). "Read the docs" → `/docs/getting-started` (secondary). "Sign in" → `/login`. Signed-in visitors see **"Open workspace"** → `/app` instead (a client-side hint read from `localStorage` `rook-auth` without loading the auth library; the server render shows the signed-out CTAs).

## 6. Walkthrough (home)

- One frame at a time, no scrollbar, autoplays; clicking a step in the list on the left slides to that frame (transform). A small pause/play control. Steps are the 6 from `content/flow.ts`.
- Frames are built from the app's **real UI components** (`AgentRow`, `EngineRow`, `RulesCard`, `SearchCard`, `CounterexampleCard`, `FixCard`, `VerifyCard`, …) fed with **sample data** in `content/walkthrough.ts`, taken from the recorded minishop run (`web/lib/fixtures/minishop-run.json`, the same case as the home's refund story in `content/story.ts`: create_product(price 1) → buy → refund 1 → refund 1; paid 1, refunded 2; replayed 10/10; fresh search 1,500 sequences in that run, the CLI default being 20,000).
- Frames are inert: the `inert` attribute, no network, no real actions (the default read-only `RunActionsContext`), and each is labelled **"Product illustration — not a live run"**. Only the active frame is exposed; the others are `inert` and `aria-hidden`.
- Under reduced motion: no autoplay, no slide animation (an instant switch). With JS off: frame 1 shows and every step's text is readable in the list.

## 7. Sign-in

- Layout (ROOK-058): one centred column that fills the first screen, like a dedicated sign-in page: the mark, the heading and lead, a card whose one main action is **Continue with Google** (with Google's mark), a quiet "Try Rook without signing in" link under it, then the guest note and plain links to Terms and Privacy. Signing in is offered here and from the app sidebar's Sign in button, never inside the app's chat column.
- Sign in only on a click, never on page load. States: **idle**, **opening** (button disabled, "Opening Google…"), **failed** (the reason and a Retry button), **not configured** (`SIGN_IN_AVAILABLE` false: a plain message and a link to try the demo, no dead button). Returning from Google with `?code=` completes the sign-in the user already started, then goes to `/app`.
- With JS off: a `<noscript>` note that sign-in needs JavaScript; the rest of the page still renders. The Google button carries `data-needs-js` and a `<noscript><style>` hides it, so there is no dead button.
- The app keeps its account menu with **Sign out** (`components/Sidebar.tsx`).

## 8. Metadata and performance

- Per-page title (template `%s · Rook`), description, Open Graph and Twitter cards (`summary_large_image` with an OG image), theme colour. `metadataBase` = `SITE_URL`; the favicon, logo, OG image, page titles and the header wordmark use the same mark and name.
- Footer (M12): Product (Overview, Try Rook, Pricing, Roadmap, Sign in), Docs (Getting started, Install, Rules, GitHub Action, Data and IBM Bob), Company (About, Contact, GitHub), Legal (Privacy, Terms, Security). Under the columns (ROOK-060): who operates Roook with the contact address as a `mailto:` link, then the licence line.
- Structured data (ROOK-060): one schema.org JSON-LD block on the home page (`lib/structuredData.ts`, `components/site/JsonLd.tsx`): Organization (name, URL, logo, email, founder, GitHub), Person (the founder), WebSite and SoftwareApplication. Built from `content/site.ts` only; no address, registration, rating, review, price or staff. It is a data block, so the nonce CSP does not apply to it.
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
