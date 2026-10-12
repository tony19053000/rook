import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { collectStrings, copyViolations, NO_HACKATHON, NO_PLACEHOLDER } from "./copyRules";
import { RECORDED_STRINGS } from "./recordedData";
import * as pricing from "@/content/pricing";

// Every module in web/content/, so a new content file is scanned without touching this test.
const CONTENT_FILES = readdirSync(resolve(process.cwd(), "content")).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"));

/** The only content allowed to name the hackathon: the About page's story (06 §4 "Positioning"). */
const HACKATHON_ALLOWED = new Set(["about.ts"]);

describe("copy rules (06 §4, §9)", () => {
  it("catch social proof and invented numbers", () => {
    for (const bad of [
      "Trusted by 500+ teams",
      "Loved by developers",
      "Used by engineers at big companies",
      "Our customers say",
      "Read the testimonials",
      "Join thousands of teams",
      "Teams use Rook every day",
      "1,000+ bugs found",
      "10k+ runs",
      "Find bugs 10x faster",
      "99% fewer incidents",
      "4.9/5 on reviews",
      "★★★★★",
      "1,200 developers",
      "$29 per month",
      "Starts at 9/mo",
    ]) {
      expect(copyViolations(bad), bad).not.toEqual([]);
    }
  });

  it("catch certification and audit claims unless they are negated", () => {
    for (const bad of [
      "Rook is SOC 2 certified.",
      "SOC2 Type II",
      "ISO 27001 compliant hosting",
      "HIPAA-ready by design",
      "Fully GDPR compliant",
      "Independently audited code",
      "Penetration tested every release",
      "Certified secure",
    ]) {
      expect(copyViolations(bad), bad).toContain("certification / audit claim");
    }
    for (const ok of [
      "There has been no third-party audit or penetration test, and Rook holds no certifications.",
      "Rook is not SOC 2 certified.",
      "It has never been penetration tested.",
    ]) {
      expect(copyViolations(ok), ok).toEqual([]);
    }
  });

  it("a negation shields a term only when it governs it (no contrast word, not 'not just')", () => {
    for (const bad of [
      "not just audited but certified",
      "SOC 2 certified",
      "We are HIPAA compliant",
      "GDPR-compliant",
      "independently audited",
      "not only audited, but also penetration tested",
      "No setup needed, however it is SOC 2 certified.",
    ]) {
      expect(copyViolations(bad), bad).toContain("certification / audit claim");
    }
    for (const ok of [
      "Rook has no third-party audit or penetration test, and no certifications",
      "not audited",
      "never penetration tested",
    ]) {
      expect(copyViolations(ok), ok).toEqual([]);
    }
  });

  it("stay strict about customers and counts with a plus: no pattern exempts run data (ROOK-054)", () => {
    for (const bad of [
      "happy customer: refund(amount=1) feedback",
      "our customer: love(it)",
      "Built for every customer",
      "customer: refund(amount=1)",
      "500\n+ runs",
      "1,000\n+ bugs found",
      "1,000\n+ teams",
      "else 0\n+        already = order.refunded_total",
    ]) {
      expect(copyViolations(bad), bad).not.toEqual([]);
    }
  });

  it("exempt recorded run data by identity only: the fixture's exact step lines, diff and actor names", () => {
    for (const ok of ["customer: refund(amount=1)", "admin: create_product(price=1, stock=1)", "+        already = order.refunded_total", "customer"]) {
      expect(RECORDED_STRINGS.has(ok), ok).toBe(true);
    }
    for (const bad of ["happy customer: refund(amount=1) feedback", "our customer: love(it)", "Built for every customer", "customers", "customer: refund(amount=2)", "500\n+ runs"]) {
      expect(RECORDED_STRINGS.has(bad), bad).toBe(false);
    }
  });

  it("catch the word demo (ROOK-048), but not words that only start with it", () => {
    for (const bad of ["Try the demo", "DEMO repos", "Two demos", "the demo's rule"]) {
      expect(copyViolations(bad), bad).toContain("the word demo");
    }
    for (const ok of ["Try Rook", "It demonstrates the bug", "a democratic process"]) {
      expect(copyViolations(ok), ok).toEqual([]);
    }
  });

  it("allow the true product facts", () => {
    for (const ok of [
      "Needs Python 3.12+ and Docker.",
      "Replayed on the real app, 10 times by default.",
      "A fresh search with a new seed (default budget 20,000 sequences).",
      "Guests get 3 runs a day; 5 per user per day.",
      "13 Bob agents: a Coordinator and 12 specialists.",
      "10 s timeout, 1 MB response cap.",
      "Paid ₹100, refunded ₹110.",
      "A pull request opens from a rook/fix-* branch.",
    ]) {
      expect(copyViolations(ok), ok).toEqual([]);
    }
  });

  it("ban currency amounts only where pricing applies", () => {
    expect(copyViolations("Paid ₹100", { pricing: true })).toContain("currency amount");
    expect(copyViolations("Pro: $29", { pricing: true })).toContain("currency amount");
    expect(copyViolations("Pricing will be published at launch", { pricing: true })).toEqual([]);
  });

  it("collectStrings walks nested arrays and objects", () => {
    expect(collectStrings({ a: "x", b: [{ c: "y" }, 3, null], d: () => "z" }).sort()).toEqual(["x", "y"]);
  });

  it("nothing in content/*.ts breaks a rule", async () => {
    expect(CONTENT_FILES.length).toBeGreaterThanOrEqual(5);
    for (const file of CONTENT_FILES) {
      const mod: unknown = await import(`../content/${file}`);
      const isPricing = file === "pricing.ts";
      for (const text of collectStrings(mod)) {
        if (RECORDED_STRINGS.has(text)) continue; // verbatim data of the recorded run, by identity (lib/recordedData.ts)
        expect(copyViolations(text, { pricing: isPricing }), `${file}: ${text}`).toEqual([]);
      }
    }
  });

  it("catch the word hackathon and [placeholders], but not CLI syntax (ROOK-053)", () => {
    for (const bad of ["A hackathon-stage project", "Built for the Hackathon"]) expect(NO_HACKATHON.pattern.test(bad), bad).toBe(true);
    for (const bad of ["Contact: [contact email]", "[Company legal name]", "under the laws of [jurisdiction]", "Effective [date]", "See [...]", "[TBD]", "[ … ]"]) {
      expect(NO_PLACEHOLDER.pattern.test(bad), bad).toBe(true);
    }
    for (const ok of ["rook run [repo]", "rook replay <cx> --base-url <url>", "a list [1, 2]", "Early access, open source."]) {
      expect(NO_PLACEHOLDER.pattern.test(ok), ok).toBe(false);
    }
  });

  it("no hackathon outside the About story, and no [placeholders], in content/*.ts (ROOK-053)", async () => {
    let aboutMentions = 0;
    for (const file of CONTENT_FILES) {
      const mod: unknown = await import(`../content/${file}`);
      for (const text of collectStrings(mod)) {
        expect(NO_PLACEHOLDER.pattern.test(text), `${file}: ${text}`).toBe(false);
        if (HACKATHON_ALLOWED.has(file)) aboutMentions += Number(NO_HACKATHON.pattern.test(text));
        else expect(NO_HACKATHON.pattern.test(text), `${file}: ${text}`).toBe(false);
      }
    }
    expect(aboutMentions, "the About story names the hackathon once").toBe(1);
  });

  it("the pricing content states no price while plans is empty", () => {
    expect(pricing.plans).toEqual([]);
    for (const text of collectStrings(pricing)) expect(copyViolations(text, { pricing: true }), text).toEqual([]);
  });
});
