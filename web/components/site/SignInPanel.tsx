"use client";

// The /login sign-in control (06 §7), driven by the state machine in lib/signIn.ts. Google sign-in starts only on
// a click. Back from Google, `?code=` finishes the sign-in the user started (then /app) and `?error=` shows the
// failure; either way the one-time query leaves the address bar. Nothing here calls the Rook API. With JS off the
// Google button is hidden by a <noscript> style, so only the note shows (no dead button).

import { useRouter } from "next/navigation";
import { useEffect, useReducer, useRef } from "react";
import { Button, ButtonLink } from "./Button";
import { completeSignIn, oauthReturn, SIGN_IN_AVAILABLE, signInWithGoogle } from "@/lib/session";
import { canStart, initialSignInState, signInReducer } from "@/lib/signIn";
import { loginCopy } from "@/content/login";

/** Marks a control that does nothing without JS; the <noscript> style hides it for no-JS visitors (06 §7). */
export const NO_JS_STYLE = "[data-needs-js]{display:none}";

export function SignInPanel({ available = SIGN_IN_AVAILABLE }: { available?: boolean }) {
  const router = useRouter();
  const [state, dispatch] = useReducer(signInReducer, available, initialSignInState);
  // A second click in the same tick, before React re-renders the disabled button, must not start another sign-in.
  const opening = useRef(false);

  useEffect(() => {
    const back = oauthReturn(window.location.search);
    if (back === null) return;
    if ("error" in back) {
      dispatch({ type: "failed", reason: loginCopy.cancelled });
      router.replace("/login");
      return;
    }
    dispatch({ type: "returned" });
    // completeSignIn exchanges each code once, however often this effect runs.
    void completeSignIn(back.code).then((message) => {
      if (message === null) {
        router.replace("/app");
        return;
      }
      dispatch({ type: "failed", reason: message });
      router.replace("/login");
    });
  }, [router]);

  const start = () => {
    if (opening.current || !canStart(state)) return;
    opening.current = true;
    dispatch({ type: "start" });
    void signInWithGoogle(window.location.origin).then((message) => {
      if (message === null) return; // the browser is on its way to Google
      opening.current = false;
      dispatch({ type: "failed", reason: message });
    });
  };

  return (
    <div className="flex flex-col gap-3" data-sign-in-state={state.kind}>
      <noscript>
        <style>{NO_JS_STYLE}</style>
        <p className="rounded-xl border border-site-line bg-site-raised px-4 py-3 text-sm text-site-muted">{loginCopy.noscript}</p>
      </noscript>

      {state.kind === "unavailable" && <p className="text-sm leading-relaxed text-site-muted">{loginCopy.unavailable}</p>}

      {(state.kind === "idle" || state.kind === "opening") && (
        <Button
          data-needs-js=""
          size="lg"
          className="w-full"
          onClick={start}
          disabled={state.kind === "opening"}
          aria-busy={state.kind === "opening" || undefined}
        >
          {state.kind === "opening" ? loginCopy.opening : loginCopy.google}
        </Button>
      )}

      {state.kind === "completing" && (
        <p role="status" className="text-sm text-site-muted">
          {loginCopy.completing}
        </p>
      )}

      {state.kind === "failed" && (
        <>
          <p role="alert" className="rounded-xl border border-site-warn/40 bg-site-warn-soft px-4 py-3 text-sm text-site-warn">
            {state.reason}
          </p>
          <Button size="lg" className="w-full" onClick={start}>
            {loginCopy.retry}
          </Button>
        </>
      )}

      <ButtonLink href={loginCopy.demo.href} variant="secondary" size="lg" className="w-full">
        {loginCopy.demo.label}
      </ButtonLink>
    </div>
  );
}
