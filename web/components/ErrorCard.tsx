// An inline error card (04 §3.6): a clear cause and the next step. The guest limit gets the install
// command for the CLI. Every string comes from lib/pages.errorView and is cleaned.

import { Button, Card, CardHeader, Pill } from "./cards/ui";
import { CLI_INSTALL, cleanErrorView, type ErrorView } from "@/lib/pages";

export function ErrorCard({ view, onRetry }: { view: ErrorView; onRetry?: () => void }) {
  const v = cleanErrorView(view);
  const limit = v.kind === "limit";
  return (
    <Card name="error" alert={!limit}>
      <CardHeader label={v.title} labelTone={limit ? undefined : "bad"} pill={<Pill tone={limit ? "warn" : "bad"}>{limit ? "? Limit" : "✗ Error"}</Pill>} />
      <p role="alert" data-error={v.kind} className="text-[14px]">
        {limit ? (
          <>
            Install the CLI to run on your own repos: <code className="rounded bg-sunk px-1.5 py-0.5 font-mono text-[13px]">{CLI_INSTALL}</code>
          </>
        ) : (
          v.message
        )}
      </p>
      {v.retryable && onRetry && (
        <div>
          <Button onClick={onRetry}>Try again</Button>
        </div>
      )}
    </Card>
  );
}
