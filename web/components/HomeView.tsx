"use client";

// Home (04 §3.2 `/app`). A short greeting near the top, the rest of the main column empty, and the composer at
// the bottom with the IBM Bob chip and the repo picker. Signed out it is the same workspace: the first example
// repo is already picked, so a guest only has to press Send, and signing in lives on its own page (`/login`,
// reached from the sidebar's Sign in button), never inside the chat column. Sending creates a run (POST /runs)
// and opens `/runs/[id]`; a GitHub repo runs on the server only when GET /me said `can_run_github` (ROOK-041),
// otherwise it gets the `rook run` CLI hint.

import { useCallback, useState } from "react";
import { AgentSprite } from "./AgentSprite";
import { AppShell } from "./AppShell";
import { Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { RepoPicker } from "./RepoPicker";
import { Note } from "./cards/ui";
import { MASCOT } from "@/lib/agents";
import type { ApiClient, RepoOption, RunSummary } from "@/lib/api";
import {
  bobModeLabel,
  DEFAULT_REQUEST,
  errorView,
  firstName,
  HOSTED_GITHUB_NOTE,
  OWN_REPOS_NOTE,
  pickerGroups,
  shellProps,
  startRun,
  type ErrorView,
} from "@/lib/pages";
import { clean } from "@/lib/safeText";
import { canRunGithub, type Session } from "@/lib/session";
import type { ReposView } from "@/lib/useShell";

export interface HomeViewProps {
  api: Pick<ApiClient, "createRun">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  repos: Pick<ReposView, "repos" | "loading" | "error" | "retry">;
  navigate: (href: string) => void;
  /** "Connect GitHub" (ROOK-031): goes to GitHub's install page; resolves to an error message, or null. */
  connectGithub?: () => Promise<string | null>;
  /** The repo picked on first render (tests; by default nothing, or the first example for a guest). */
  defaultSelected?: RepoOption | null;
  /** The server's Bob mode from GET /health, or null while unknown: example repos are recorded only on `replay`. */
  bobMode?: string | null;
}

export function HomeView({ api, session, runs, repos, navigate, connectGithub, defaultSelected = null, bobMode = null }: HomeViewProps) {
  const [picked, setPicked] = useState<RepoOption | null>(defaultSelected);
  const [auto, setAuto] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<ErrorView | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState(DEFAULT_REQUEST);

  const reposError = repos.error === null || repos.error === undefined ? null : errorView(repos.error, "repos");
  const groups = pickerGroups(repos.repos, session);
  const guest = session.kind === "guest";
  const hostedGithub = canRunGithub(session);
  // A guest starts with the first example picked, so the composer is ready to send.
  const selected = picked ?? (guest ? (groups.demo[0] ?? null) : null);

  const start = useCallback(
    async (repo: RepoOption, text: string): Promise<void> => {
      const request = text || DEFAULT_REQUEST;
      setHint(null);
      setCreateError(null);
      setLastRequest(request);
      setCreating(true);
      const outcome = await startRun(api, repo, request, auto, hostedGithub);
      if (outcome.kind === "started") {
        navigate(outcome.href);
        return;
      }
      if (outcome.kind === "hint") setHint(outcome.message);
      else setCreateError(outcome.error);
      setCreating(false);
    },
    [api, auto, navigate, hostedGithub],
  );

  // AppShell pads the composer by 20px; -mx-1 makes the 16px mobile gutter of 04 §3.2.
  const composer = (
    <div className="flex flex-col gap-1.5 max-md:-mx-1">
      {hint !== null && (
        <div className="mx-auto w-full max-w-[760px] px-1" data-hint>
          <Note tone="warn">{clean(hint)}</Note>
        </div>
      )}
      {hint === null && hostedGithub && selected !== null && selected.kind === "github" && (
        <div className="mx-auto w-full max-w-[760px] px-1" data-hosted-note>
          <Note tone="muted">{HOSTED_GITHUB_NOTE}</Note>
        </div>
      )}
      <Composer
        onSend={(text) => {
          if (selected === null) return false;
          void start(selected, text);
        }}
        allowEmpty
        disabled={creating}
        canSend={selected !== null}
        placeholder={creating ? "Starting the run…" : undefined}
        auto={auto}
        onAutoChange={setAuto}
        status={bobModeLabel(selected, bobMode)}
        picker={
          <RepoPicker
            groups={groups}
            selected={selected}
            onSelect={(repo) => {
              setPicked(repo);
              setHint(null);
            }}
            onConnectGithub={
              connectGithub &&
              (() => {
                setHint(null);
                void connectGithub().then((message) => {
                  if (message !== null) setHint(message);
                });
              })
            }
            loading={repos.loading}
            error={reposError?.message ?? null}
            onRetry={repos.retry}
          />
        }
      />
    </div>
  );

  const name = firstName(session);

  return (
    <AppShell {...shellProps(session, runs)} active="home" composer={composer}>
      <div className="flex items-center justify-center gap-2.5 pt-[10vh] text-center" data-greeting>
        <AgentSprite look={MASCOT} px={2} animate={false} />
        <h1 className="font-serif text-[22px] font-normal leading-tight tracking-tight">
          {name ? `What should Rook check next, ${name}?` : "What should Rook check next?"}
        </h1>
      </div>
      {!guest && !hostedGithub && (
        <p className="mx-auto max-w-[520px] text-center text-[13px] text-muted" data-own-repos-note>
          {OWN_REPOS_NOTE} Pick one of your repos below to get its <code className="font-mono">rook run</code> command, or pick an example repo to
          run here.
        </p>
      )}
      {createError !== null && (
        <div className="mt-6">
          <ErrorCard view={createError} onRetry={selected === null ? undefined : () => void start(selected, lastRequest)} />
        </div>
      )}
      {reposError !== null && !repos.loading && (
        <div className="mt-6">
          <ErrorCard view={reposError} onRetry={repos.retry} />
        </div>
      )}
    </AppShell>
  );
}
