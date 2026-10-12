// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import SiteLayout from "@/app/(site)/layout";
import PrivacyPage from "@/app/(site)/privacy/page";
import SecurityPage from "@/app/(site)/security/page";
import TermsPage from "@/app/(site)/terms/page";
import { CONTACT_EMAIL, operator } from "@/content/site";
import { collectStrings, copyViolations, NO_PLACEHOLDER } from "@/lib/copyRules";
import * as legal from "@/content/legal";

afterEach(cleanup);

const main = (page: ReactElement): string => {
  const { container } = render(<SiteLayout>{page}</SiteLayout>);
  return container.querySelector("main")?.textContent ?? "";
};

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

  it("names the operator, the contact email and India", () => {
    const text = main(page);
    expect(text).toContain(operator.name);
    expect(text).toContain("individual developer");
    expect(text).toContain(CONTACT_EMAIL);
    expect(text).toContain("India");
    expect(text).toMatch(/laws of India/);
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
