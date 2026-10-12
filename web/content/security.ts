// The /security page copy (06 §5.3): a plain summary of docs/03_SECURITY_ACCESS.md and the code, never stronger
// than either, then "What is not yet true". No certifications or audits are claimed or implied.

export interface SecuritySection {
  id: string;
  title: string;
  intro?: string;
  items: string[];
  /** An internal link after the list. */
  link?: { label: string; href: string };
}

export const securityCopy = {
  title: "Security",
  description: "How Rook handles your data and code: sandboxing, AI boundaries, secrets and sign-in, and what is not yet true.",
  eyebrow: "Security",
  heading: "Security at Rook",
  lead: "Rook runs your app and reads your code, so this page says exactly how that is contained today, and what is not yet true.",
  tocLabel: "On this page",
} as const;

export const securitySections: SecuritySection[] = [
  {
    id: "data",
    title: "How data is handled",
    items: [
      "Sign-in is Google through Supabase Auth. Supabase holds the account; the browser keeps the session in localStorage.",
      "The Rook server stores runs, each run's redacted event log (including what you type into the composer and chat) and counterexamples. Guest run quotas are counted per guest cookie and per client IP address, per day.",
      "If you connect GitHub, Rook stores your installation id and keeps short-lived installation tokens in memory only.",
      "In live runs, repo content and run data go to IBM Bob as prompts. Guest runs use recorded Bob answers.",
      "No analytics, ads or tracking scripts on the site or the app.",
      "You can delete a run, or all your data on the Rook server, from the web app. Runs older than 30 days and guest quota rows older than 2 days are deleted automatically.",
    ],
    link: { label: "Read the privacy policy", href: "/privacy" },
  },
  {
    id: "sandboxing",
    title: "Sandboxing",
    intro: "Rook starts the app it tests in a sandbox and talks to it only over HTTP.",
    items: [
      "The CLI runs your app in Docker as a non-root user with --cap-drop ALL, no-new-privileges and pids, memory and CPU limits.",
      "Only the workspace copy of your repo is mounted, never your home folder or the original. Ports are published on 127.0.0.1 only, and at run time the app gets an internal network wherever the app allows it.",
      "The sandbox gets none of Rook's environment, so Rook's keys never reach your app.",
      "The engine sends requests only to the sandbox's host and port, follows no redirects elsewhere, and uses a 10 s timeout and a 1 MB response cap.",
      "On the hosted site, guests run only allowlisted example repos pinned by commit SHA, with recorded Bob answers, in a process sandbox as a separate unprivileged user. The hosted server mounts no Docker socket, and hosted runs of your own repos are turned off. Run your own repo with the CLI on your machine.",
    ],
  },
  {
    id: "ai-boundaries",
    title: "AI boundaries",
    intro: "IBM Bob is the only AI in Rook. It proposes and explains; the deterministic engine decides.",
    items: [
      "Every Bob agent is read-only except two: the Mechanic, which may write only under .rook-sandbox/, and the Surgeon, which may edit only the files in the reviewed diagnosis. A Surgeon change outside those paths is reverted and rejected.",
      "No agent gets command, browser or MCP tools. The engine runs commands, not Bob.",
      "Repo content is marked as untrusted data in every prompt, and every answer must match a strict JSON schema.",
      "Bob's output is never executed. Rules are checked with a safe expression evaluator (no eval or exec), and actions are declarative HTTP templates.",
      "Only the engine marks a rule broken or a fix verified. Approving rules, applying a fix and opening a pull request need your answer, or --auto, which still ends on a branch for review.",
    ],
  },
  {
    id: "secrets",
    title: "Secrets",
    items: [
      "Secrets live only on the host: never in git, logs, events or the web bundle.",
      "A redaction filter scrubs keys and tokens from every event, log line and error before it is stored or sent.",
      "The Bob key reaches Bob only through the child process environment, never on the command line.",
      "The browser gets only the Supabase project URL and its public key.",
    ],
  },
  {
    id: "auth",
    title: "Sign-in and GitHub",
    items: [
      "Google sign-in uses Supabase Auth with PKCE. Sign-out is local to the browser.",
      "The server verifies the Supabase token on every call. Guests get a signed, httpOnly guest cookie.",
      "Every run route checks the owner and answers 404 to anyone else, so run ids don't leak.",
      "The Rook GitHub App asks for the minimum: Contents read & write, Pull requests read & write, Metadata read. Webhooks are verified with HMAC, and installation tokens are scoped to one repo.",
      "Rook never pushes to your default branch: fixes land on a rook/fix-* branch, as a pull request for a GitHub repo.",
    ],
  },
  {
    id: "hardening",
    title: "Web and server hardening",
    items: [
      "A Content Security Policy with a per-request nonce, plus Referrer-Policy, X-Content-Type-Options, X-Frame-Options and a Permissions-Policy that turns off camera, microphone, geolocation and payment.",
      "Rate limits on the API (60 requests per minute per IP, 10 per minute to start runs) and daily guest quotas.",
      "Every request body is validated against a schema, with a 64 KB size limit.",
      "Repo files, Bob output and diffs are rendered as escaped text in the web app.",
    ],
  },
];

export const notYetTrue = {
  id: "not-yet-true",
  title: "What is not yet true",
  intro: "Rook is in early access. These are the gaps we know about today.",
  items: [
    "There has been no third-party audit or penetration test, and Rook holds no certifications.",
    "Hosted runs of your own repos are off. Starting sandboxes from the server needs the Docker socket, which is root-equivalent on the host, so the hosted server no longer mounts it. Turning hosted runs back on needs a separate runner host.",
    "Prompt injection from repo text is bounded by Bob's tool permissions and the engine's checks, not eliminated.",
    "The offline settings for the allowlisted example apps' test commands are best effort.",
    "Your Supabase sign-in account is deleted by emailing the contact address, not self-serve. Run and server data deletion is self-serve in the web app.",
  ],
} as const;
