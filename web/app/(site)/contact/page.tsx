import type { Metadata } from "next";
import { Card } from "@/components/site/Card";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { link, type } from "@/components/site/tokens";
import { contactChannels, contactCopy, type ContactLink } from "@/content/contact";
import { mailtoHref } from "@/content/site";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(contactCopy.title, contactCopy.description, "/contact");

const LINK = `${link} break-words`;

function ChannelLink({ id, link }: { id: string; link: ContactLink }) {
  if (link.kind === "email") {
    return (
      <a href={mailtoHref(link.subject)} className={LINK} data-channel={id}>
        {link.label}
      </a>
    );
  }
  return (
    <a href={link.href} className={LINK} data-channel={id} rel="noopener noreferrer">
      {link.label}
    </a>
  );
}

// /contact (06 §5.9): mailto: links with prefilled subjects and GitHub Issues. Plain links, no form, so it
// works without JS and needs no backend. A server component.
export default function ContactPage() {
  return (
    <>
      <PageHeader eyebrow={contactCopy.eyebrow} heading={contactCopy.heading} lead={contactCopy.lead}>
        <p className="mt-8 inline-flex max-w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-site-strong bg-white/[0.03] px-4 py-3 text-base text-site-muted">
          <span className={type.label}>{contactCopy.emailLabel}:</span>{" "}
          <a href={mailtoHref(contactCopy.emailSubject)} className={`${LINK} font-mono text-[0.9375rem]`}>
            {contactCopy.email}
          </a>
        </p>
      </PageHeader>

      <Section id="channels" title={contactCopy.channelsTitle} width="narrow">
        <ul className="grid gap-4 sm:grid-cols-2">
          {contactChannels.map((channel) => (
            <Card as="li" key={channel.id} className="flex flex-col">
              <h3 className={`${type.h3} text-site-ink`}>{channel.title}</h3>
              <p className={`${type.small} mt-2 flex-1`}>{channel.body}</p>
              <p className="mt-5 text-[0.9375rem]">
                <ChannelLink id={channel.id} link={channel.link} />
              </p>
            </Card>
          ))}
        </ul>
      </Section>

      <Section id="expect" title={contactCopy.expectTitle} width="narrow" className="pb-10 sm:pb-16">
        <ul className="site-list text-base leading-[1.7] text-site-muted">
          {contactCopy.expect.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}
