import type { Metadata } from "next";
import { Card } from "@/components/site/Card";
import { Container } from "@/components/site/Container";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { type } from "@/components/site/tokens";
import { contactChannels, contactCopy, type ContactLink } from "@/content/contact";
import { mailtoHref } from "@/content/site";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(contactCopy.title, contactCopy.description, "/contact");

const LINK = "text-site-link underline underline-offset-4 break-words";

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
      <PageHeader eyebrow={contactCopy.eyebrow} heading={contactCopy.heading} lead={contactCopy.lead} />
      <Container width="narrow" className="mt-6">
        <p className={type.body}>
          {contactCopy.emailLabel}:{" "}
          <a href={mailtoHref(contactCopy.emailSubject)} className={LINK}>
            {contactCopy.email}
          </a>
        </p>
      </Container>

      <Section id="channels" title={contactCopy.channelsTitle} width="narrow">
        <ul className="grid gap-4">
          {contactChannels.map((channel) => (
            <Card as="li" key={channel.id}>
              <h3 className={`${type.h3} text-site-ink`}>{channel.title}</h3>
              <p className={`${type.small} mt-2`}>{channel.body}</p>
              <p className="mt-4 text-sm">
                <ChannelLink id={channel.id} link={channel.link} />
              </p>
            </Card>
          ))}
        </ul>
      </Section>

      <Section id="expect" title={contactCopy.expectTitle} width="narrow">
        <ul className="flex list-disc flex-col gap-3 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint">
          {contactCopy.expect.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}
