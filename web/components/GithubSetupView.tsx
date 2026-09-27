"use client";

// /github/setup (ROOK-031): where GitHub sends the browser after the Rook App is installed. It shows the
// connection being checked by the server, then "GitHub connected" or what went wrong with a way to retry.

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "./AppShell";
import type { RunSummary } from "@/lib/api";
import { shellProps } from "@/lib/pages";
import { clean } from "@/lib/safeText";
import type { Session } from "@/lib/session";

export type GithubSetupStatus = { kind: "working" } | { kind: "done" } | { kind: "error"; message: string };

export interface GithubSetupViewProps {
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  status: GithubSetupStatus;
  connectGithub?: () => Promise<string | null>;
}

export function GithubSetupView({ session, runs, status, connectGithub }: GithubSetupViewProps) {
  const [retryError, setRetryError] = useState<string | null>(null);
  return (
    <AppShell {...shellProps(session, runs)} active="repositories">
      <div className="mx-auto flex w-full max-w-[420px] flex-col items-center gap-3 pt-16 text-center" data-github-setup={status.kind}>
        <span aria-hidden className="size-8 rounded-full bg-accent" />
        {status.kind === "working" && (
          <>
            <h1 className="font-serif text-[28px] font-normal tracking-tight">Connecting GitHub…</h1>
            <p className="text-muted" aria-busy="true">
              Checking the installation with GitHub.
            </p>
          </>
        )}
        {status.kind === "done" && (
          <>
            <h1 className="font-serif text-[28px] font-normal tracking-tight">GitHub connected</h1>
            <p className="text-muted">
              Your shared repositories are in the repo picker. The hosted server runs the demo repositories; run your own with the CLI:{" "}
              <code className="font-mono">rook run owner/name</code>
            </p>
            <Link href="/" className="w-full rounded-lg border border-accent bg-accent px-3.5 py-2 font-medium text-accent-ink">
              Go to Rook
            </Link>
          </>
        )}
        {status.kind === "error" && (
          <>
            <h1 className="font-serif text-[28px] font-normal tracking-tight">GitHub is not connected</h1>
            <p role="alert" className="text-bad">
              {clean(status.message)}
            </p>
            {connectGithub && (
              <button
                type="button"
                onClick={() => {
                  setRetryError(null);
                  void connectGithub().then(setRetryError);
                }}
                className="w-full rounded-lg border border-line bg-surface px-3.5 py-2 font-medium hover:bg-hover"
              >
                Connect GitHub again
              </button>
            )}
            {retryError !== null && <p className="text-[12.5px] text-bad">{clean(retryError)}</p>}
            <Link href="/" className="text-link underline-offset-2 hover:underline">
              Back to Rook
            </Link>
          </>
        )}
      </div>
    </AppShell>
  );
}
