"use client";

/**
 * OIDC redirect target: `?code=…&state=…` in, session out.
 *
 * This route is the reason `AUTH_MODE=oidc` can now be used at all. Before it
 * existed the deployment shipped an identity provider, provisioned a public
 * PKCE client for it, and had nowhere for the browser to come back to.
 *
 * The URL is untrusted input by definition — anyone can craft a callback — so
 * every branch here has to end in a stated reason rather than a silent bounce:
 * the state check is what makes an injected code useless, and the verifier lives
 * only in this tab's sessionStorage.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { fetchAuthConfig, setSession } from "../../../lib/auth";
import { completeOidcSignIn, oidcReturnPath, oidcSession } from "../../../lib/oidc";

type Phase = "working" | "signed-in" | "failed";

function Callback() {
  const params = useSearchParams();
  const [phase, setPhase] = useState<Phase>("working");
  const [message, setMessage] = useState("");
  // React StrictMode runs effects twice in development; one exchange per code,
  // because an authorization code is single-use and the second attempt would
  // fail with `invalid_grant` and look like a broken login.
  const started = useRef(false);

  const run = useCallback(async () => {
    setPhase("working");
    setMessage("");
    const search = params?.toString() ?? "";
    try {
      // The token endpoint comes from the server's own configuration, not from
      // the URL that just arrived. A callback may carry a code; it may not
      // choose which address that code is posted to.
      const config = await fetchAuthConfig();
      if (!config.oidcProvider) throw new Error("This deployment does not offer identity-provider sign-in.");
      const tokens = await completeOidcSignIn(search, config.oidcProvider);
      setSession(oidcSession(tokens));
      setPhase("signed-in");
      const target = oidcReturnPath();
      // Whole-window navigation, not a router push: the app boot reads the
      // session on mount and a client-side push would land on a shell that has
      // already decided nobody is signed in.
      window.location.replace(target.startsWith("/") ? target : "/");
    } catch (e) {
      setPhase("failed");
      setMessage(e instanceof Error ? e.message : "Sign-in could not be completed.");
    }
  }, [params]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run();
  }, [run]);

  if (phase === "failed") {
    return (
      <main className="authscreen">
        <div className="authscreen-card" role="alert" aria-live="assertive">
          <div className="authscreen-badge">SIGN-IN</div>
          <h1 className="authscreen-title">Sign-in did not finish</h1>
          <p className="authscreen-sub">{message}</p>
          <div className="authscreen-actions">
            <button type="button" className="btn btn-primary btn-md" onClick={() => { started.current = false; void run(); }}>
              Try again
            </button>
            <Link className="btn btn-ghost btn-md" href="/">
              Back to the start
            </Link>
          </div>
          <p className="authscreen-note">
            If this keeps happening, check that this origin is listed in <code>WEB_ORIGINS</code>:
            the identity provider will not return to an address it has not been told about.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="authscreen">
      <div className="authscreen-card" role="status" aria-live="polite">
        <div className="authscreen-badge">SIGN-IN</div>
        <h1 className="authscreen-title">Finishing sign-in…</h1>
        <p className="authscreen-sub">Exchanging your credentials for a session.</p>
      </div>
    </main>
  );
}

export default function CallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="authscreen">
          <div className="authscreen-card" role="status">
            <h1 className="authscreen-title">Finishing sign-in…</h1>
          </div>
        </main>
      }
    >
      <Callback />
    </Suspense>
  );
}
