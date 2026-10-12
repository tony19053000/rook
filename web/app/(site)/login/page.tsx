import type { Metadata } from "next";
import Link from "next/link";
import { Card } from "@/components/site/Card";
import { Container } from "@/components/site/Container";
import { SignInPanel } from "@/components/site/SignInPanel";
import { space, type } from "@/components/site/tokens";
import { loginCopy } from "@/content/login";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(loginCopy.title, loginCopy.description, "/login");

// /login (06 §7): the URL is in the Supabase redirect allowlist, so it never moves. The page is a server
// component; only the sign-in control is a client island, and nothing calls the API on load.
export default function LoginPage() {
  return (
    <Container width="narrow" className={space.pageTop}>
      <Card className="mx-auto flex max-w-md flex-col gap-6 sm:p-8">
        <div>
          <h1 className={`${type.h2} text-site-ink`}>{loginCopy.heading}</h1>
          <p className={`${type.body} mt-3`}>{loginCopy.lead}</p>
        </div>
        <SignInPanel />
        <p className={type.small}>
          {loginCopy.guestNote}{" "}
          <Link href={loginCopy.cliLink.href} className="text-site-link underline underline-offset-4">
            {loginCopy.cliLink.label}
          </Link>
        </p>
      </Card>
    </Container>
  );
}
