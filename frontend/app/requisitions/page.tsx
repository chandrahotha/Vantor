import type { Metadata } from "next";
import Requisitions from "./client";

export const metadata: Metadata = {
  title: "Requisitions",
  description: "Demand capture: requisitions with approval-tier seeding on submit, before any purchase order can exist.",
  alternates: { canonical: "/requisitions" },
};

export default Requisitions;