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

// /contact (06 §5.9): the email, founder and website, mailto: links with prefilled subjects and GitHub Issues. Plain links, no form, so it
// works without JS and needs no backend. A server component.
export default function ContactPage() {
  return (
    <>
      <PageHeader eyebrow={contactCopy.eyebrow} heading={contactCopy.heading} lead={contactCopy.lead}>
        <dl className="mt-8 inline-grid max-w-full grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-5 gap-y-2.5 rounded-xl border border-site-strong bg-white/[0.03] px-4 py-3.5 text-base text-site-muted">
          <dt className={type.label}>{contactCopy.emailLabel}</dt>
          <dd>
            <a href={mailtoHref(contactCopy.emailSubject)} className={`${LINK} font-mono text-[0.9375rem]`} data-contact="email">
              {contactCopy.email}
            </a>
          </dd>
          <dt className={type.label}>{contactCopy.founderLabel}</dt>
          <dd>{contactCopy.founder}</dd>
          <dt className={type.label}>{contactCopy.websiteLabel}</dt>
          <dd>
            <a href={contactCopy.website} className={`${LINK} font-mono text-[0.9375rem]`} data-contact="website">
              {contactCopy.website}
            </a>
          </dd>
        </dl>
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
