// The site copy rules (06 §4, §9): no social proof, no invented numbers, and no prices while no plans are set.
// Used by the tests that scan web/content/*.ts and the rendered site pages.

export interface CopyRule {
  name: string;
  pattern: RegExp;
}

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
];

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
