// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import SiteLayout from "@/app/(site)/layout";
import PrivacyPage from "@/app/(site)/privacy/page";
import SecurityPage from "@/app/(site)/security/page";
import TermsPage from "@/app/(site)/terms/page";
import { CONTACT_EMAIL, operator, SITE_URL } from "@/content/site";
import { collectStrings, copyViolations, NO_PLACEHOLDER } from "@/lib/copyRules";
import * as legal from "@/content/legal";

afterEach(cleanup);

const mainElement = (page: ReactElement): HTMLElement => {
  const { container } = render(<SiteLayout>{page}</SiteLayout>);
  return container.querySelector("main")!;
};
const main = (page: ReactElement): string => mainElement(page).textContent ?? "";

describe.each([
  ["/privacy", <PrivacyPage key="p" />],
  ["/terms", <TermsPage key="t" />],
])("%s is in effect (ROOK-056)", (_path, page) => {
  it("has no draft banner, no draft wording and no [placeholders]", () => {
    const text = main(page);
    expect(text).not.toMatch(/draft|pending legal review|hackathon/i);
    expect(text.match(new RegExp(NO_PLACEHOLDER.pattern.source, "g")) ?? []).toEqual([]);
    expect(text).toContain("Last updated: 12 October 2026");
  });

  it("names the operator as a person operating Roook, the site, the contact email and India", () => {
    const text = main(page);
    expect(text).toContain(`${operator.name}, operating Roook`);
    expect(text).toContain(`${operator.name} is an individual based in India. Roook is not incorporated as a company`);
    expect(text).toContain(SITE_URL);
    expect(text).toContain(CONTACT_EMAIL);
    expect(text).toMatch(/laws of India/);
  });

  it("names no company form, registration, postal address or other mailbox", () => {
    const text = main(page);
    expect(text).not.toMatch(/\b(Pvt|Private Limited|Ltd|LLP|LLC|Inc|GmbH|registered office|registration number|CIN|GSTIN)\b/);
    expect(text).not.toMatch(/gmail\.com|vercel\.app/i);
    expect(text.split(CONTACT_EMAIL).join(""), "an address other than the contact one").not.toContain("@");
  });

  it("links every mention of the contact address as mailto:", () => {
    const el = mainElement(page);
    const mentions = (el.textContent ?? "").split(CONTACT_EMAIL).length - 1;
    const links = [...el.querySelectorAll('a[href^="mailto:"]')];
    expect(mentions).toBeGreaterThanOrEqual(1);
    expect(links).toHaveLength(mentions);
    for (const a of links) {
      expect(new URL(a.getAttribute("href")!).pathname).toBe(CONTACT_EMAIL);
      expect(a.textContent).toBe(CONTACT_EMAIL);
    }
  });

  it("claims no certification, audit or compliance", () => {
    expect(copyViolations(main(page))).toEqual([]);
  });
});

describe("/privacy facts", () => {
  it("states the retention numbers and the deletion routes", () => {
    const text = main(<PrivacyPage />);
    expect(text).toMatch(/30 days/);
    expect(text).toMatch(/2 days/);
    expect(text).toMatch(/Oregon/);
    expect(text).toMatch(/email/i);
    expect(text).not.toMatch(/not deleted automatically/i);
  });
});

describe("/terms facts", () => {
  it("mentions the MIT licence and as-is early access", () => {
    const text = main(<TermsPage />);
    expect(text).toMatch(/MIT licence/);
    expect(text).toMatch(/as is during early access/);
  });
});

describe("/security after ROOK-050 and 051", () => {
  it("does not say the socket is mounted, and says hosted own-repo runs are off", () => {
    const text = main(<SecurityPage />);
    expect(text).toMatch(/mounts no Docker socket/);
    expect(text).toMatch(/hosted runs of your own repos are turned off/i);
    expect(text).not.toMatch(/has access to the Docker socket/);
    expect(text).not.toMatch(/not deleted automatically/i);
    expect(text).toMatch(/30 days/);
    expect(copyViolations(text)).toEqual([]);
  });
});

describe("content/legal.ts", () => {
  it("has no placeholder or draft export", () => {
    expect(Object.keys(legal)).not.toContain("legalPlaceholders");
    expect(Object.keys(legal)).not.toContain("LEGAL_DRAFT_BANNER");
    for (const s of collectStrings(legal)) expect(NO_PLACEHOLDER.pattern.test(s), s).toBe(false);
  });
});
