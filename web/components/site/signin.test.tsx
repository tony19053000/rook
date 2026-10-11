// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/(site)/login/page";
import SiteLayout from "@/app/(site)/layout";
import { SignInPanel } from "./SignInPanel";
import { loginCopy } from "@/content/login";
import { canStart, initialSignInState, signInReducer, type SignInState } from "@/lib/signIn";

// 06 §7 / §9: Google sign-in starts only on a click. lib/session is mocked (the real oauthReturn is kept), so a
// call is counted, never made.
const mocks = vi.hoisted(() => ({
  signIn: vi.fn<(origin: string) => Promise<string | null>>(),
  complete: vi.fn<(code: string) => Promise<string | null>>(),
  router: { replace: vi.fn(), push: vi.fn() },
}));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/session")>()),
  SIGN_IN_AVAILABLE: true,
  signInWithGoogle: mocks.signIn,
  completeSignIn: mocks.complete,
}));

const CODE = "34e770dd-9ff9-416c-87fa-43b31d7ef225";
const fetchSpy = vi.fn();

function visit(path: string) {
  window.history.replaceState(null, "", path);
  return render(
    <SiteLayout>
      <LoginPage />
    </SiteLayout>,
  );
}

const google = () => screen.getByRole("button", { name: loginCopy.google });

beforeEach(() => {
  mocks.signIn.mockReset();
  mocks.complete.mockReset();
  mocks.router.replace.mockReset();
  fetchSpy.mockReset();
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("the sign-in state machine (lib/signIn.ts)", () => {
  const idle: SignInState = { kind: "idle" };

  it("starts idle when configured, unavailable when not", () => {
    expect(initialSignInState(true)).toEqual(idle);
    expect(initialSignInState(false)).toEqual({ kind: "unavailable" });
  });

  it("idle → opening → failed → opening (Retry)", () => {
    const opening = signInReducer(idle, { type: "start" });
    expect(opening).toEqual({ kind: "opening" });
    const failed = signInReducer(opening, { type: "failed", reason: "nope" });
    expect(failed).toEqual({ kind: "failed", reason: "nope" });
    expect(signInReducer(failed, { type: "start" })).toEqual({ kind: "opening" });
  });

  it("a second start while opening or completing changes nothing", () => {
    expect(signInReducer({ kind: "opening" }, { type: "start" })).toEqual({ kind: "opening" });
    expect(signInReducer({ kind: "completing" }, { type: "start" })).toEqual({ kind: "completing" });
    expect(canStart({ kind: "opening" })).toBe(false);
    expect(canStart({ kind: "completing" })).toBe(false);
    expect(canStart(idle)).toBe(true);
    expect(canStart({ kind: "failed", reason: "x" })).toBe(true);
  });

  it("back from Google: idle → completing → failed", () => {
    const completing = signInReducer(idle, { type: "returned" });
    expect(completing).toEqual({ kind: "completing" });
    expect(signInReducer(completing, { type: "failed", reason: "r" })).toEqual({ kind: "failed", reason: "r" });
  });

  it("unavailable never leaves (no button can appear)", () => {
    const off: SignInState = { kind: "unavailable" };
    for (const event of [{ type: "start" }, { type: "returned" }, { type: "failed", reason: "x" }] as const) {
      expect(signInReducer(off, event)).toBe(off);
    }
    expect(canStart(off)).toBe(false);
  });
});

describe("/login (06 §7)", () => {
  it("a plain visit calls nothing: no sign-in, no code exchange, no fetch", () => {
    visit("/login");
    expect(google()).toBeTruthy();
    expect(mocks.signIn).not.toHaveBeenCalled();
    expect(mocks.complete).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(mocks.router.replace).not.toHaveBeenCalled();
  });

  it("?code= finishes the sign-in once without starting a new one, then goes to /app", async () => {
    mocks.complete.mockResolvedValue(null);
    visit(`/login?code=${CODE}`);
    expect(screen.getByRole("status").textContent).toBe(loginCopy.completing);
    expect(screen.queryByRole("button", { name: loginCopy.google })).toBeNull();
    await waitFor(() => expect(mocks.router.replace).toHaveBeenCalledWith("/app"));
    expect(mocks.complete).toHaveBeenCalledTimes(1);
    expect(mocks.complete).toHaveBeenCalledWith(CODE);
    expect(mocks.signIn).not.toHaveBeenCalled();
  });

  it("?code= that fails shows the reason and Retry, and cleans the URL", async () => {
    mocks.complete.mockResolvedValue("Sign-in did not complete. Try again.");
    visit(`/login?code=${CODE}`);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("Sign-in did not complete. Try again.");
    expect(screen.getByRole("button", { name: loginCopy.retry })).toBeTruthy();
    expect(mocks.router.replace).toHaveBeenCalledWith("/login");
    expect(mocks.signIn).not.toHaveBeenCalled();
  });

  it("?error= shows a friendly reason (not the provider's text) and Retry, without starting sign-in", () => {
    visit("/login?error=access_denied&error_description=%3Cb%3Eevil%3C%2Fb%3E");
    expect(screen.getByRole("alert").textContent).toBe(loginCopy.cancelled);
    expect(screen.getByRole("button", { name: loginCopy.retry })).toBeTruthy();
    expect(mocks.router.replace).toHaveBeenCalledWith("/login");
    expect(mocks.signIn).not.toHaveBeenCalled();
    expect(mocks.complete).not.toHaveBeenCalled();
  });

  it("a click starts sign-in exactly once; the button is disabled and says Opening Google…", () => {
    mocks.signIn.mockReturnValue(new Promise(() => undefined)); // the browser is leaving for Google
    visit("/login");
    fireEvent.click(google());
    expect(mocks.signIn).toHaveBeenCalledTimes(1);
    expect(mocks.signIn).toHaveBeenCalledWith(window.location.origin);
    const busy = screen.getByRole("button", { name: loginCopy.opening }) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    fireEvent.click(busy);
    expect(mocks.signIn).toHaveBeenCalledTimes(1);
  });

  it("a double click in one tick (before React re-renders) still starts only one sign-in", () => {
    mocks.signIn.mockReturnValue(new Promise(() => undefined));
    visit("/login");
    const button = google();
    act(() => {
      button.click();
      button.click();
    });
    expect(mocks.signIn).toHaveBeenCalledTimes(1);
  });

  it("failed shows the reason and Retry; Retry starts sign-in again", async () => {
    mocks.signIn.mockResolvedValue("Could not start Google sign-in. Try again.");
    visit("/login");
    fireEvent.click(google());
    expect((await screen.findByRole("alert")).textContent).toBe("Could not start Google sign-in. Try again.");
    fireEvent.click(screen.getByRole("button", { name: loginCopy.retry }));
    expect(mocks.signIn).toHaveBeenCalledTimes(2);
  });

  it("not configured: a plain message and the demo link, and no button at all", () => {
    render(<SignInPanel available={false} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText(loginCopy.unavailable)).toBeTruthy();
    expect(screen.getByRole("link", { name: loginCopy.demo.label }).getAttribute("href")).toBe("/app");
    expect(mocks.signIn).not.toHaveBeenCalled();
  });

  it("not configured even when Google sends a code back: still no button, nothing to retry", () => {
    mocks.complete.mockResolvedValue("Google sign-in is not configured on this site.");
    window.history.replaceState(null, "", `/login?code=${CODE}`);
    render(<SignInPanel available={false} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("explains in <noscript> that sign-in needs JavaScript", () => {
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).toContain(`<noscript>`);
    expect(html).toContain(loginCopy.noscript);
  });
});
