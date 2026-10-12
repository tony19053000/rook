import type { Metadata } from "next";
import { GuideView } from "@/components/site/docs/GuideView";
import { installGuide } from "@/content/docsInstall";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(installGuide.title, installGuide.description, installGuide.path);

export default function InstallGuidePage() {
  return <GuideView guide={installGuide} />;
}
