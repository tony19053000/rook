"use client";

// React glue: open the run's event stream and fold it through the runStore reducer.

import { useEffect, useReducer, useRef, useState } from "react";
import { initialRunState, reduceRun, type RunState } from "./runStore";
import { openRunStream, type RunStream, type RunStreamOptions, type StreamStatus, type StreamStatusInfo } from "./sse";

export type UseRunStreamOptions = Pick<RunStreamOptions, "baseUrl" | "runId" | "fetch" | "getToken">;

export interface RunStreamView {
  state: RunState;
  status: StreamStatus;
  info: StreamStatusInfo;
  /** Reconnect now instead of waiting for the backoff (the banner's Retry). */
  retry: () => void;
}

export function useRunStream({ baseUrl, runId, fetch, getToken }: UseRunStreamOptions): RunStreamView {
  const [state, dispatch] = useReducer(reduceRun, initialRunState);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [info, setInfo] = useState<StreamStatusInfo>({ attempt: 0 });
  const stream = useRef<RunStream | null>(null);

  useEffect(() => {
    // The reducer drops any seq it has seen, so a remount (React strict mode) can't apply an event twice.
    const s = openRunStream({
      baseUrl,
      runId,
      fetch,
      getToken,
      onEvent: dispatch,
      onStatus: (next, nextInfo) => {
        setStatus(next);
        setInfo(nextInfo);
      },
    });
    stream.current = s;
    return () => s.close();
  }, [baseUrl, runId, fetch, getToken]);

  return { state, status, info, retry: () => stream.current?.reconnectNow() };
}
