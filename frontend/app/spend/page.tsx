import type { Metadata } from "next";
import { SpendPage } from "../shared/modules";

export const metadata: Metadata = {
  title: "Spend intelligence",
  description:
    "Spend analytics with leakage, maverick and concentration detection, per-currency ledger totals, PO price anomaly cases and a deterministic should-cost model.",
  alternates: { canonical: "/spend" },
};

export default SpendPage;
