import type { Metadata } from "next";
import { LegalDocView } from "@/components/site/LegalDocView";
import { termsOfService } from "@/content/legal";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(termsOfService.title, termsOfService.description, "/terms");

export default function TermsPage() {
  return <LegalDocView doc={termsOfService} />;
}
