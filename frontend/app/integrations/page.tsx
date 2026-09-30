import type { Metadata } from "next";
import Integrations from "./client";

/** The metadata here used to be a verbatim copy of the negotiation simulator's:
 *  the browser tab, the document description and the canonical URL on the
 *  Integrations route all claimed to be `/negosim`. The default import was even
 *  bound to the name `NegoSim` while resolving to this folder's own client. */
export const metadata: Metadata = {
  title: "Integrations",
  description:
    "ERP and ecosystem adapters with signed webhook endpoints, delivery history and secret references held outside the database.",
  alternates: { canonical: "/integrations" },
};

export default Integrations;
