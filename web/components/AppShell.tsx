"use client";

// The layout shell (04 §3.1): a 280px sidebar (or a 52px icon rail when collapsed, remembered per browser),
// the main column and a sticky composer. Under 768px the sidebar is a drawer behind a menu button.

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import { Sidebar, type SidebarProps } from "./Sidebar";
import { browserStorage, readCollapsed, writeCollapsed } from "@/lib/sidebarPrefs";

export interface AppShellProps extends Partial<SidebarProps> {
  children: ReactNode;
  /** Sticky at the bottom of the main column. */
  composer?: ReactNode;
  /** Shown above the chat column, e.g. the "Reconnecting…" banner. */
  banner?: ReactNode;
}

export function AppShell({ children, composer, banner, recents = [], coins = 0, userName = "guest", collapsed: startCollapsed = false, ...sidebar }: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(startCollapsed);

  // Read after mount so the server render and the first client render agree.
  useEffect(() => {
    setCollapsed(readCollapsed(browserStorage()));
  }, []);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const onToggle = () => {
    if (drawerOpen) {
      setDrawerOpen(false);
      return;
    }
    setCollapsed((was) => {
      writeCollapsed(browserStorage(), !was);
      return !was;
    });
  };

  const rail = collapsed && !drawerOpen;
  return (
    <div className="flex h-dvh bg-app text-ink">
      {drawerOpen && (
        <button type="button" aria-label="Close menu" className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={() => setDrawerOpen(false)} />
      )}
      <div
        id="sidebar"
        data-collapsed={rail || undefined}
        className={`${drawerOpen ? "fixed inset-y-0 left-0 z-30 flex w-[280px] max-w-[85vw]" : "hidden"} min-h-0 flex-none md:static md:flex md:max-w-none md:transition-[width] md:duration-200 ${
          rail ? "md:w-[52px]" : "md:w-[280px]"
        }`}
      >
        <Sidebar {...sidebar} recents={recents} coins={coins} userName={userName} collapsed={rail} onToggle={onToggle} />
      </div>

      <section className="relative flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Main">
        <div className="flex items-center gap-1 px-2 py-2 md:hidden">
          <button
            type="button"
            aria-label="Open menu"
            aria-controls="sidebar"
            aria-expanded={drawerOpen}
            className="grid size-9 place-items-center rounded-lg text-muted hover:bg-hover hover:text-ink"
            onClick={() => setDrawerOpen(true)}
          >
            <Icon name="menu" size={18} />
          </button>
          <Link href="/" className="font-serif text-[20px] leading-none tracking-tight">
            Rook
          </Link>
          <Link href="/" aria-label="New run" className="ml-auto grid size-9 place-items-center rounded-lg text-muted hover:bg-hover hover:text-ink">
            <Icon name="plus" size={18} />
          </Link>
        </div>
        {banner}
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="mx-auto flex max-w-[760px] flex-col gap-2.5 px-5 pb-4 pt-7 md:pt-10" aria-live="polite">
            {children}
          </div>
        </div>
        {composer && <div className="sticky bottom-0 bg-app px-5 pb-4 pt-2">{composer}</div>}
      </section>
    </div>
  );
}
