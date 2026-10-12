import type { Metadata } from "next";
import { GuideView } from "@/components/site/docs/GuideView";
import { gettingStartedGuide } from "@/content/docsGettingStarted";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(gettingStartedGuide.title, gettingStartedGuide.description, gettingStartedGuide.path);

export default function GettingStartedGuidePage() {
  return <GuideView guide={gettingStartedGuide} />;
}
