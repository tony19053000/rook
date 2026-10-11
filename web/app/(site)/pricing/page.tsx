import type { Metadata } from "next";
import { PricingView } from "@/components/site/PricingView";
import { plans, pricingCopy } from "@/content/pricing";

export const metadata: Metadata = { title: pricingCopy.title, description: pricingCopy.description };

export default function PricingPage() {
  return <PricingView plans={plans} />;
}
