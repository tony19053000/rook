"use client";

// The small pages (04 §3.2): /runs, /repositories, /counterexamples and /rules. Presentational (local UI
// state only); the data hooks live in PageClients.tsx so these render in tests.

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "./AppShell";
import { ErrorCard } from "./ErrorCard";
import { RunsList } from "./RunsList";
import type { RepoOption, RunSummary } from "@/lib/api";
import { errorView, pickerGroups, repoKey, repoMeta, shellProps } from "@/lib/pages";
import { clean } from "@/lib/safeText";
import type { Session } from "@/lib/session";

type RunsData = { runs: RunSummary[]; loading: boolean; error: unknown; refresh?: () => void };

function Title({ children, sub }: { children: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 pb-3">
      <h1 className="font-serif text-[26px] font-normal tracking-tight">{children}</h1>
      {sub && <p className="text-muted">{sub}</p>}
    </div>
  );
}

export function RunsPageView({ session, runs, now }: { session: Session; runs: RunsData; now?: number }) {
  return (
    <AppShell {...shellProps(session, runs)} active="runs">
      <Title sub="Every run is saved. Open one to see its rules, counterexamples and fixes.">Runs</Title>
      <RunsList runs={runs.runs} loading={runs.loading} error={runs.error} onRetry={runs.refresh} now={now} />
    </AppShell>
  );
}

export function CounterexamplesView({ session, runs, now }: { session: Session; runs: RunsData; now?: number }) {
  const withResult = runs.runs.filter((r) => r.result !== null);
  return (
    <AppShell {...shellProps(session, runs)} active="counterexamples">
      <Title sub="Runs where Roook broke a rule. Open one for the steps, the fix and the verification.">Counterexamples</Title>
      <RunsList
        runs={withResult}
        loading={runs.loading}
        error={runs.error}
        onRetry={runs.refresh}
        now={now}
        empty="No counterexamples yet. When a run breaks a rule, it shows up here."
      />
    </AppShell>
  );
}

export function RulesView({ session, runs }: { session: Session; runs: RunsData }) {
  return (
    <AppShell {...shellProps(session, runs)} active="rules">
      <Title>Rules</Title>
      <p className="text-muted">
        Rules are drafted, checked and approved inside each run, and saved with the repo in <code className="font-mono">rook/rook.yaml</code>. Open a{" "}
        <Link href="/runs" className="text-link underline-offset-2 hover:underline">
          run
        </Link>{" "}
        to see its rules.
      </p>
    </AppShell>
  );
}

export interface RepositoriesViewProps {
  session: Session;
  runs: RunsData;
  repos: RepoOption[];
  loading: boolean;
  error: unknown;
  onRetry?: () => void;
  /** "Connect GitHub" for a signed-in user without GitHub: resolves to an error message, or null. */
  connectGithub?: () => Promise<string | null>;
}

function RepoList({ repos }: { repos: RepoOption[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {repos.map((repo) => (
        <li key={repoKey(repo)} data-repo={repoKey(repo)} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3">
          <span className="font-medium">{clean(repo.name)}</span>
          <span className="text-[12.5px] text-muted">{repoMeta(repo)}</span>
        </li>
      ))}
    </ul>
  );
}

export function RepositoriesView({ session, runs, repos, loading, error, onRetry, connectGithub }: RepositoriesViewProps) {
  const groups = pickerGroups(repos, session);
  const [connectError, setConnectError] = useState<string | null>(null);
  const onConnect = connectGithub
    ? () => {
        setConnectError(null);
        void connectGithub().then(setConnectError);
      }
    : undefined;
  let body;
  if (loading) body = <div className="h-14 animate-pulse rounded-xl border border-line bg-surface" aria-busy="true" />;
  else if (error !== null && error !== undefined) body = <ErrorCard view={errorView(error, "repos")} onRetry={onRetry} />;
  else
    body = (
      <div className="flex flex-col gap-4">
        {groups.github !== null && (
          <section className="flex flex-col gap-2">
            <h2 className="text-[13px] font-semibold text-muted">Your GitHub repositories</h2>
            {groups.github.length === 0 ? <p className="text-muted">No repositories shared with Roook yet.</p> : <RepoList repos={groups.github} />}
          </section>
        )}
        {groups.connectGithub && (
          <section className="flex flex-col items-start gap-2" data-connect-github>
            <h2 className="text-[13px] font-semibold text-muted">Your GitHub repositories</h2>
            <button type="button" onClick={onConnect} disabled={!onConnect} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-[13.5px] font-medium hover:bg-hover disabled:opacity-50">
              Connect GitHub
            </button>
            {connectError !== null && (
              <p role="alert" className="text-[12.5px] text-bad">
                {clean(connectError)}
              </p>
            )}
          </section>
        )}
        <section className="flex flex-col gap-2">
          <h2 className="text-[13px] font-semibold text-muted">Example repositories</h2>
          {groups.demo.length === 0 ? <p className="text-muted">No example repositories on this server.</p> : <RepoList repos={groups.demo} />}
        </section>
        {session.kind === "guest" && (
          <p className="text-[13px] text-muted">
            <Link href="/login" className="text-link underline-offset-2 hover:underline">
              Sign in
            </Link>{" "}
            to connect GitHub, or run Roook on any repo with the CLI.
          </p>
        )}
        <section className="flex flex-col gap-1 border-t border-line pt-4 text-[13px] text-muted" data-add-to-ci>
          <h2 className="text-[13px] font-semibold text-muted">Add to CI</h2>
          <p>
            Run Roook on every pull request with <code className="font-mono">rook run --ci</code>.
          </p>
        </section>
      </div>
    );
  return (
    <AppShell {...shellProps(session, runs)} active="repositories">
      <Title sub="The hosted server runs the example repositories. Use the CLI for your own.">Repositories</Title>
      {body}
    </AppShell>
  );
}
