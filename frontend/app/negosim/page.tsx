import type { Metadata } from "next";
import NegoSim from "./client";

export const metadata: Metadata = {
  title: "Negotiation simulator",
  description: "Deterministic negotiation rehearsal with concession ladder and walk-away floor — simulation only, never touches live procurement data.",
  alternates: { canonical: "/negosim" },
};

export default NegoSim;