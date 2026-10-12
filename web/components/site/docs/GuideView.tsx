import Link from "next/link";
import type { ReactNode } from "react";
import { CodeBlock } from "../CodeBlock";
import { Container } from "../Container";
import { InlineCode } from "../InlineCode";
import { NavLinkItem } from "../NavLinkItem";
import { link as LINK, measure, type } from "../tokens";
import { DocsNav } from "./DocsNav";
import { guideNeighbours, guidesCopy } from "@/content/docsGuides";
import type { DocBlock, DocGuide, DocSlot, DocSubsection } from "@/content/docsModel";
import { mailtoHref } from "@/content/site";

const LIST = "site-list text-base leading-[1.7] text-site-muted";

function Block({ block, slots }: { block: DocBlock; slots: Partial<Record<DocSlot, ReactNode>> }) {
  switch (block.kind) {
    case "p":
      return (
        <p className={`${type.body} ${measure}`}>
          <InlineCode text={block.text} />
        </p>
      );
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag className={`${LIST} ${measure}`}>
          {block.items.map((item) => (
            <li key={item}>
              <InlineCode text={item} />
            </li>
          ))}
        </Tag>
      );
    }
    case "code":
      return (
        <div className={measure}>
          <CodeBlock code={block.code} label={block.label} prompt={block.prompt} />
        </div>
      );
    case "note":
      return (
        <div role="note" className={`rounded-xl border border-site-warn/30 border-l-2 border-l-site-warn bg-site-warn-soft px-5 py-4 ${measure}`}>
          <p className="text-sm font-semibold text-site-warn">{block.title}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-site-warn">
            <InlineCode text={block.text} />
          </p>
        </div>
      );
    case "terms":
      return (
        <dl className={`site-panel flex flex-col divide-y divide-site-line rounded-2xl ${measure}`}>
          {block.items.map((item) => (
            <div key={item.term} className="flex flex-col gap-1.5 px-5 py-4 sm:px-6">
              <dt className="font-mono text-[0.8125rem] break-words text-site-ink">{item.term}</dt>
              <dd className={type.small}>
                <InlineCode text={item.text} />
              </dd>
            </div>
          ))}
        </dl>
      );
    case "links":
      return (
        <ul className={`flex flex-col gap-2.5 text-[0.9375rem] ${measure}`}>
          {block.items.map((link) => (
            <li key={link.href}>
              <NavLinkItem link={link} className={LINK} />
            </li>
          ))}
        </ul>
      );
    case "email":
      return (
        <p className={`text-[0.9375rem] ${measure}`}>
          <a href={mailtoHref(block.subject)} className={LINK}>
            {block.label}
          </a>
        </p>
      );
    case "slot":
      return <div data-doc-slot={block.name}>{slots[block.name]}</div>;
  }
}

function Blocks({ part, slots }: { part: DocSubsection; slots: Partial<Record<DocSlot, ReactNode>> }) {
  return (
    <div className="mt-5 flex flex-col gap-5">
      {part.blocks.map((block, i) => (
        <Block key={i} block={block} slots={slots} />
      ))}
    </div>
  );
}

interface GuideViewProps {
  guide: DocGuide;
  /** The page-specific parts its `slot` blocks name. */
  slots?: Partial<Record<DocSlot, ReactNode>>;
}

// A docs guide (06 §5.10, ROOK-055): the docs navigation, the page's one h1, a table of contents of anchor links,
// the sections (h2, with h3 subsections) and the previous/next links. A server component with no client code.
// Wide screens: the navigation in a left rail, the table of contents in a right rail, both sticky. Narrower
// ones: the same table of contents, in the flow under the lead.
export function GuideView({ guide, slots = {} }: GuideViewProps) {
  const { previous, next } = guideNeighbours(guide.path);
  return (
    <div className="relative isolate">
      <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-72" />
      <Container className="pt-10 pb-20 sm:pt-16 sm:pb-28">
        <div className="grid gap-10 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-14 xl:grid-cols-[13rem_minmax(0,1fr)]">
          <DocsNav current={guide.path} />

          <article className="grid min-w-0 gap-x-14 xl:grid-cols-[minmax(0,1fr)_14rem]" data-guide={guide.path}>
            <div className="min-w-0 xl:col-start-1 xl:row-start-1">
              <p className={type.eyebrow}>{guidesCopy.eyebrow}</p>
              <h1 className={`${type.h1} mt-6 max-w-3xl text-site-ink`}>{guide.heading}</h1>
              <p className={`${type.lead} mt-6 ${measure}`}>{guide.lead}</p>
            </div>

            <div className="mt-10 min-w-0 xl:col-start-2 xl:row-span-2 xl:row-start-1 xl:mt-0">
              <nav
                aria-label={guidesCopy.tocLabel}
                data-toc
                className={`rounded-2xl border border-site-line bg-site-card px-5 py-5 xl:sticky xl:top-24 xl:max-h-[calc(100vh-8rem)] xl:overflow-y-auto xl:rounded-none xl:border-0 xl:border-l xl:bg-transparent xl:py-1 xl:pr-0 ${measure}`}
              >
                <p className={type.label}>{guidesCopy.tocLabel}</p>
                <ol className="mt-4 flex flex-col gap-2.5 text-sm">
                  {guide.sections.map((section) => (
                    <li key={section.id}>
                      <a href={`#${section.id}`} className="text-site-muted transition-colors hover:text-site-ink">
                        {section.title}
                      </a>
                      {section.subsections && (
                        <ol className="mt-2.5 flex flex-col gap-2 border-l border-site-line pl-3.5">
                          {section.subsections.map((sub) => (
                            <li key={sub.id}>
                              <a href={`#${sub.id}`} className="text-site-faint transition-colors hover:text-site-ink">
                                {sub.title}
                              </a>
                            </li>
                          ))}
                        </ol>
                      )}
                    </li>
                  ))}
                </ol>
              </nav>
            </div>

            <div className="min-w-0 xl:col-start-1 xl:row-start-2">
              {guide.sections.map((section) => (
                <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="mt-12 scroll-mt-24 border-t border-site-line pt-12">
                  <h2 id={`${section.id}-title`} className={`${type.h2Doc} text-site-ink`}>
                    {section.title}
                  </h2>
                  <Blocks part={section} slots={slots} />
                  {section.subsections?.map((sub) => (
                    <div key={sub.id} id={sub.id} className="mt-10 scroll-mt-24">
                      <h3 className="text-lg leading-snug font-semibold tracking-[-0.012em] text-site-ink">{sub.title}</h3>
                      <Blocks part={sub} slots={slots} />
                    </div>
                  ))}
                </section>
              ))}

              <nav aria-label={guidesCopy.pagerLabel} data-pager className="mt-16 grid gap-4 border-t border-site-line pt-8 sm:grid-cols-2">
                {previous ? (
                  <Link href={previous.href} rel="prev" className="site-panel group rounded-2xl px-5 py-4 transition-colors hover:border-site-strong">
                    <span className={type.label}>{guidesCopy.previous}</span>
                    <span className="mt-1.5 block text-base font-medium text-site-ink">{previous.label}</span>
                  </Link>
                ) : (
                  <span />
                )}
                {next && (
                  <Link href={next.href} rel="next" className="site-panel group rounded-2xl px-5 py-4 transition-colors hover:border-site-strong sm:text-right">
                    <span className={type.label}>{guidesCopy.next}</span>
                    <span className="mt-1.5 block text-base font-medium text-site-ink">{next.label}</span>
                  </Link>
                )}
              </nav>
            </div>
          </article>
        </div>
      </Container>
    </div>
  );
}
