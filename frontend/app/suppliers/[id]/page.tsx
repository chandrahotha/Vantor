import type { Metadata } from "next";
import SupplierDetail from "./client";

export const metadata: Metadata = {
  title: "Supplier",
  description: "Supplier 360: contacts, certifications, verification, scorecard and qualification state — every change audited.",
  robots: { index: false, follow: false },
};

/** Server wrapper so the detail page gets its own metadata. */
export default async function SupplierPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SupplierDetail id={id} />;
}
