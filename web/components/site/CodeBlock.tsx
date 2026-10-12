// A command or code sample. Long lines wrap, so a 360 px screen never scrolls sideways.

import { REPO_FILE_ATTR } from "@/lib/verbatim";

interface CodeBlockProps {
  code: string;
  label?: string;
  prompt?: boolean;
  /** The code is a whole file of the Rook repo, unchanged (lib/verbatim.ts: the tests compare it with the file). */
  repoFile?: boolean;
}

export function CodeBlock({ code, label, prompt = false, repoFile = false }: CodeBlockProps) {
  return (
    <figure className="overflow-hidden rounded-xl border border-site-line bg-site-raised shadow-[inset_0_1px_0_rgb(255_255_255/0.03)]">
      {label && (
        <figcaption className="flex items-center gap-3 border-b border-site-line bg-white/[0.02] px-4 py-2.5 font-mono text-xs break-words text-site-faint">
          <span aria-hidden className="hidden flex-none gap-1.5 sm:flex">
            <span className="size-2 rounded-full bg-site-strong" />
            <span className="size-2 rounded-full bg-site-strong" />
            <span className="size-2 rounded-full bg-site-strong" />
          </span>
          <span className="min-w-0">{label}</span>
        </figcaption>
      )}
      <pre className="px-4 py-3.5 font-mono text-[0.8125rem] leading-[1.7] whitespace-pre-wrap break-words text-site-ink">
        <code {...(repoFile ? { [REPO_FILE_ATTR]: "" } : {})}>
          {prompt && (
            <span aria-hidden className="mr-2.5 select-none text-site-accent">
              $
            </span>
          )}
          {code}
        </code>
      </pre>
    </figure>
  );
}
