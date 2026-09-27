"use client";

// Home (04 §3.2 `/`). Signed in: a short greeting near the top, the rest of the main column empty, and the
// composer at the bottom with the IBM Bob chip and the repo picker. Signed out: what Rook does, "Sign in with
// Google", and a small "Try an example without signing in" link that starts the first example (judges without
// an account need it). Sending creates a run (POST /runs) and opens `/runs/[id]`; a GitHub repo runs on the
// server only when GET /me said `can_run_github` (ROOK-041), otherwise it gets the `rook run` CLI hint.

import Link from "next/link";
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
  pickerGroups,
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

export const SIGNED_OUT_TITLE = "Find the bug. Prove it. Verify the fix.";

export interface HomeViewProps {
  api: Pick<ApiClient, "createRun">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  repos: Pick<ReposView, "repos" | "loading" | "error" | "retry">;
  navigate: (href: string) => void;
  /** "Connect GitHub" (ROOK-031): goes to GitHub's install page; resolves to an error message, or null. */
  connectGithub?: () => Promise<string | null>;
  /** "Sign in with Google": starts the OAuth redirect; resolves to an error message, or null. Else a /login link. */
  signIn?: () => Promise<string | null>;
  /** The repo picked on first render (tests; nothing by default). */
  defaultSelected?: RepoOption | null;
}

export function HomeView({ api, session, runs, repos, navigate, connectGithub, signIn, defaultSelected = null }: HomeViewProps) {
  const [selected, setSelected] = useState<RepoOption | null>(defaultSelected);
  const [auto, setAuto] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<ErrorView | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState(DEFAULT_REQUEST);
  const [signingIn, setSigningIn] = useState(false);

  const reposError = repos.error === null || repos.error === undefined ? null : errorView(repos.error, "repos");
  const groups = pickerGroups(repos.repos, session);
  const guest = session.kind === "guest";
  const hostedGithub = canRunGithub(session);
  const example = groups.demo[0] ?? null;

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

  const tryExample = () => {
    if (example === null || creating) return;
    setSelected(example);
    void start(example, DEFAULT_REQUEST);
  };

  const onSignIn = () => {
    if (signIn === undefined) return;
    setSigningIn(true);
    setHint(null);
    void signIn().then((message) => {
      if (message !== null) {
        setHint(message);
        setSigningIn(false);
      }
    });
  };

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
        status={bobModeLabel(selected)}
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

  const name = firstName(session);

  return (
    <AppShell {...shellProps(session, runs)} active="home" composer={composer}>
      {guest ? (
        <div className="flex flex-col items-center gap-3 pt-[10vh] text-center" data-signed-out>
          <AgentSprite look={MASCOT} px={3} animate={false} />
          <h1 className="font-serif text-[26px] font-normal leading-tight tracking-tight min-[480px]:text-[30px]">{SIGNED_OUT_TITLE}</h1>
          <p className="max-w-[520px] text-[15px] text-muted" data-tagline>
            {TAGLINE}
          </p>
          <div className="mt-2 flex flex-col items-center gap-2.5">
            {signIn !== undefined ? (
              <button
                type="button"
                onClick={onSignIn}
                disabled={signingIn}
                className="rounded-lg bg-accent px-5 py-2 text-[14.5px] font-medium text-accent-ink shadow-sm hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {signingIn ? "Opening Google…" : "Sign in with Google"}
              </button>
            ) : (
              <Link href="/login" className="rounded-lg bg-accent px-5 py-2 text-[14.5px] font-medium text-accent-ink shadow-sm hover:opacity-90">
                Sign in with Google
              </Link>
            )}
            <button
              type="button"
              onClick={tryExample}
              disabled={creating || example === null}
              data-try-example
              className="text-[13px] text-muted underline decoration-line underline-offset-4 hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              {creating ? "Starting the example…" : "Try an example without signing in"}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center gap-2.5 pt-[10vh] text-center" data-greeting>
          <AgentSprite look={MASCOT} px={2} animate={false} />
          <h1 className="font-serif text-[22px] font-normal leading-tight tracking-tight">
            {name ? `What should Rook check next, ${name}?` : "What should Rook check next?"}
          </h1>
        </div>
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
