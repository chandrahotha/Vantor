import { Suspense } from "react";
import type { Metadata } from "next";
import SuppliersClient from "./suppliers-client";

export const metadata: Metadata = {
  title: "Suppliers",
  description:
    "Supplier master with scorecards, certification, qualification and risk tiering. Server-paginated search and sort over real data.",
  alternates: { canonical: "/suppliers" },
};

/** `useSearchParams` needs a Suspense boundary to keep the route statically
 *  renderable; the boundary is also where the loading state belongs. */
export default function SuppliersPage() {
  return (
    <Suspense fallback={null}>
      <SuppliersClient />
    </Suspense>
  );
}
