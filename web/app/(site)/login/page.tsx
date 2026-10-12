import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/Container";
import { LogoMark } from "@/components/site/Logo";
import { SignInPanel } from "@/components/site/SignInPanel";
import { link } from "@/components/site/tokens";
import { loginCopy } from "@/content/login";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(loginCopy.title, loginCopy.description, "/login");

// /login (06 §7): the URL is in the Supabase redirect allowlist, so it never moves. The page is a server
// component; only the sign-in control is a client island, and nothing calls the API on load.
// One centred column that fills the first screen: the mark, the heading, the sign-in card, then the small print.
export default function LoginPage() {
  return (
    <div className="relative isolate">
      <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-[28rem]" />
      <div aria-hidden className="site-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[44rem]" />
      <Container width="narrow" className="flex min-h-[calc(100vh-3.75rem)] flex-col items-center justify-center py-16 sm:py-20">
        <div className="flex w-full max-w-[26rem] flex-col items-center text-center">
          <LogoMark size={52} />
          <h1 className="mt-8 font-serif text-[2.5rem] leading-[1.08] font-normal tracking-[-0.022em] text-balance text-site-ink sm:text-5xl">
            {loginCopy.heading}
          </h1>
          <p className="mt-5 text-[1.0625rem] leading-relaxed text-pretty text-site-muted">{loginCopy.lead}</p>

          <div className="site-panel mt-10 w-full rounded-2xl p-5 text-left sm:p-6">
            <SignInPanel />
          </div>

          <p className="mt-8 text-sm leading-relaxed text-site-faint">
            {loginCopy.guestNote}{" "}
            <Link href={loginCopy.cliLink.href} className={link}>
              {loginCopy.cliLink.label}
            </Link>
          </p>
          <ul className="mt-6 flex items-center gap-5 text-xs text-site-faint">
            {loginCopy.legal.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="underline decoration-site-strong underline-offset-4 transition-colors hover:text-site-ink">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </Container>
    </div>
  );
}
