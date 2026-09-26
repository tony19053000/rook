import { AppShell } from "@/components/AppShell";
import { Composer } from "@/components/Composer";

// Home (04 §3.2). Creating a run from the composer arrives with ROOK-036.
export default function HomePage() {
  return (
    <AppShell composer={<Composer />}>
      <div className="flex items-center justify-center gap-3 pt-16">
        <span aria-hidden className="size-7 rounded-full bg-accent" />
        <h1 className="font-serif text-[30px] font-normal tracking-tight">What should we try to break today?</h1>
      </div>
      <p className="text-center text-muted">Pick a repository. Rook finds the shortest way to break its rules, then proves the fix.</p>
    </AppShell>
  );
}
