// A command or code sample. Long lines wrap, so a 360 px screen never scrolls sideways.

export function CodeBlock({ code, label, prompt = false }: { code: string; label?: string; prompt?: boolean }) {
  return (
    <figure className="overflow-hidden rounded-xl border border-site-line bg-site-raised">
      {label && (
        <figcaption className="border-b border-site-line px-4 py-2 font-mono text-xs text-site-faint">{label}</figcaption>
      )}
      <pre className="px-4 py-3 font-mono text-sm leading-relaxed whitespace-pre-wrap break-words text-site-ink">
        <code>
          {prompt && (
            <span aria-hidden className="mr-2 select-none text-site-faint">
              $
            </span>
          )}
          {code}
        </code>
      </pre>
    </figure>
  );
}
