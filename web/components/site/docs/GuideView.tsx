import Link from "next/link";
import type { ReactNode } from "react";
import { CodeBlock } from "../CodeBlock";
import { Container } from "../Container";
import { InlineCode } from "../InlineCode";
import { NavLinkItem } from "../NavLinkItem";
import { measure, type } from "../tokens";
import { DocsNav } from "./DocsNav";
import { guideNeighbours, guidesCopy } from "@/content/docsGuides";
import type { DocBlock, DocGuide, DocSlot, DocSubsection } from "@/content/docsModel";
import { mailtoHref } from "@/content/site";

const LINK = "text-site-link underline underline-offset-4";
const LIST = "flex flex-col gap-2 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint";

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
        <Tag className={`${LIST} ${measure} ${block.ordered ? "list-decimal" : "list-disc"}`}>
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
        <div role="note" className={`rounded-xl border border-site-warn/40 bg-site-warn-soft px-4 py-3 ${measure}`}>
          <p className="text-sm font-semibold text-site-warn">{block.title}</p>
          <p className="mt-1 text-sm leading-relaxed text-site-warn">
            <InlineCode text={block.text} />
          </p>
        </div>
      );
    case "terms":
      return (
        <dl className={`flex flex-col divide-y divide-site-line rounded-2xl border border-site-line bg-site-card ${measure}`}>
          {block.items.map((item) => (
            <div key={item.term} className="flex flex-col gap-1 px-5 py-4">
              <dt className="font-mono text-sm break-words text-site-ink">{item.term}</dt>
              <dd className={type.small}>
                <InlineCode text={item.text} />
              </dd>
            </div>
          ))}
        </dl>
      );
    case "links":
      return (
        <ul className={`flex flex-col gap-2 text-sm ${measure}`}>
          {block.items.map((link) => (
            <li key={link.href}>
              <NavLinkItem link={link} className={LINK} />
            </li>
          ))}
        </ul>
      );
    case "email":
      return (
        <p className={`text-sm ${measure}`}>
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
export function GuideView({ guide, slots = {} }: GuideViewProps) {
  const { previous, next } = guideNeighbours(guide.path);
  return (
    <Container className="pt-10 pb-16 sm:pt-14 sm:pb-24">
      <div className="grid gap-10 lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-14 xl:grid-cols-[14rem_minmax(0,1fr)]">
        <DocsNav current={guide.path} />

        <article className="min-w-0" data-guide={guide.path}>
          <p className={type.eyebrow}>{guidesCopy.eyebrow}</p>
          <h1 className={`${type.h1} mt-4 max-w-3xl text-site-ink`}>{guide.heading}</h1>
          <p className={`${type.lead} mt-5 ${measure}`}>{guide.lead}</p>

          <nav aria-label={guidesCopy.tocLabel} data-toc className={`mt-8 rounded-2xl border border-site-line bg-site-card px-5 py-4 ${measure}`}>
            <p className={type.eyebrow}>{guidesCopy.tocLabel}</p>
            <ol className="mt-3 flex flex-col gap-2 text-sm">
              {guide.sections.map((section) => (
                <li key={section.id}>
                  <a href={`#${section.id}`} className={LINK}>
                    {section.title}
                  </a>
                  {section.subsections && (
                    <ol className="mt-2 flex flex-col gap-1.5 pl-4">
                      {section.subsections.map((sub) => (
                        <li key={sub.id}>
                          <a href={`#${sub.id}`} className="text-site-muted underline underline-offset-4 hover:text-site-ink">
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

          {guide.sections.map((section) => (
            <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="mt-14 scroll-mt-24">
              <h2 id={`${section.id}-title`} className={`${type.h2} text-site-ink`}>
                {section.title}
              </h2>
              <Blocks part={section} slots={slots} />
              {section.subsections?.map((sub) => (
                <div key={sub.id} id={sub.id} className="mt-10 scroll-mt-24">
                  <h3 className={`${type.h3} text-site-ink`}>{sub.title}</h3>
                  <Blocks part={sub} slots={slots} />
                </div>
              ))}
            </section>
          ))}

          <nav aria-label={guidesCopy.pagerLabel} data-pager className="mt-16 grid gap-4 border-t border-site-line pt-8 sm:grid-cols-2">
            {previous ? (
              <Link href={previous.href} rel="prev" className="rounded-2xl border border-site-line bg-site-card px-5 py-4 transition-colors hover:border-site-control">
                <span className="block text-xs text-site-faint">{guidesCopy.previous}</span>
                <span className="mt-1 block text-base font-medium text-site-ink">{previous.label}</span>
              </Link>
            ) : (
              <span />
            )}
            {next && (
              <Link href={next.href} rel="next" className="rounded-2xl border border-site-line bg-site-card px-5 py-4 transition-colors hover:border-site-control sm:text-right">
                <span className="block text-xs text-site-faint">{guidesCopy.next}</span>
                <span className="mt-1 block text-base font-medium text-site-ink">{next.label}</span>
              </Link>
            )}
          </nav>
        </article>
      </div>
    </Container>
  );
}
