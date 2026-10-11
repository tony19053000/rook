// How Rook works, the 6 steps (06 §4). One list, used by the home walkthrough (ROOK-044) and /docs (ROOK-045).

export interface FlowStep {
  id: string;
  title: string;
  summary: string;
  details: string[];
}

export const flowSteps: FlowStep[] = [
  {
    id: "understand",
    title: "Understand",
    summary: "Bob agents read your repo, start the app in a sandbox and map its HTTP API.",
    details: [
      "Scout reads the repo.",
      "Mechanic starts the app in a sandbox (Docker on the CLI).",
      "Mapper turns its HTTP API into actions and state readers.",
    ],
  },
  {
    id: "rules",
    title: "Rules",
    summary: "Bob proposes business rules with evidence from the code, and you approve them.",
    details: [
      "The Lawmaker proposes business rules (invariants) with evidence from the code.",
      "The Rule Critic rejects weak ones.",
      "You approve them. They're saved in rook/rook.yaml in your repo.",
    ],
  },
  {
    id: "search",
    title: "Search",
    summary: "The deterministic engine runs seeded sequences of valid actions against the real running app.",
    details: [
      "Seeded, reproducible sequences of valid actions run against the real running app.",
      "Every approved rule is checked after every step with a safe expression evaluator (no eval).",
      "Strategist weights and Test Designer scenarios steer the search. Concurrent steps catch races.",
    ],
  },
  {
    id: "shrink",
    title: "Shrink and prove",
    summary: "A failing sequence is shrunk to a minimal one and replayed on the real app.",
    details: [
      "Delta debugging shrinks the steps, then the values.",
      "The minimal sequence is replayed on the real app, 10 times by default, and flaky results are reported.",
      "It's saved as a counterexample JSON file plus a regression test.",
    ],
  },
  {
    id: "fix",
    title: "Diagnose and fix",
    summary: "Bob finds the root cause, and after you approve, writes the fix in a workspace copy.",
    details: [
      "The Detective finds the root cause; the Diagnosis Reviewer checks it against the evidence.",
      "After you approve, the Surgeon writes the fix, only in a workspace copy and only in the approved files.",
      "The Fix Reviewer checks the fix.",
    ],
  },
  {
    id: "verify",
    title: "Verify and ship",
    summary: "The fix counts only if four engine checks pass. Then a pull request opens.",
    details: [
      "Four engine checks: exact replay, your project's tests, the generated regression test, and a fresh search with a new seed.",
      "Then a pull request opens from a rook/fix-* branch with the steps, diagnosis, fix, test and results.",
    ],
  },
];
