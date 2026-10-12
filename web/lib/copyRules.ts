// The site copy rules (06 §4, §9): no social proof, no invented numbers, and no prices while no plans are set.
// Used by the tests that scan web/content/*.ts and the rendered site pages.

export interface CopyRule {
  name: string;
  pattern: RegExp;
}

/**
 * ROOK-048: people never see the word "demo" (it is "Try Rook" and "example repos"). The site and the web app's
 * visible strings are both checked against it; API values like `kind: "demo"` are not user-facing.
 */
export const NO_DEMO_WORD: CopyRule = { name: "the word demo", pattern: /\bdemos?\b/i };

/**
 * ROOK-053: the site presents Rook as early access, not a hackathon entry. Only the About story may say it
 * (06 §4 "Positioning"); the tests scope this rule to everything else.
 */
export const NO_HACKATHON: CopyRule = { name: "the word hackathon", pattern: /\bhackathons?\b/i };

/**
 * ROOK-053: no fill-in-later text such as "[contact email]", "[Company legal name]", "[jurisdiction]" or "[...]".
 * A capitalised or placeholder-ish word in square brackets counts; CLI syntax like "rook run [repo]" does not.
 */
export const NO_PLACEHOLDER: CopyRule = {
  name: "a [placeholder]",
  pattern: /\[\s*(?:\.\.\.|…)\s*\]|\[(?:[A-Z][^\]\n]*|[^\]\n]*\b(?:email|name|jurisdiction|date|address|company|legal|tbd|todo|placeholder|insert)\b[^\]\n]*)\]/,
};

/** Banned everywhere on the site. */
export const BANNED_COPY: CopyRule[] = [
  { name: "trusted by", pattern: /\btrusted by\b/i },
  { name: "loved by", pattern: /\bloved by\b/i },
  { name: "used by", pattern: /\bused by\b/i },
  { name: "customers", pattern: /\bcustomers?\b/i },
  { name: "testimonial", pattern: /\btestimonials?\b/i },
  { name: "case study", pattern: /\bcase stud(y|ies)\b/i },
  { name: "join thousands", pattern: /\bjoin (thousands|hundreds|millions)\b/i },
  { name: "thousands of", pattern: /\b(thousands|hundreds|millions) of\b/i },
  { name: "teams/companies use", pattern: /\b(teams|companies|developers|engineers|startups|enterprises) (use|love|rely on|trust)\b/i },
  { name: "a count of adopters", pattern: /\b\d[\d,.]*\s*k?\+?\s*(teams|companies|customers|developers|engineers|users|stars|downloads|installs)\b/i },
  // "%s" is the title template, not a figure.
  { name: "percentage", pattern: /%(?!s\b)|\bper ?cent\b/i },
  { name: "multiplier (10x)", pattern: /\b\d+(\.\d+)?\s?[x×](?![a-z0-9])/i },
  // "1,000+", "500+", "10k+"; a version like "3.12+" is not a count (no digit or dot right before it).
  { name: "count with a plus (1,000+)", pattern: /(?<![\d.])\d[\d,]*\s*[kKmM]?\s*\+|\d\.\d+\s*[kKmM]\s*\+/ },
  { name: "per month / year", pattern: /\bper (month|year|seat|user\/month)\b|\/\s?(mo|month|yr|year)\b|\bmonthly\b|\bannually\b/i },
  { name: "star rating", pattern: /[★☆⭐]|\b\d(\.\d)?\s*\/\s*5\b|\b\d(\.\d)?\s*stars?\b|\brated\b/i },
  { name: "award / as seen in", pattern: /\baward[- ]winning\b|\bas seen (in|on)\b|\bfeatured in\b/i },
  // Rook holds no certifications and has had no audit (06 §4). A claim like "SOC 2 certified" or "independently
  // audited" is banned; a negated one ("no third-party audit", "not SOC 2 certified") is the honest line.
  { name: "certification / audit claim", pattern: certificationClaim() },
  NO_DEMO_WORD,
];

/**
 * A certification or audit term, unless a negation governs it: the negation comes at most 40 characters earlier in
 * the same clause, is not "not just / not only" (which asserts the term), and no contrast word stands between them
 * ("not just audited but certified" still claims "certified").
 */
function certificationClaim(): RegExp {
  const negation = String.raw`\b(?:no|not|nor|never|without|isn't|aren't|hasn't|haven't)\b(?!\s+(?:just|only|merely|simply)\b)`;
  const contrast = String.raw`\b(?:but|however|yet|though|although|instead)\b`;
  const clauseChar = String.raw`(?:(?!${contrast})[^.;:])`;
  const term = String.raw`\b(?:soc ?[12]|iso ?27001|hipaa|gdpr[- ]compliant|pci[- ]dss|fedramp|(?:independently |third[- ]party )?audited|pen(?:etration)?[- ]tested|certified)\b`;
  return new RegExp(String.raw`(?<!${negation}${clauseChar}{0,40})${term}`, "i");
}

/** Banned on the pricing page and in the pricing content while prices may not be stated (06 §5.4). */
export const BANNED_PRICING: CopyRule[] = [
  { name: "currency amount", pattern: /[$€£₹¥]\s?\d|\b\d[\d,.]*\s?(usd|eur|gbp|inr|dollars?|euros?|rupees?)\b/i },
  { name: "free plan price", pattern: /\bfree (tier|plan|forever)\b|\$0\b/i },
];

/** The rules a text breaks (empty = clean). */
export function copyViolations(text: string, opts: { pricing?: boolean } = {}): string[] {
  const rules = opts.pricing ? [...BANNED_COPY, ...BANNED_PRICING] : BANNED_COPY;
  return rules.filter((rule) => rule.pattern.test(text)).map((rule) => rule.name);
}

/** Every string inside a value: strings, arrays and plain objects, deeply (functions and the rest skipped). */
export function collectStrings(value: unknown, seen: Set<unknown> = new Set()): string[] {
  if (typeof value === "string") return [value];
  if (value === null || typeof value !== "object" || seen.has(value)) return [];
  seen.add(value);
  const children = Array.isArray(value) ? value : Object.values(value);
  return children.flatMap((child) => collectStrings(child, seen));
}
