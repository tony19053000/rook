import type { Metadata } from "next";
import { PageHeader } from "@/components/site/PageHeader";
import { Container } from "@/components/site/Container";
import { type } from "@/components/site/tokens";
import { roadmapCopy, roadmapLists, type RoadmapList } from "@/content/roadmap";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(roadmapCopy.title, roadmapCopy.description, "/roadmap");

/** The marker colour of each list (site tokens, all at least 3:1 on the card as UI marks). */
const MARK: Record<RoadmapList["id"], string> = { shipped: "bg-site-good", limited: "bg-site-warn", planned: "bg-site-control" };

// /roadmap (06 §5.8): Shipped, Limited and Planned, each a section with a plain list: three columns of a board
// on wide screens, one after the other on narrow ones. A server component.
export default function RoadmapPage() {
  return (
    <>
      <PageHeader eyebrow={roadmapCopy.eyebrow} heading={roadmapCopy.heading} lead={roadmapCopy.lead} width="wide" />
      <Container className="grid gap-x-5 gap-y-14 py-14 sm:py-20 lg:grid-cols-3 lg:items-start">
        {roadmapLists.map((list) => (
          <section key={list.id} id={list.id} aria-labelledby={`${list.id}-title`} className="scroll-mt-24">
            <div className="flex items-center gap-3">
              <span aria-hidden className={`size-2.5 flex-none rounded-full ${MARK[list.id]}`} />
              <h2 id={`${list.id}-title`} className={`${type.h2Doc} text-site-ink`}>
                {list.title}
              </h2>
            </div>
            <p className={`${type.small} mt-2`}>{list.intro}</p>
            <ul className="site-panel mt-6 flex flex-col divide-y divide-site-line rounded-2xl" data-roadmap={list.id}>
              {list.items.map((item) => (
                <li key={item} className="flex items-start gap-3.5 px-5 py-4 text-[0.9375rem] leading-relaxed text-site-muted">
                  <span aria-hidden className={`mt-[0.6em] size-1.5 flex-none rounded-full ${MARK[list.id]}`} />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </Container>
    </>
  );
}
