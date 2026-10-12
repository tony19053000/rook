// The /roadmap page copy (06 §5.8): Shipped, Limited and Planned, from the facts in 06 §4 only. Planned items carry
// no dates.

import { site } from "./site";

export interface RoadmapList {
  id: "shipped" | "limited" | "planned";
  title: string;
  intro: string;
  items: string[];
}

export const roadmapCopy = {
  title: "Roadmap",
  description: `What ${site.name} does today, what is limited, and what is planned.`,
  eyebrow: "Roadmap",
  heading: "Roadmap",
  lead: `${site.name} is in early access. This page says what is shipped, what is limited, and what is planned next.`,
} as const;

export const roadmapLists: RoadmapList[] = [
  {
    id: "shipped",
    title: "Shipped",
    intro: "In the code on GitHub today.",
    items: [
      "The rook CLI: an interactive terminal session with agent characters, plus run --ci, replay, explain, verify, init, serve and login.",
      "13 IBM Bob agents as Bob Shell custom modes: a Coordinator and 12 specialists, from Scout to Surgeon.",
      "Rules you approve, saved in rook/rook.yaml in your repo.",
      "A deterministic, seeded search against the real running app that checks every approved rule after every step.",
      "Minimal counterexamples, replayed on the real app (10 times by default) and saved as JSON plus a regression test.",
      "Fixes that count only after four engine checks, delivered on a rook/fix-* branch: a pull request for a GitHub repo, a local branch for a local folder.",
      "A GitHub Action that runs on pull requests, keeps one report comment updated and fails the job if an approved rule breaks.",
      "The web app, with Google sign-in, run history and the GitHub App link.",
    ],
  },
  {
    id: "limited",
    title: "Limited",
    intro: "Available, with limits you should know about.",
    items: [
      "Guest runs on this site offer two example repos, shop-app and minishop, with recorded IBM Bob answers, 3 runs a day.",
      "Hosted runs of your own repos are turned off on the hosted server. Run your own repos with the CLI on your machine.",
      "HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.",
      "Not on PyPI: install from GitHub. Live runs need Docker and your own IBM Bob key.",
      "In the web app, editing a single rule, replaying a counterexample and downloading the test are not built yet.",
    ],
  },
  {
    id: "planned",
    title: "Planned",
    intro: "Planned, with no dates. Plans can change.",
    items: [
      "Hosted runs of your own repos again, from a separate runner host.",
      "Self-serve deletion of your runs and data from the web app.",
      "Editing a single rule, replaying a counterexample and downloading the test in the web app.",
      "More guest example repos, once the Mapper can set up their dependent actions.",
      "Publishing the CLI on PyPI.",
      "Hosted plans. No price is set.",
    ],
  },
];
