"use client";

// The client halves of the pages: each wires the API client, the session and the recents into a view.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { GithubSetupView, type GithubSetupStatus } from "./GithubSetupView";
import { HomeView } from "./HomeView";
import { RunPage } from "./RunPage";
import { CounterexamplesView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { SIGN_IN_AVAILABLE, signInWithGoogle } from "@/lib/session";
import { useApi, useBobMode, useRepos, useRuns, useSession } from "@/lib/useShell";
import { finishGithubConnect, SETUP_PATH, setupParams, startGithubConnect } from "@/lib/github";

export function HomeClient() {
  const api = useApi();
  const session = useSession(api);
  const runs = useRuns(api);
  const repos = useRepos(api);
  const bobMode = useBobMode(api);
  const router = useRouter();

  const connectGithub = useCallback(() => startGithubConnect(api, (url) => window.location.assign(url)), [api]);
  const signIn = useCallback(() => signInWithGoogle(window.location.origin), []);
  return (
    <HomeView
      api={api}
      session={session}
      runs={runs}
      repos={repos}
      bobMode={bobMode}
      navigate={(href) => router.push(href)}
      connectGithub={connectGithub}
      signIn={SIGN_IN_AVAILABLE ? signIn : undefined}
    />
  );
}

export function GithubSetupClient() {
  const api = useApi();
  const session = useSession(api);
  const runs = useRuns(api);
  const router = useRouter();
  const [status, setStatus] = useState<GithubSetupStatus>({ kind: "working" });

  useEffect(() => {
    const params = setupParams(window.location.search);
    if (params === null) {
      setStatus({ kind: "error", message: "This GitHub link is incomplete. Connect GitHub again from Rook." });
      return;
    }
    let cancelled = false;
    void finishGithubConnect(api, params).then((message) => {
      if (cancelled) return;
      setStatus(message === null ? { kind: "done" } : { kind: "error", message });
      router.replace(SETUP_PATH); // the one-time state and code leave the address bar
    });
    return () => {
      cancelled = true;
    };
  }, [api, router]);

  const connectGithub = useCallback(() => startGithubConnect(api, (url) => window.location.assign(url)), [api]);
  return <GithubSetupView session={session} runs={runs} status={status} connectGithub={connectGithub} />;
}

export function RunClient({ runId }: { runId: string }) {
  const api = useApi();
  const session = useSession(api);
  const runs = useRuns(api);
  const router = useRouter();
  return <RunPage key={runId} runId={runId} api={api} session={session} runs={runs} navigate={(href) => router.push(href)} />;
}

export function RunsClient() {
  const api = useApi();
  return <RunsPageView session={useSession(api)} runs={useRuns(api)} />;
}

export function CounterexamplesClient() {
  const api = useApi();
  return <CounterexamplesView session={useSession(api)} runs={useRuns(api)} />;
}

export function RulesClient() {
  const api = useApi();
  return <RulesView session={useSession(api)} runs={useRuns(api)} />;
}

export function RepositoriesClient() {
  const api = useApi();
  const repos = useRepos(api);
  const connectGithub = useCallback(() => startGithubConnect(api, (url) => window.location.assign(url)), [api]);
  return (
    <RepositoriesView
      session={useSession(api)}
      runs={useRuns(api)}
      repos={repos.repos}
      loading={repos.loading}
      error={repos.error}
      onRetry={repos.retry}
      connectGithub={connectGithub}
    />
  );
}
