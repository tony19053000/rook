"use client";

// The client halves of the pages: each wires the API client, the session and the recents into a view.

import { useRouter } from "next/navigation";
import { HomeView } from "./HomeView";
import { RunPage } from "./RunPage";
import { CounterexamplesView, LoginView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { useApi, useRepos, useRuns, useSession } from "@/lib/useShell";

export function HomeClient() {
  const api = useApi();
  const session = useSession();
  const runs = useRuns(api);
  const repos = useRepos(api);
  const router = useRouter();
  return <HomeView api={api} session={session} runs={runs} repos={repos} navigate={(href) => router.push(href)} />;
}

export function RunClient({ runId }: { runId: string }) {
  const api = useApi();
  const session = useSession();
  const runs = useRuns(api);
  return <RunPage key={runId} runId={runId} api={api} session={session} runs={runs} />;
}

export function RunsClient() {
  const api = useApi();
  return <RunsPageView session={useSession()} runs={useRuns(api)} />;
}

export function CounterexamplesClient() {
  const api = useApi();
  return <CounterexamplesView session={useSession()} runs={useRuns(api)} />;
}

export function RulesClient() {
  const api = useApi();
  return <RulesView session={useSession()} runs={useRuns(api)} />;
}

export function LoginClient() {
  const api = useApi();
  return <LoginView session={useSession()} runs={useRuns(api)} />;
}

export function RepositoriesClient() {
  const api = useApi();
  const repos = useRepos(api);
  return <RepositoriesView session={useSession()} runs={useRuns(api)} repos={repos.repos} loading={repos.loading} error={repos.error} onRetry={repos.retry} />;
}
