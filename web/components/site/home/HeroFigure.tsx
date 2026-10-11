import { heroFigure } from "@/content/home";

// The hero's product figure (06 §5.1): a still illustration of a Rook result, captioned as an illustration.
// A server component; HeroParallax only moves the layer it sits in.
export function HeroFigure() {
  const f = heroFigure;
  return (
    <figure className="mx-auto w-full max-w-3xl lg:max-w-5xl 2xl:max-w-6xl">
      <div className="overflow-hidden rounded-2xl border border-site-line bg-site-card/90 shadow-[0_30px_120px_-40px_rgba(255,106,77,0.45)] backdrop-blur">
        <div className="flex items-center gap-2 border-b border-site-line px-4 py-3">
          <span aria-hidden className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-site-line" />
            <span className="size-2.5 rounded-full bg-site-line" />
            <span className="size-2.5 rounded-full bg-site-line" />
          </span>
          <span className="ml-2 font-mono text-xs text-site-faint">rook</span>
        </div>
        <div className="flex flex-col gap-5 p-5 sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-mono text-xs font-medium uppercase tracking-[0.12em] text-site-accent">{f.title}</span>
            <span className="rounded-full border border-site-accent/40 bg-site-accent/10 px-2.5 py-0.5 font-mono text-xs font-medium text-site-accent">
              <span aria-hidden>✗ </span>
              {f.status}
            </span>
          </div>
          <p className="text-base font-semibold text-site-ink sm:text-lg">{f.rule}</p>
          <ol className="flex flex-wrap items-center gap-2 font-mono text-sm" aria-label="Minimal steps">
            {f.steps.map((step, i) => (
              <li key={step} className="flex items-center gap-2">
                {i > 0 && (
                  <span aria-hidden className="text-site-faint">
                    →
                  </span>
                )}
                <span className="rounded-lg border border-site-line bg-site-raised px-3 py-1.5 text-site-ink">
                  <span className="mr-2 text-site-faint">{i + 1}</span>
                  {step}
                </span>
              </li>
            ))}
          </ol>
          <dl className="grid grid-cols-2 gap-3">
            {f.observed.map((o, i) => (
              <div key={o.label} className="rounded-xl border border-site-line bg-site-raised px-4 py-3">
                <dt className="font-mono text-xs uppercase tracking-[0.12em] text-site-faint">{o.label}</dt>
                <dd className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${i === f.observed.length - 1 ? "text-site-accent" : "text-site-ink"}`}>
                  {o.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-sm text-site-good">
            <span>
              <span aria-hidden>✓ </span>
              {f.replayed}
            </span>
            <span>
              <span aria-hidden>✓ </span>
              {f.test}
            </span>
          </p>
        </div>
      </div>
      <figcaption className="mt-3 text-center font-mono text-xs text-site-faint">{f.caption}</figcaption>
    </figure>
  );
}
