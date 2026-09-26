import type { Metadata } from "next";
import { RunClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Run · Rook" };

// The live run (04 §3.2). The id comes from the URL; the server checks the owner on every call.
export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RunClient runId={id} />;
}
