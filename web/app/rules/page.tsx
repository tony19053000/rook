import type { Metadata } from "next";
import { RulesClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Rules" };

export default function RulesPage() {
  return <RulesClient />;
}
