import type { Metadata } from "next";
import { GithubSetupClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Connect GitHub · Rook" };

// The GitHub App's Setup URL (ROOK-031): GitHub sends the browser here after the install.
export default function GithubSetupPage() {
  return <GithubSetupClient />;
}
