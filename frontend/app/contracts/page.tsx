import type { Metadata } from "next";
import ContractsPage from "./client";

export const metadata: Metadata = {
  title: "Contracts",
  description: "Repository with obligations, lifecycle transitions, expiry rolling, e-sign records and deterministic PO matching.",
  alternates: { canonical: "/contracts" },
};

export default ContractsPage;