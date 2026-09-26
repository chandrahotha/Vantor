import type { Metadata } from "next";
import { ContractsPage } from "../shared/modules";

export const metadata: Metadata = {
  title: "Contracts",
  description:
    "Contract repository with obligations, lifecycle transitions, expiry rolling, e-signature records and deterministic 11-dimension PO matching.",
  alternates: { canonical: "/contracts" },
};

export default ContractsPage;
