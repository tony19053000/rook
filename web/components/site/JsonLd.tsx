import type { JsonLdValue } from "@/lib/structuredData";

/**
 * A schema.org JSON-LD block. It is a data block, not a script the browser runs, so the nonce-based CSP (03 §8)
 * does not apply to it. "<" is escaped so no value can close the element.
 */
export function JsonLd({ data }: { data: JsonLdValue }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />;
}
