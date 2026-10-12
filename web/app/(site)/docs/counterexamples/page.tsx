import type { Metadata } from "next";
import { GuideView } from "@/components/site/docs/GuideView";
import { RefundStory } from "@/components/site/home/RefundStory";
import { counterexamplesGuide } from "@/content/docsCounterexamples";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(counterexamplesGuide.title, counterexamplesGuide.description, counterexamplesGuide.path);

// The refund case is the home page's story (content/story.ts): the recorded minishop run, labelled as recorded.
export default function CounterexamplesGuidePage() {
  return <GuideView guide={counterexamplesGuide} slots={{ "refund-story": <RefundStory /> }} />;
}
