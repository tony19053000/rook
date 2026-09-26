import { notFound } from "next/navigation";
import { devPagesEnabled } from "@/lib/config";
import { DevStream } from "./DevStream";

// A dev-only page: the recorded minishop run streamed through the real SSE client and runStore, from an
// in-browser fake server that drops the connection twice (to show resume + de-duplication).
export default function DevStreamPage() {
  if (!devPagesEnabled(process.env.NODE_ENV)) notFound();
  return <DevStream />;
}
