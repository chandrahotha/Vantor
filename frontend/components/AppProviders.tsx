"use client";
import type { ReactNode } from "react";
import { ToastProvider } from "./ui";

/** Client boundary that mounts the toast region above every page.
 *
 *  It has to live here, in the root layout, rather than inside `Shell`: a page
 *  calls `useToast()` during its own render, and `Shell` is rendered *by* the
 *  page, so a provider inside `Shell` would be a descendant of its own consumer
 *  and every toast would go to the context's no-op default. */
export default function AppProviders({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>;
}
