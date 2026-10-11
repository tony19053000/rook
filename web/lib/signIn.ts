// The /login state machine (06 §7). Pure, so it is unit-tested; components/site/SignInPanel.tsx runs it.
//
//   unavailable                      Google sign-in is not configured: no button at all, ever
//   idle      --start-->    opening  the click; the button is disabled while Google opens
//   opening   --failed-->   failed   signInWithGoogle returned an error (it navigates away on success)
//   failed    --start-->    opening  Retry
//   idle      --returned--> completing   back from Google with ?code=: finishing the sign-in already started
//   completing --failed-->  failed
// Every other event leaves the state as it is (e.g. a second click while opening starts nothing).

export type SignInState =
  | { kind: "unavailable" }
  | { kind: "idle" }
  | { kind: "opening" }
  | { kind: "completing" }
  | { kind: "failed"; reason: string };

export type SignInEvent = { type: "start" } | { type: "returned" } | { type: "failed"; reason: string };

export function initialSignInState(available: boolean): SignInState {
  return available ? { kind: "idle" } : { kind: "unavailable" };
}

export function signInReducer(state: SignInState, event: SignInEvent): SignInState {
  switch (event.type) {
    case "start":
      return state.kind === "idle" || state.kind === "failed" ? { kind: "opening" } : state;
    case "returned":
      return state.kind === "idle" ? { kind: "completing" } : state;
    case "failed":
      return state.kind === "unavailable" ? state : { kind: "failed", reason: event.reason };
  }
}

/** Whether a click may start Google sign-in now. */
export function canStart(state: SignInState): boolean {
  return state.kind === "idle" || state.kind === "failed";
}
