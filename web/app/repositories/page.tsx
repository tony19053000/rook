import type { Metadata } from "next";
import { RepositoriesClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Repositories · Rook" };

export default function RepositoriesPage() {
  return <RepositoriesClient />;
}
