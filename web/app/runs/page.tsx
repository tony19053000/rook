import type { Metadata } from "next";
import { RunsClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return <RunsClient />;
}
