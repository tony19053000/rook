// Structured data for search engines (06 §8): who runs Roook and what it is, as one schema.org JSON-LD graph on the
// home page. Every value comes from content/site.ts, so it says nothing the site's own text does not.

import { CONTACT_EMAIL, LICENSE_URL, operator, REPO_URL, site, SITE_URL } from "@/content/site";
import { absoluteUrl } from "./seo";

export type JsonLdValue = string | boolean | JsonLdValue[] | { [key: string]: JsonLdValue };

const ORGANIZATION_ID = `${SITE_URL}/#organization`;
const FOUNDER_ID = `${SITE_URL}/#founder`;
const WEBSITE_ID = `${SITE_URL}/#website`;

/** Roook, its founder, the website and the product. No address, registration, rating, price or review: there are none. */
export function siteStructuredData(): JsonLdValue {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": ORGANIZATION_ID,
        name: site.name,
        url: SITE_URL,
        logo: absoluteUrl("/icon.svg"),
        description: site.oneLiner,
        email: CONTACT_EMAIL,
        founder: { "@id": FOUNDER_ID },
        sameAs: [REPO_URL],
      },
      {
        "@type": "Person",
        "@id": FOUNDER_ID,
        name: operator.name,
        jobTitle: operator.role,
        worksFor: { "@id": ORGANIZATION_ID },
      },
      {
        "@type": "WebSite",
        "@id": WEBSITE_ID,
        name: site.name,
        url: SITE_URL,
        description: site.tagline,
        inLanguage: "en",
        publisher: { "@id": ORGANIZATION_ID },
      },
      {
        "@type": "SoftwareApplication",
        name: site.name,
        url: SITE_URL,
        description: site.oneLiner,
        applicationCategory: "DeveloperApplication",
        license: LICENSE_URL,
        isAccessibleForFree: true,
        author: { "@id": FOUNDER_ID },
        publisher: { "@id": ORGANIZATION_ID },
      },
    ],
  };
}
