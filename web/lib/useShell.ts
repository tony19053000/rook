"use client";

// Hooks shared by the pages: one API client per page (same-origin by default, 02 §13), the session, and the
// sidebar recents from GET /runs, refreshed while a run is queued or running.

import { useCallback, useEffect, useMemo, useState } from "react";
import { createApiClient, type ApiClient, type RepoOption, type RunSummary } from "./api";
import { apiBase } from "./config";
import { anyActive, RECENTS_POLL_MS } from "./pages";
import { currentSession, getToken, type Session } from "./session";

export function useApi(): ApiClient {
  return useMemo(() => createApiClient({ baseUrl: apiBase(), getToken }), []);
}

export function useSession(): Session {
  return useMemo(() => currentSession(), []);
}

export interface RunsView {
  runs: RunSummary[];
  loading: boolean;
  error: unknown;
  refresh: () => void;
}

/** GET /runs, polled every RECENTS_POLL_MS while any run is active. */
export function useRuns(api: Pick<ApiClient, "listRuns">): RunsView {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    api.listRuns().then(
      (list) => {
        if (cancelled) return;
        setRuns(list);
        setError(null);
        setLoading(false);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(e);
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, tick]);

  const active = anyActive(runs);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(refresh, RECENTS_POLL_MS);
    return () => clearInterval(timer);
  }, [active, refresh]);

  return { runs, loading, error, refresh };
}

export interface ReposView {
  repos: RepoOption[];
  loading: boolean;
  error: unknown;
  retry: () => void;
}

/** GET /repos (demo repos for a guest; GitHub ones too once ROOK-031 is in). */
export function useRepos(api: Pick<ApiClient, "repos">): ReposView {
  const [repos, setRepos] = useState<RepoOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const retry = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.repos().then(
      (list) => {
        if (cancelled) return;
        setRepos(list);
        setError(null);
        setLoading(false);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(e);
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, tick]);

  return { repos, loading, error, retry };
}
