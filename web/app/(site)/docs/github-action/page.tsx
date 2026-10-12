import type { Metadata } from "next";
import { GuideView } from "@/components/site/docs/GuideView";
import { githubActionGuide } from "@/content/docsGithubAction";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(githubActionGuide.title, githubActionGuide.description, githubActionGuide.path);

export default function GithubActionGuidePage() {
  return <GuideView guide={githubActionGuide} />;
}
