"use client";

// The /login sign-in control (06 §7), driven by the state machine in lib/signIn.ts. Google sign-in starts only on
// a click. Back from Google, `?code=` finishes the sign-in the user started (then /app) and `?error=` shows the
// failure; either way the one-time query leaves the address bar. Nothing here calls the Roook API. With JS off the
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

  const configured = state.kind !== "unavailable";
  return (
    <div className="flex flex-col gap-3" data-sign-in-state={state.kind}>
      <noscript>
        <style>{NO_JS_STYLE}</style>
        <p className="rounded-xl border border-site-line bg-site-raised px-4 py-3 text-sm text-site-muted">{loginCopy.noscript}</p>
      </noscript>

      {state.kind === "unavailable" && (
        <p className="rounded-xl border border-site-line bg-site-raised px-4 py-3 text-sm leading-relaxed text-site-muted">{loginCopy.unavailable}</p>
      )}

      {(state.kind === "idle" || state.kind === "opening") && (
        <Button
          data-needs-js=""
          size="lg"
          className="w-full"
          onClick={start}
          disabled={state.kind === "opening"}
          aria-busy={state.kind === "opening" || undefined}
        >
          <GoogleMark />
          {state.kind === "opening" ? loginCopy.opening : loginCopy.google}
        </Button>
      )}

      {state.kind === "completing" && (
        <p role="status" className="py-3 text-center text-sm text-site-muted">
          {loginCopy.completing}
        </p>
      )}

      {state.kind === "failed" && (
        <>
          <p role="alert" className="rounded-xl border border-site-warn/35 bg-site-warn-soft px-4 py-3 text-sm leading-relaxed text-site-warn">
            {state.reason}
          </p>
          <Button size="lg" className="w-full" onClick={start}>
            <GoogleMark />
            {loginCopy.retry}
          </Button>
        </>
      )}

      {/* Signing in is the page's one action; trying Roook as a guest is a quiet link under it. */}
      <div className={configured ? "mt-1 border-t border-site-line pt-3" : ""}>
        <ButtonLink href={loginCopy.demo.href} variant={configured ? "ghost" : "secondary"} size={configured ? "md" : "lg"} className="w-full">
          {loginCopy.demo.label}
        </ButtonLink>
      </div>
    </div>
  );
}

/** Google's "G" mark, for the sign-in button. */
function GoogleMark() {
  return (
    <svg aria-hidden width="18" height="18" viewBox="0 0 48 48" className="flex-none">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}
