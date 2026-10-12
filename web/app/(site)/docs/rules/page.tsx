import type { Metadata } from "next";
import { CodeBlock } from "@/components/site/CodeBlock";
import { GuideView } from "@/components/site/docs/GuideView";
import { guidesCopy } from "@/content/docsGuides";
import { rulesGuide } from "@/content/docsRules";
import { MINISHOP_ROOK_YAML, MINISHOP_ROOK_YAML_PATH } from "@/lib/fixtures/minishopRookYaml";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(rulesGuide.title, rulesGuide.description, rulesGuide.path);

// The example is tests/fixtures/minishop/rook.yaml, whole and unchanged (a test compares it with the file).
export default function RulesGuidePage() {
  const example = (
    <CodeBlock code={MINISHOP_ROOK_YAML} label={`${MINISHOP_ROOK_YAML_PATH} · ${guidesCopy.repoFileNote}`} repoFile />
  );
  return <GuideView guide={rulesGuide} slots={{ "rook-yaml": example }} />;
}
