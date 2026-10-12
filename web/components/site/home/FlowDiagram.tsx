import { flowDiagram } from "@/content/home";
import { flowSteps, type FlowStep } from "@/content/flow";
import { type } from "../tokens";

// The 6 steps as a diagram (06 §4 "How it works"): a real ordered list, so screen readers, 360 px screens and
// pages without JS get the same steps. The connectors are decoration (aria-hidden). Vertical on phones, a
// 3 x 2 grid on tablets, one row on wide screens. A server component.
export function FlowDiagram({ steps = flowSteps }: { steps?: FlowStep[] }) {
  return (
    <ol aria-label={flowDiagram.listLabel} data-flow-diagram className="grid gap-x-4 gap-y-0 sm:grid-cols-2 sm:gap-y-4 lg:grid-cols-3 xl:grid-cols-6">
      {steps.map((step, i) => {
        const actors = flowDiagram.actors[step.id] ?? [];
        const engine = actors.includes("Engine");
        return (
          <li key={step.id} data-step={step.id} className="relative flex gap-4 pb-8 sm:block sm:pb-0">
            {/* Phones: a vertical line from this step's number to the next one. */}
            {i < steps.length - 1 && <span aria-hidden className="absolute top-10 bottom-0 left-[1.1875rem] w-px bg-site-line sm:hidden" />}
            {/* One row (xl): a line from this number to the next. */}
            {i < steps.length - 1 && <span aria-hidden className="absolute top-5 left-12 -right-4 hidden h-px bg-site-line xl:block" />}
            <span
              aria-hidden
              className={`relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full border font-mono text-sm font-semibold ${
                engine ? "border-site-good/50 bg-site-good/10 text-site-good" : "border-site-accent/50 bg-site-accent/10 text-site-accent"
              }`}
            >
              {i + 1}
            </span>
            <div className="min-w-0 sm:mt-4 sm:h-[calc(100%-3.5rem)] sm:rounded-2xl sm:border sm:border-site-line sm:bg-site-card sm:p-5">
              <h3 className={`${type.h3} text-site-ink`}>
                <span className="sr-only">Step {i + 1}: </span>
                {step.title}
              </h3>
              <p className={`${type.small} mt-1.5`}>{step.summary}</p>
              {actors.length > 0 && (
                <p className="mt-3 flex flex-wrap gap-1.5">
                  {actors.map((actor) => (
                    <span key={actor} className="rounded-full border border-site-line bg-site-raised px-2 py-0.5 font-mono text-[0.6875rem] text-site-muted">
                      {actor}
                    </span>
                  ))}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
