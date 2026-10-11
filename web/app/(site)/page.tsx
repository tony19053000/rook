import { ButtonLink } from "@/components/site/Button";
import { Container } from "@/components/site/Container";
import { type } from "@/components/site/tokens";
import { homeHero } from "@/content/home";
import { cta } from "@/content/site";

// The marketing home (06 §5.1). ROOK-044 adds the parallax hero, the walkthrough and the sections.
export default function HomePage() {
  return (
    <Container className="pt-20 pb-24 sm:pt-28 sm:pb-32">
      <p className={type.eyebrow}>{homeHero.eyebrow}</p>
      <h1 className={`${type.display} mt-5 max-w-4xl text-site-ink`}>{homeHero.heading}</h1>
      <p className={`${type.lead} mt-6 max-w-2xl`}>{homeHero.lead}</p>
      <div className="mt-10 flex flex-wrap gap-3">
        <ButtonLink href={cta.demo.href} size="lg">
          {cta.demo.label}
        </ButtonLink>
        <ButtonLink href={cta.signIn.href} variant="secondary" size="lg">
          {cta.signIn.label}
        </ButtonLink>
      </div>
    </Container>
  );
}
