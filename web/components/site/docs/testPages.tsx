// Every docs page with its route, for the tests that render them all (docs.test.tsx, launch.test.tsx).
import type { ReactElement } from "react";
import CounterexamplesGuidePage from "@/app/(site)/docs/counterexamples/page";
import DataGuidePage from "@/app/(site)/docs/data/page";
import GettingStartedGuidePage from "@/app/(site)/docs/getting-started/page";
import GithubActionGuidePage from "@/app/(site)/docs/github-action/page";
import InstallGuidePage from "@/app/(site)/docs/install/page";
import DocsPage from "@/app/(site)/docs/page";
import RulesGuidePage from "@/app/(site)/docs/rules/page";

export const DOCS_OVERVIEW: [string, () => ReactElement] = ["/docs", () => <DocsPage />];

export const GUIDE_PAGES: [string, () => ReactElement][] = [
  ["/docs/getting-started", () => <GettingStartedGuidePage />],
  ["/docs/install", () => <InstallGuidePage />],
  ["/docs/rules", () => <RulesGuidePage />],
  ["/docs/counterexamples", () => <CounterexamplesGuidePage />],
  ["/docs/github-action", () => <GithubActionGuidePage />],
  ["/docs/data", () => <DataGuidePage />],
];
