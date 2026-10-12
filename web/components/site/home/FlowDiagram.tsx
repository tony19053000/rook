import { flowDiagram } from "@/content/home";
import { flowSteps, type FlowStep } from "@/content/flow";
import { type } from "../tokens";

// The 6 steps as a diagram (06 §4 "How it works"): a real ordered list, so screen readers, 360 px screens and
// pages without JS get the same steps. The connectors are decoration (aria-hidden). Vertical on phones, a
// 3 x 2 grid on tablets, one row on wide screens. A server component.
// Colour says who does the step: the engine's steps are green (it decides), Bob's are blue.

const NODE = {
  engine: "border-site-good/40 bg-site-good/10 text-site-good",
  bob: "border-site-link/40 bg-site-link/10 text-site-link",
} as const;

const ACTOR: Record<string, string> = {
  Engine: "border-site-good/30 bg-site-good/10 text-site-good",
  Bob: "border-site-link/30 bg-site-link/10 text-site-link",
};
const ACTOR_OTHER = "border-site-strong bg-white/[0.04] text-site-ink";

export function FlowDiagram({ steps = flowSteps }: { steps?: FlowStep[] }) {
  return (
    <ol aria-label={flowDiagram.listLabel} data-flow-diagram className="grid gap-x-4 gap-y-0 sm:grid-cols-2 sm:gap-y-5 lg:grid-cols-3 xl:grid-cols-6 xl:gap-x-3">
      {steps.map((step, i) => {
        const actors = flowDiagram.actors[step.id] ?? [];
        const engine = actors.includes("Engine");
        return (
          <li key={step.id} data-step={step.id} className="relative flex gap-4 pb-8 last:pb-0 sm:block sm:pb-0">
            {/* Phones: a vertical line from this step's number to the next one. */}
            {i < steps.length - 1 && <span aria-hidden className="absolute top-10 bottom-0 left-[1.1875rem] w-px bg-site-strong sm:hidden" />}
            {/* One row (xl): a line from this number to the next. */}
            {i < steps.length - 1 && <span aria-hidden className="absolute top-5 left-[3.25rem] -right-3 hidden h-px bg-site-strong xl:block" />}
            <span
              aria-hidden
              className={`relative z-10 flex size-10 shrink-0 items-center justify-center rounded-[0.625rem] border font-mono text-sm font-medium ${engine ? NODE.engine : NODE.bob}`}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="sm:site-panel min-w-0 sm:mt-4 sm:flex sm:h-[calc(100%-3.5rem)] sm:flex-col sm:rounded-2xl sm:p-5">
              <h3 className={`${type.h3} text-site-ink`}>
                <span className="sr-only">Step {i + 1}: </span>
                {step.title}
              </h3>
              <p className={`${type.small} mt-2`}>{step.summary}</p>
              {actors.length > 0 && (
                <p className="mt-4 flex flex-wrap gap-1.5 sm:mt-auto sm:pt-5">
                  {actors.map((actor) => (
                    <span key={actor} className={`rounded-full border px-2 py-0.5 font-mono text-[0.6875rem] leading-4 ${ACTOR[actor] ?? ACTOR_OTHER}`}>
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
