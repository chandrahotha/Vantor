import type { Metadata } from "next";
import Approvals from "../copilot/approvals";
import Shell from "../../components/Shell";

export const metadata: Metadata = {
  title: "Approvals",
  description:
    "Every approval waiting on a human decision, ordered by the tier it must be decided in, with the written reason a rejection requires.",
  alternates: { canonical: "/approvals" },
};

/** The approval queue as a first-class route.
 *
 * VNT-045. This queue is the most-used surface in the product for anyone whose
 * job is approving spend, and it had no route at all: it rendered only inside the
 * copilot page, so reaching it meant navigating to the AI chat and scrolling past
 * the conversation. A control that governs money should not be filed under a
 * feature it has nothing to do with.
 *
 * The component is the existing one, unchanged, so the two renderings cannot
 * drift. The one the copilot page still mounts is left in place — removing it
 * would delete UI that some people navigate to directly, and the point here was
 * that the surface was missing, not that it was duplicated. */
export default function ApprovalsPage() {
  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Approvals</h1>
          <p>
            Executive approval workbench: pending purchase requisitions, capital expenditure thresholds,
            and contract signing authorities requiring governance sign-off.
          </p>
        </div>
      </div>
      <Approvals />
    </Shell>
  );
}
