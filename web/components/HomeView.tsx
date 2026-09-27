"use client";

// Home (04 §3.2 `/`): the greeting and the composer with the repo picker. Choosing a repo and sending creates
// a run (POST /runs) and opens `/runs/[id]`. Guests see only the demo repos and get "Try the demo".

import { useCallback, useState } from "react";
import { AppShell } from "./AppShell";
import { Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { RepoPicker } from "./RepoPicker";
import { Note } from "./cards/ui";
import type { ApiClient, RepoOption, RunSummary } from "@/lib/api";
import { DEFAULT_REQUEST, errorView, newRunBody, pickerGroups, runHref, shellProps, type ErrorView } from "@/lib/pages";
import type { Session } from "@/lib/session";
import type { ReposView } from "@/lib/useShell";

export interface HomeViewProps {
  api: Pick<ApiClient, "createRun">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  repos: Pick<ReposView, "repos" | "loading" | "error" | "retry">;
  navigate: (href: string) => void;
  /** "Connect GitHub" (ROOK-031): goes to GitHub's install page; resolves to an error message, or null. */
  connectGithub?: () => Promise<string | null>;
}

export function HomeView({ api, session, runs, repos, navigate, connectGithub }: HomeViewProps) {
  const [selected, setSelected] = useState<RepoOption | null>(null);
  const [auto, setAuto] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<ErrorView | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState(DEFAULT_REQUEST);

  const reposError = repos.error === null || repos.error === undefined ? null : errorView(repos.error, "repos");
  const groups = pickerGroups(repos.repos, session);
  const guest = session.kind === "guest";

  const start = useCallback(
    async (repo: RepoOption | null, text: string): Promise<boolean> => {
      const checked = newRunBody(repo, text || DEFAULT_REQUEST, auto);
      if ("error" in checked) {
        setHint(checked.error);
        return false;
      }
      setHint(null);
      setCreateError(null);
      setLastRequest(text || DEFAULT_REQUEST);
      setCreating(true);
      try {
        const { run_id } = await api.createRun(checked.body);
        navigate(runHref(run_id));
        return true;
      } catch (e) {
        setCreateError(errorView(e, "create"));
        setCreating(false);
        return false;
      }
    },
    [api, auto, navigate],
  );

  const tryDemo = () => {
    const repo = groups.demo[0] ?? null;
    if (repo === null) return;
    setSelected(repo);
    void start(repo, DEFAULT_REQUEST);
  };

  const composer = (
    <div className="flex flex-col gap-1.5">
      {hint !== null && (
        <div className="mx-auto w-full max-w-[760px] px-1">
          <Note tone="warn">{hint}</Note>
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
      <div className="flex items-center justify-center gap-3 pt-16">
        <span aria-hidden className="size-7 rounded-full bg-accent" />
        <h1 className="font-serif text-[30px] font-normal tracking-tight">What should we try to break today?</h1>
      </div>
      <p className="text-center text-muted">Pick a repository, then describe what to check, or just say &quot;find bugs&quot;.</p>
      {guest && (
        <div className="mt-4 flex flex-col items-center gap-2 text-center text-[13.5px] text-muted" data-guest>
          <p>You&apos;re trying Rook as a guest: demo repositories only, a few runs a day. Questions answer themselves after a short countdown.</p>
          <button
            type="button"
            onClick={tryDemo}
            disabled={creating || groups.demo.length === 0}
            className="rounded-lg border border-accent bg-accent px-3.5 py-1.5 text-[13.5px] font-medium text-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creating ? "Starting…" : "Try the demo"}
          </button>
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
