import { existsSync } from "node:fs";
import { describe, expect, it } from "vitest";
import AppHomePage from "./app/page";
import SiteHomePage from "./(site)/page";
import { HomeClient } from "@/components/PageClients";

const exists = (path: string) => existsSync(new URL(path, import.meta.url));

describe("route move (06 §1)", () => {
  it("/app renders the app home (the composer client)", () => {
    expect(AppHomePage().type).toBe(HomeClient);
  });

  it("/ is the site home, not the app", () => {
    expect(exists("./page.tsx")).toBe(false);
    expect(SiteHomePage().type).not.toBe(HomeClient);
  });

  it("the old app routes are still there", () => {
    for (const page of [
      "./runs/page.tsx",
      "./runs/[id]/page.tsx",
      "./rules/page.tsx",
      "./counterexamples/page.tsx",
      "./repositories/page.tsx",
      "./github/setup/page.tsx",
    ]) {
      expect(exists(page), page).toBe(true);
    }
  });

  it("/login, /docs and /security are site pages (/login keeps its URL: the route group adds no segment)", () => {
    for (const page of ["./(site)/login/page.tsx", "./(site)/docs/page.tsx", "./(site)/security/page.tsx"]) expect(exists(page), page).toBe(true);
    expect(exists("./login/page.tsx")).toBe(false);
  });
});
