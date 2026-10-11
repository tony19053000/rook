import type { Metadata } from "next";
import { HomeClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Workspace" };

// The app home at /app (04 §3.2, 06 §1): the greeting and the composer with the repo picker; sending creates a run.
export default function AppHomePage() {
  return <HomeClient />;
}
