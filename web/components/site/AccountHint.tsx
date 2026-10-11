"use client";

// The header's signed-in hint (06 §5): "Open workspace" instead of "Sign in" + "Try the demo" when this browser
// holds a Supabase session. It reads localStorage only (lib/authStorage.ts) and never loads auth-js or
// lib/session.ts, so the site pages stay light. The server render (and the first client render) is the
// signed-out CTAs; /app does the real session check.

import { useSyncExternalStore } from "react";
import { ButtonLink } from "./Button";
import { NavLinkItem } from "./NavLinkItem";
import { browserStorage, hasStoredSession } from "@/lib/authStorage";
import { cta } from "@/content/site";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange); // signed in or out in another tab
  return () => window.removeEventListener("storage", onChange);
}

const rememberedNow = () => hasStoredSession(browserStorage());
const signedOutOnServer = () => false;

/** Whether this browser remembers a signed-in session (false on the server and before hydration). */
export function useRemembersSignIn(): boolean {
  return useSyncExternalStore(subscribe, rememberedNow, signedOutOnServer);
}

/**
 * The header's right-hand CTAs. Both groups are always rendered in one grid cell and only their visibility
 * swaps, so the slot keeps the size of the wider group and nothing shifts when the hint turns on.
 */
export function HeaderAccountCtas() {
  const signedIn = useRemembersSignIn();
  const cell = "col-start-1 row-start-1 flex items-center justify-end gap-2";
  return (
    <div className="grid">
      <div data-account="signed-out" inert={signedIn || undefined} className={`${cell} ${signedIn ? "invisible" : ""}`}>
        {/* Wrapped: `hidden` on the link itself would lose to the button's own display class. */}
        <span className="hidden md:block">
          <ButtonLink href={cta.signIn.href} variant="ghost" size="sm">
            {cta.signIn.label}
          </ButtonLink>
        </span>
        <ButtonLink href={cta.demo.href} size="sm">
          {cta.demo.label}
        </ButtonLink>
      </div>
      <div data-account="signed-in" inert={!signedIn || undefined} className={`${cell} ${signedIn ? "" : "invisible"}`}>
        <ButtonLink href={cta.workspace.href} size="sm">
          {cta.workspace.label}
        </ButtonLink>
      </div>
    </div>
  );
}

/** The account entry of the mobile <details> menu: "Sign in", or "Open workspace" when signed in. */
export function MobileAccountLink({ className }: { className: string }) {
  return <NavLinkItem link={useRemembersSignIn() ? cta.workspace : cta.signIn} className={className} />;
}
