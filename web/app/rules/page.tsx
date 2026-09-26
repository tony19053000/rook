import type { Metadata } from "next";
import { RulesClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Rules · Rook" };

export default function RulesPage() {
  return <RulesClient />;
}
