"use client";
import Link from "next/link";

/** Route-level error boundary. Every page needs one: without it a thrown render
 *  error shows the browser's default blank page with no way back into the app. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="shell">
      <main className="main" id="main">
        <div className="pagehead">
          <div>
            <h1>Something broke</h1>
            <p>This view failed to render. Your data is unaffected.</p>
          </div>
        </div>
        <div className="error" role="alert">
          <div>{error.message || "Unexpected error."}</div>
          {error.digest ? <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>digest {error.digest}</div> : null}
        </div>
        <div className="toolbar" style={{ marginTop: 16 }}>
          <button onClick={reset}>Try again</button>
          <Link href="/">Back to dashboard</Link>
        </div>
      </main>
    </div>
  );
}
