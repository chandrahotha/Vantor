"use client";
import Shell from "../../components/Shell";
import Approvals from "../copilot/approvals";
import { AuthScreen, useBoot } from "../../components/ui";

/** The approval route's client half.
 *
 *  This file exists because `page.tsx` must stay a Server Component: Next
 *  resolves `metadata` on the server, and a `"use client"` module that also
 *  exports `metadata` fails the production build. So the gate lives here.
 *
 *  It owns the auth boundary for the route because the page renders its own
 *  chrome — without a gate here an unauthenticated visitor would see the
 *  approval workbench heading with nothing behind it. */
export default function ApprovalsRoute() {
  const { state, error, reload } = useBoot(async () => {});

  if (state !== "ok") return <AuthScreen state={state} error={error} onRetry={reload} />;

  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Approvals</h1>
          <p>
            Everything waiting on a decision from you. Rejecting one needs a written reason.
          </p>
        </div>
      </div>
      <Approvals />
    </Shell>
  );
}
