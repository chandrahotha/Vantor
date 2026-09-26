import type { Metadata } from "next";
import Governance from "./client";

export const metadata: Metadata = {
  title: "Governance",
  description:
    "Hash-chained audit trail with chain verification, catalog items, spending categories and hard budget ceilings that block over-budget approvals.",
  alternates: { canonical: "/governance" },
};

export default Governance;
