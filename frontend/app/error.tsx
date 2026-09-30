"use client";
import Link from "next/link";

/** Route-level error boundary. Every page needs one: without it a thrown render
 *  error shows the browser's default blank page with no way back into the app. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    // Not `.shell`: that is a two-column grid whose first track is the fixed
    // 248px sidebar. With `<main>` as the only child the whole error page was
    // laid out inside that 248px column — a wall of wrapped text down the left
    // edge of an otherwise empty screen, on the one screen a user reaches when
    // something has already gone wrong. This boundary renders outside the app
    // chrome (the shell's client islands are what may have thrown), so it gets
    // a plain centred column of its own.
    <div className="errorpage">
      <main className="main errorpage-main" id="main">
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
