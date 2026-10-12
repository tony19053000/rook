import type { Metadata } from "next";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { roadmapCopy, roadmapLists, type RoadmapList } from "@/content/roadmap";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(roadmapCopy.title, roadmapCopy.description, "/roadmap");

/** The marker colour of each list (site tokens, all at least 3:1 on the card as UI marks). */
const MARK: Record<RoadmapList["id"], string> = { shipped: "bg-site-good", limited: "bg-site-warn", planned: "bg-site-faint" };

// /roadmap (06 §5.8): Shipped, Limited and Planned, each a section with a plain list. A server component.
export default function RoadmapPage() {
  return (
    <>
      <PageHeader eyebrow={roadmapCopy.eyebrow} heading={roadmapCopy.heading} lead={roadmapCopy.lead} />
      {roadmapLists.map((list) => (
        <Section key={list.id} id={list.id} title={list.title} intro={list.intro} width="narrow">
          <ul className="flex flex-col divide-y divide-site-line rounded-2xl border border-site-line bg-site-card" data-roadmap={list.id}>
            {list.items.map((item) => (
              <li key={item} className="flex items-start gap-3 px-5 py-4 text-base leading-relaxed text-site-muted">
                <span aria-hidden className={`mt-2.5 size-2 flex-none rounded-full ${MARK[list.id]}`} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Section>
      ))}
    </>
  );
}
