import type { Metadata } from "next";
import { CounterexamplesClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Counterexamples · Rook" };

export default function CounterexamplesPage() {
  return <CounterexamplesClient />;
}
