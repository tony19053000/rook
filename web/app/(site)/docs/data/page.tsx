import type { Metadata } from "next";
import { GuideView } from "@/components/site/docs/GuideView";
import { dataGuide } from "@/content/docsData";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(dataGuide.title, dataGuide.description, dataGuide.path);

export default function DataGuidePage() {
  return <GuideView guide={dataGuide} />;
}
