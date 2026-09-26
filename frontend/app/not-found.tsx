import Link from "next/link";
import Shell from "../components/Shell";
import { Empty } from "../components/ui";

export default function NotFound() {
  return (
    <Shell>
      <div className="pagehead">
        <div>
          <h1>Page not found</h1>
          <p>That route does not exist in VANTOR.</p>
        </div>
      </div>
      <Empty title="Nothing here" hint="Use the sidebar, or press Ctrl+K to jump anywhere." />
      <p style={{ marginTop: 16 }}>
        <Link href="/">Back to dashboard</Link>
      </p>
    </Shell>
  );
}
