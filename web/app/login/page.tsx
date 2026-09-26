import type { Metadata } from "next";
import { LoginClient } from "@/components/PageClients";

export const metadata: Metadata = { title: "Sign in · Rook" };

// Sign-in is a stub until Supabase Google OAuth lands (ROOK-030); "Try the demo" works now.
export default function LoginPage() {
  return <LoginClient />;
}
