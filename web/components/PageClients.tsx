"use client";

// The client halves of the pages: each wires the API client, the session and the recents into a view.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { GithubSetupView, type GithubSetupStatus } from "./GithubSetupView";
import { HomeView } from "./HomeView";
import { RunPage } from "./RunPage";
import { CounterexamplesView, LoginView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { completeSignIn, oauthReturn, SIGN_IN_AVAILABLE, signInWithGoogle, signOutAndReload } from "@/lib/session";
import { useApi, useRepos, useRuns, useSession } from "@/lib/useShell";
import { finishGithubConnect, isSetupReturn, SETUP_PATH, setupParams, startGithubConnect } from "@/lib/github";

export function HomeClient() {
  const api = useApi();
  const session = useSession(api);
  const runs = useRuns(api);
  const repos = useRepos(api);
  const router = useRouter();

  // GitHub's Setup URL may point at the site root: hand the setup return to /github/setup.
  useEffect(() => {
    if (isSetupReturn(window.location.search)) router.replace(`${SETUP_PATH}${window.location.search}`);
  }, [router]);

  const connectGithub = useCallback(() => startGithubConnect(api, (url) => window.location.assign(url)), [api]);
  return <HomeView api={api} session={session} runs={runs} repos={repos} navigate={(href) => router.push(href)} connectGithub={connectGithub} />;
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
  return <RunPage key={runId} runId={runId} api={api} session={session} runs={runs} />;
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

export function LoginClient() {
  const api = useApi();
  const session = useSession(api);
  const runs = useRuns(api);
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Back from Google: /login?code=… (PKCE) or ?error=…; the code is exchanged once, then the URL is cleaned.
  useEffect(() => {
    const back = oauthReturn(window.location.search);
    if (back === null) return;
    if ("error" in back) {
      setError("Sign-in was cancelled or failed. Try again.");
      router.replace("/login");
      return;
    }
    setBusy(true);
    void completeSignIn(back.code).then((message) => {
      if (message === null) router.replace("/");
      else {
        setError(message);
        setBusy(false);
        router.replace("/login");
      }
    });
  }, [router]);

  const onSignIn = () => {
    setBusy(true);
    setError(null);
    void signInWithGoogle(window.location.origin).then((message) => {
      if (message !== null) {
        setError(message);
        setBusy(false);
      }
    });
  };

  return (
    <LoginView
      session={session}
      runs={runs}
      signIn={{ available: SIGN_IN_AVAILABLE, busy, error, onSignIn, onSignOut: () => void signOutAndReload() }}
    />
  );
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
