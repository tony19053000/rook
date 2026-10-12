"use client";

// The home hero's scroll-driven parallax (06 §3, §5.1). Three decorative or illustrative layers move at
// different speeds as the hero scrolls away: the grid, the glow and the product figure. The hero text is a
// sibling of those layers, never inside one, so it never moves. Transform only.
// The server render and reduced motion get no style at all on the layers: the still, final page. (The
// app's useReducedMotion reports "reduced" on the server, so the first paint is always still.)

import { LazyMotion, domAnimation, m, useScroll, useTransform } from "motion/react";
import { useRef, type ReactNode } from "react";
import { Container } from "../Container";
import { useReducedMotion } from "@/lib/motion";

interface HeroParallaxProps {
  /** The id of the hero's h1, which names the region. */
  labelledBy: string;
  /** Eyebrow, h1, lead and CTAs: rendered outside every moving layer. */
  text: ReactNode;
  figure: ReactNode;
}

export function HeroParallax({ labelledBy, text, figure }: HeroParallaxProps) {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const gridY = useTransform(scrollYProgress, [0, 1], [0, 180]);
  const glowY = useTransform(scrollYProgress, [0, 1], [0, 110]);
  const glowScale = useTransform(scrollYProgress, [0, 1], [1, 1.2]);
  const figureY = useTransform(scrollYProgress, [0, 1], [0, -56]);

  return (
    <section ref={ref} aria-labelledby={labelledBy} data-hero className="relative isolate overflow-hidden">
      {/* Still decoration (not a parallax layer): a faint light from above the header. */}
      <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-[34rem]" />
      <LazyMotion features={domAnimation} strict>
        <m.div
          aria-hidden
          data-layer="grid"
          className="site-grid pointer-events-none absolute inset-x-0 -top-48 -bottom-48 -z-10"
          style={reduced ? undefined : { y: gridY }}
        />
        <m.div
          aria-hidden
          data-layer="glow"
          className="site-glow pointer-events-none absolute top-[26rem] left-1/2 -z-10 h-[26rem] w-[min(64rem,130vw)] -translate-x-1/2 sm:top-[30rem]"
          style={reduced ? undefined : { y: glowY, scale: glowScale }}
        />
        <Container className="pt-16 pb-20 sm:pt-24 sm:pb-28 lg:pt-28">
          <div data-hero-text className="mx-auto flex max-w-4xl flex-col items-center text-center xl:max-w-[70rem]">
            {text}
          </div>
          <m.div data-layer="figure" className="mt-14 sm:mt-20" style={reduced ? undefined : { y: figureY }}>
            {figure}
          </m.div>
        </Container>
      </LazyMotion>
    </section>
  );
}
