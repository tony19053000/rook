/** Text with `code spans` between backticks (a diagnosis as the Detective writes it, a command in a guide). */
export function InlineCode({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="rounded bg-site-raised px-1 py-0.5 font-mono text-[0.9em] break-words text-site-ink">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
