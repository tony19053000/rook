// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/(site)/login/page";
import SiteLayout from "@/app/(site)/layout";
import { loginCopy } from "@/content/login";

// 06 §9: /login makes no API calls on load. Unlike signin.test.tsx, lib/session.ts is real here (no Supabase
// config in tests, so the page shows "not configured").
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const router = { replace: vi.fn(), push: vi.fn() };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("/login on load", () => {
  it.each(["/login", "/login?code=34e770dd-9ff9-416c-87fa-43b31d7ef225", "/login?error=access_denied"])("%s fetches nothing", async (path) => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    window.history.replaceState(null, "", path);
    render(
      <SiteLayout>
        <LoginPage />
      </SiteLayout>,
    );
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByText(loginCopy.unavailable)).toBeTruthy();
    expect(screen.queryByRole("button", { name: loginCopy.google })).toBeNull();
  });
});
