"use client";

// The layout shell (04 §3.1, docs/mockups/4-web-app.html): a 260px sidebar, the main column and a sticky
// composer. Under 820px the sidebar becomes a drawer behind a hamburger button.

import { useEffect, useState, type ReactNode } from "react";
import { Sidebar, type SidebarProps } from "./Sidebar";

export interface AppShellProps extends Partial<SidebarProps> {
  children: ReactNode;
  /** Sticky at the bottom of the main column. */
  composer?: ReactNode;
  /** Shown above the chat column, e.g. the "Reconnecting…" banner. */
  banner?: ReactNode;
}

export function AppShell({ children, composer, banner, recents = [], coins = 0, userName = "guest", ...sidebar }: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="grid h-dvh grid-cols-1 bg-app text-ink min-[820px]:grid-cols-[260px_minmax(0,1fr)]">
      {drawerOpen && (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-20 bg-black/40 min-[820px]:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <div
        id="sidebar"
        className={`${drawerOpen ? "fixed inset-y-0 left-0 z-30 flex w-[260px]" : "hidden"} min-h-0 min-[820px]:static min-[820px]:flex`}
      >
        <Sidebar {...sidebar} recents={recents} coins={coins} userName={userName} />
      </div>

      <section className="relative flex min-h-0 flex-col" aria-label="Run">
        <div className="flex items-center gap-2 border-b border-line px-3 py-2 min-[820px]:hidden">
          <button
            type="button"
            aria-label="Open menu"
            aria-controls="sidebar"
            aria-expanded={drawerOpen}
            className="rounded-lg px-2 py-1 text-lg hover:bg-hover"
            onClick={() => setDrawerOpen(true)}
          >
            ☰
          </button>
          <span className="font-serif text-lg">Rook</span>
        </div>
        {banner}
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="mx-auto flex max-w-[760px] flex-col gap-2.5 px-5 pb-4 pt-7" aria-live="polite">
            {children}
          </div>
        </div>
        {composer && <div className="sticky bottom-0 bg-app px-5 pb-3.5 pt-2">{composer}</div>}
      </section>
    </div>
  );
}
