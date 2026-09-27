"use client";

// Home (04 §3.2 `/`): the greeting and the composer with the repo picker. Choosing a repo and sending creates
// a run (POST /runs) and opens `/runs/[id]`. Guests see only the demo repos and get "Try the demo". A signed-in
// user whose server said `can_run_github` (GET /me) runs their own GitHub repos the same way (ROOK-041);
// otherwise a GitHub repo gets the `rook run` CLI hint.

import { useCallback, useState } from "react";
import { AppShell } from "./AppShell";
import { Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { RepoPicker } from "./RepoPicker";
import { Note } from "./cards/ui";
import type { ApiClient, RepoOption, RunSummary } from "@/lib/api";
import {
  DEFAULT_REQUEST,
  errorView,
  HOSTED_GITHUB_NOTE,
  newRunBody,
  pickerGroups,
  repoKey,
  shellProps,
  startRun,
  type ErrorView,
} from "@/lib/pages";
import { clean } from "@/lib/safeText";
import { canRunGithub, type Session } from "@/lib/session";
import type { ReposView } from "@/lib/useShell";

/** What Rook is, in one line (also the page description in app/layout.tsx). */
export const TAGLINE =
  "Rook finds the smallest sequence of actions that breaks a business rule, proves it on the real app, and verifies the fix.";

const STEPS = ["You approve the business rules Rook reads from the code", "The engine searches and replays the shortest break", "Bob writes a fix; the engine verifies it before shipping"];

export interface HomeViewProps {
  api: Pick<ApiClient, "createRun">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  repos: Pick<ReposView, "repos" | "loading" | "error" | "retry">;
  navigate: (href: string) => void;
  /** "Connect GitHub" (ROOK-031): goes to GitHub's install page; resolves to an error message, or null. */
  connectGithub?: () => Promise<string | null>;
  /** The repo picked on first render (tests; nothing by default). */
  defaultSelected?: RepoOption | null;
}

export function HomeView({ api, session, runs, repos, navigate, connectGithub, defaultSelected = null }: HomeViewProps) {
  const [selected, setSelected] = useState<RepoOption | null>(defaultSelected);
  const [auto, setAuto] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<ErrorView | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState(DEFAULT_REQUEST);

  const reposError = repos.error === null || repos.error === undefined ? null : errorView(repos.error, "repos");
  const groups = pickerGroups(repos.repos, session);
  const guest = session.kind === "guest";
  const hostedGithub = canRunGithub(session);

  const start = useCallback(
    async (repo: RepoOption | null, text: string): Promise<boolean> => {
      const request = text || DEFAULT_REQUEST;
      const body = newRunBody(repo, request, auto, hostedGithub);
      if ("error" in body) {
        setHint(body.error);
        return false;
      }
      setHint(null);
      setCreateError(null);
      setLastRequest(request);
      setCreating(true);
      const outcome = await startRun(api, repo, request, auto, hostedGithub);
      if (outcome.kind === "started") {
        navigate(outcome.href);
        return true;
      }
      if (outcome.kind === "hint") setHint(outcome.message);
      else setCreateError(outcome.error);
      setCreating(false);
      return false;
    },
    [api, auto, navigate, hostedGithub],
  );

  // "Try the demo" uses the demo picked in the picker or the chips, else the first one the server lists.
  const demoPick = selected !== null && selected.kind === "demo" ? selected : (groups.demo[0] ?? null);
  const tryDemo = () => {
    const repo = demoPick;
    if (repo === null) return;
    setSelected(repo);
    void start(repo, DEFAULT_REQUEST);
  };

  const composer = (
    <div className="flex flex-col gap-1.5">
      {hint !== null && (
        <div className="mx-auto w-full max-w-[760px] px-1">
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
          if (selected === null) {
            setHint("Pick a repository first.");
            return false;
          }
          void start(selected, text);
        }}
        allowEmpty
        disabled={creating}
        placeholder={creating ? "Starting the run…" : 'Describe what to check, or "find bugs"'}
        auto={auto}
        onAutoChange={setAuto}
        picker={
          <RepoPicker
            groups={groups}
            selected={selected}
            onSelect={(repo) => {
              setSelected(repo);
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

  return (
    <AppShell {...shellProps(session, runs)} active="home" composer={composer}>
      <div className="flex flex-col items-center gap-3 pt-10 text-center min-[820px]:pt-16">
        <div className="flex items-center justify-center gap-3">
          <span aria-hidden className="size-7 flex-none rounded-full bg-accent" />
          <h1 className="font-serif text-[26px] font-normal leading-tight tracking-tight min-[480px]:text-[30px]">What should we try to break today?</h1>
        </div>
        <p className="max-w-[560px] text-[15px] text-ink" data-tagline>
          {TAGLINE}
        </p>
        <p className="text-muted">Pick a repository, then describe what to check, or just say &quot;find bugs&quot;.</p>
      </div>
      <ol className="mx-auto mt-3 hidden w-full max-w-[640px] grid-cols-3 gap-2 text-[13px] text-muted min-[560px]:grid" data-steps>
        {STEPS.map((step, i) => (
          <li key={step} className="flex items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2">
            <span className="num flex-none font-semibold text-accent">{i + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      {guest && (
        <div className="mt-5 flex flex-col items-center gap-2.5 text-center text-[13.5px] text-muted" data-guest>
          <button
            type="button"
            onClick={tryDemo}
            disabled={creating || demoPick === null}
            className="rounded-lg border border-accent bg-accent px-5 py-2 text-[14.5px] font-semibold text-accent-ink shadow-sm hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creating
              ? "Starting…"
              : demoPick !== null
                ? `Try the demo on ${clean(demoPick.name)} →`
                : repos.loading
                  ? "Loading the demos…"
                  : "Try the demo"}
          </button>
          <p className="max-w-[560px]">
            No sign-in needed: you&apos;re a guest, so only the demo repositories run (a few runs a day). Questions answer
            themselves after a short countdown.
          </p>
        </div>
      )}
      {groups.demo.length > 0 && (
        <div className="mt-3 flex flex-col items-center gap-1.5" data-demo-chips>
          <span className="text-[11px] font-semibold uppercase tracking-[.08em] text-faint">Demo repositories</span>
          <div className="flex flex-wrap justify-center gap-1.5">
            {groups.demo.map((repo) => {
              const on = selected !== null && repoKey(selected) === repoKey(repo);
              return (
                <button
                  key={repoKey(repo)}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    setSelected(repo);
                    setHint(null);
                  }}
                  className={`rounded-full border px-3 py-1 text-[13px] hover:bg-hover ${on ? "border-accent text-ink" : "border-line text-muted"}`}
                >
                  {clean(repo.name)}
                  {repo.language && <span className="text-faint"> · {clean(repo.language)}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {createError !== null && (
        <div className="mt-4">
          <ErrorCard view={createError} onRetry={() => void start(selected, lastRequest)} />
        </div>
      )}
      {reposError !== null && !repos.loading && (
        <div className="mt-4">
          <ErrorCard view={reposError} onRetry={repos.retry} />
        </div>
      )}
    </AppShell>
  );
}
