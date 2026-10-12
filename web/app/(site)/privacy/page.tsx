import type { Metadata } from "next";
import { LegalDocView } from "@/components/site/LegalDocView";
import { privacyPolicy } from "@/content/legal";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(privacyPolicy.title, privacyPolicy.description, "/privacy");

export default function PrivacyPage() {
  return <LegalDocView doc={privacyPolicy} />;
}
