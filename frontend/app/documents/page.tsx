import type { Metadata } from "next";
import { DocumentsPage } from "../shared/modules";

export const metadata: Metadata = {
  title: "Documents",
  description:
    "Hash-verified document store for PDF, DOCX, XLSX and CSV with server-side text extraction, chunking and keyword search across the tenant.",
  alternates: { canonical: "/documents" },
};

export default DocumentsPage;
