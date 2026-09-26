export function Badge({ tone, children }: { tone?: "ok" | "warn" | "bad" | "info"; children: React.ReactNode }) {
  return <span className={`badge${tone ? ` ${tone}` : ""}`}>{children}</span>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty" role="status">
      <div style={{ fontWeight: 700, color: "#0f172a" }}>{title}</div>
      {hint ? <div style={{ marginTop: 6 }}>{hint}</div> : null}
    </div>
  );
}

export function ErrorBox({ message, requestId }: { message: string; requestId?: string }) {
  return (
    <div className="error" role="alert">
      <div>{message}</div>
      {requestId ? <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>request {requestId}</div> : null}
    </div>
  );
}
