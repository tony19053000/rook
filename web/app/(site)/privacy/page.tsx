import type { Metadata } from "next";
import { LegalDocView } from "@/components/site/LegalDocView";
import { privacyPolicy } from "@/content/legal";

export const metadata: Metadata = { title: privacyPolicy.title, description: privacyPolicy.description };

export default function PrivacyPage() {
  return <LegalDocView doc={privacyPolicy} />;
}
