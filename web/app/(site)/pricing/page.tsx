import type { Metadata } from "next";
import { PricingView } from "@/components/site/PricingView";
import { plans, pricingCopy } from "@/content/pricing";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(pricingCopy.title, pricingCopy.description, "/pricing");

export default function PricingPage() {
  return <PricingView plans={plans} />;
}
