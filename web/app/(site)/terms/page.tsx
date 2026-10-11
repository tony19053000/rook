import type { Metadata } from "next";
import { LegalDocView } from "@/components/site/LegalDocView";
import { termsOfService } from "@/content/legal";

export const metadata: Metadata = { title: termsOfService.title, description: termsOfService.description };

export default function TermsPage() {
  return <LegalDocView doc={termsOfService} />;
}
