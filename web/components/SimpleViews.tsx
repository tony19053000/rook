// The small pages (04 §3.2): /login, /runs, /repositories, /counterexamples and /rules. Presentational only;
// the hooks live in PageClients.tsx so these render in tests.

import Link from "next/link";
import { AppShell } from "./AppShell";
import { ErrorCard } from "./ErrorCard";
import { RunsList } from "./RunsList";
import type { RepoOption, RunSummary } from "@/lib/api";
import { errorView, pickerGroups, repoKey, repoMeta, shellProps } from "@/lib/pages";
import { clean } from "@/lib/safeText";
import { SIGN_IN_AVAILABLE, type Session } from "@/lib/session";

type RunsData = { runs: RunSummary[]; loading: boolean; error: unknown; refresh?: () => void };

function Title({ children, sub }: { children: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 pb-3">
      <h1 className="font-serif text-[26px] font-normal tracking-tight">{children}</h1>
      {sub && <p className="text-muted">{sub}</p>}
    </div>
  );
}

export function LoginView({ session, runs }: { session: Session; runs: RunsData }) {
  return (
    <AppShell {...shellProps(session, runs)} active="login">
      <div className="mx-auto flex w-full max-w-[380px] flex-col items-center gap-3 pt-16 text-center">
        <span aria-hidden className="size-8 rounded-full bg-accent" />
        <h1 className="font-serif text-[28px] font-normal tracking-tight">Sign in to Rook</h1>
        <p className="text-muted">Sign in to keep your runs across devices and connect GitHub.</p>
        <button
          type="button"
          disabled={!SIGN_IN_AVAILABLE}
          aria-describedby="signin-note"
          className="w-full rounded-lg border border-line bg-surface px-3.5 py-2 font-medium hover:bg-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Continue with Google
        </button>
        {!SIGN_IN_AVAILABLE && (
          <p id="signin-note" className="text-[12.5px] text-muted">
            Google sign-in is coming soon. You can use everything below as a guest.
          </p>
        )}
        <Link href="/" className="w-full rounded-lg border border-accent bg-accent px-3.5 py-2 font-medium text-accent-ink" data-try-demo>
          Try the demo without signing in
        </Link>
        <p className="text-[12.5px] text-muted">
          Guests can run the demo repositories a few times a day. To run on your own repos, install the CLI:{" "}
          <code className="font-mono">uv tool install rook-cli</code>
        </p>
      </div>
    </AppShell>
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
      <Title sub="Runs where Rook broke a rule. Open one for the steps, the fix and the verification.">Counterexamples</Title>
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

export function RepositoriesView({ session, runs, repos, loading, error, onRetry }: RepositoriesViewProps) {
  const groups = pickerGroups(repos, session);
  let body;
  if (loading) body = <div className="h-14 animate-pulse rounded-xl border border-line bg-surface" aria-busy="true" />;
  else if (error !== null && error !== undefined) body = <ErrorCard view={errorView(error, "repos")} onRetry={onRetry} />;
  else
    body = (
      <div className="flex flex-col gap-4">
        {groups.github !== null && (
          <section className="flex flex-col gap-2">
            <h2 className="text-[13px] font-semibold text-muted">Your GitHub repositories</h2>
            {groups.github.length === 0 ? <p className="text-muted">No repositories shared with Rook yet.</p> : <RepoList repos={groups.github} />}
          </section>
        )}
        <section className="flex flex-col gap-2">
          <h2 className="text-[13px] font-semibold text-muted">Demo repositories</h2>
          {groups.demo.length === 0 ? <p className="text-muted">No demo repositories on this server.</p> : <RepoList repos={groups.demo} />}
        </section>
        {session.kind === "guest" && (
          <p className="text-[13px] text-muted">
            <Link href="/login" className="text-link underline-offset-2 hover:underline">
              Sign in
            </Link>{" "}
            to connect GitHub, or run Rook on any repo with the CLI.
          </p>
        )}
      </div>
    );
  return (
    <AppShell {...shellProps(session, runs)} active="repositories">
      <Title sub="The hosted server runs the demo repositories. Use the CLI for your own.">Repositories</Title>
      {body}
    </AppShell>
  );
}
