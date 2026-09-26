import Shell from "../components/Shell";
import { Skeleton } from "../components/ui";

/** Route-level loading state so navigation never shows a blank frame while the
 *  server component and its client island resolve. */
export default function Loading() {
  return (
    <Shell>
      <div className="pagehead"><div><h1>Loading</h1><p>Fetching data…</p></div></div>
      <Skeleton rows={5} label="Loading page" />
    </Shell>
  );
}
