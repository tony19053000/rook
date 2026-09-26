import { notFound } from "next/navigation";
import { devPagesEnabled } from "@/lib/config";
import { DevSprites } from "./DevSprites";

// A dev-only story page: every agent sprite, agent rows (working and finished) and engine rows, with a
// reduced-motion toggle.
export default function DevSpritesPage() {
  if (!devPagesEnabled(process.env.NODE_ENV)) notFound();
  return <DevSprites />;
}
