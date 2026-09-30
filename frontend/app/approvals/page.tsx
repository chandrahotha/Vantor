import type { Metadata } from "next";
import ApprovalsRoute from "./ApprovalsRoute";

export const metadata: Metadata = {
  title: "Approvals",
  description:
    "Every approval waiting on a human decision, ordered by the tier it must be decided in, with the written reason a rejection requires.",
  alternates: { canonical: "/approvals" },
};

/** The approval queue as a first-class route.
 *
 * VNT-045. This queue is the most-used surface in the product for anyone whose
 * job is approving spend, and it had no route at all: it rendered only inside
 * the copilot page, so reaching it meant navigating to the AI chat and scrolling
 * past the conversation. A control that governs money should not be filed under
 * a feature it has nothing to do with.
 *
 * This module stays a Server Component because `metadata` is resolved on the
 * server; the route body, including the auth gate, lives in `ApprovalsRoute`.
 *
 * The copilot page no longer mounts the queue as well. Two mounts meant two
 * independent auth boots, two polls of the same endpoint, and two live copies
 * of a screen that governs money — one of them filed under the AI assistant.
 * The copilot now links here instead. */
export default function ApprovalsPage() {
  return <ApprovalsRoute />;
}
