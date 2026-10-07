/** Standalone Demo Data provider for Vantor Web.
 * Allows full offline and preview exploration of the dashboard and procurement workflows
 * without requiring a running backend server.
 */

import { Session, getSession } from "./auth";

export function isDemoSession(): boolean {
  if (typeof window === "undefined") return false;
  const s = getSession();
  if (s?.persona === "demo" || s?.token === "vantor-demo-token-active") return true;
  return localStorage.getItem("vantor.demo") === "true";
}

export function setDemoFlag(enabled: boolean) {
  if (typeof localStorage === "undefined") return;
  if (enabled) {
    localStorage.setItem("vantor.demo", "true");
  } else {
    localStorage.removeItem("vantor.demo");
  }
}

export function getDemoSession(persona?: string): Session {
  return {
    token: "vantor-demo-token-active",
    name: persona ? (persona.charAt(0).toUpperCase() + persona.slice(1)) : "Operator (Demo)",
    tenant: "vantor-enterprise-demo",
    roles: ["admin", "buyer", "approver", "finance", "auditor"],
    expiresAt: Date.now() + 24 * 60 * 60 * 1000,
    persona: "demo",
  };
}

export function getDemoResponse<T>(path: string, _init?: any): { data: T; pagination: any; requestId: string } {
  const reqId = `demo-${Date.now().toString(36)}`;
  const cleanPath = path.split("?")[0];

  // 1. Spend Summary
  if (cleanPath.includes("/spend/summary")) {
    const summary = {
      poTotalMinor: 148500000,
      invoicedTotalMinor: 112300000,
      savedMinor: 14200000,
      currencyCount: 1,
      totalsArePerCurrency: true,
      byCurrency: {
        committed: { USD: 148500000 },
        invoiced: { USD: 112300000 },
        saved: { USD: 14200000 },
      },
    };
    return { data: summary as unknown as T, pagination: null, requestId: reqId };
  }

  // 2. Contracts
  if (cleanPath.includes("/contracts")) {
    const contracts = [
      { id: "cnt-1", code: "CNT-2026-001", title: "Enterprise Cloud Hosting & Compute", status: "active", endDate: "2026-11-15", supplierName: "Apex Logistics Global", supplierId: "sup-1", valueMinor: 48000000 },
      { id: "cnt-2", code: "CNT-2026-002", title: "Facilities Management & Cleaning", status: "active", endDate: "2026-12-31", supplierName: "CleanCorp Facilities", supplierId: "sup-2", valueMinor: 12000000 },
      { id: "cnt-3", code: "CNT-2026-003", title: "Global Freight & Customs Brokerage", status: "expiring", endDate: "2026-10-25", supplierName: "TransOcean Cargo", supplierId: "sup-3", valueMinor: 35000000 },
      { id: "cnt-4", code: "CNT-2026-004", title: "Office IT Equipment Hardware Lease", status: "active", endDate: "2027-03-01", supplierName: "TechEquip Systems", supplierId: "sup-4", valueMinor: 8500000 },
      { id: "cnt-5", code: "CNT-2026-005", title: "Packaging Materials Annual Agreement", status: "active", endDate: "2027-06-30", supplierName: "PackWell Solutions", supplierId: "sup-5", valueMinor: 21000000 },
    ];
    return { data: contracts as unknown as T, pagination: { limit: 100, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 3. Purchase Orders
  if (cleanPath.includes("/purchase-orders")) {
    const pos = [
      { id: "po-1", code: "PO-2026-101", status: "approved", totalMinor: 4850000, currency: "USD", supplierId: "sup-1", supplierName: "Apex Logistics Global", lines: [{ id: "pol-1", lineNo: 1, description: "Compute Capacity Node A", quantity: 10, unitPriceMinor: 485000, lineTotalMinor: 4850000 }] },
      { id: "po-2", code: "PO-2026-102", status: "sent", totalMinor: 12500000, currency: "USD", supplierId: "sup-3", supplierName: "TransOcean Cargo", lines: [{ id: "pol-2", lineNo: 1, description: "Ocean Freight 40ft TEU", quantity: 5, unitPriceMinor: 2500000, lineTotalMinor: 12500000 }] },
      { id: "po-3", code: "PO-2026-103", status: "delivered", totalMinor: 3200000, currency: "USD", supplierId: "sup-5", supplierName: "PackWell Solutions", lines: [{ id: "pol-3", lineNo: 1, description: "Recycled Corrugated Boxes", quantity: 2000, unitPriceMinor: 1600, lineTotalMinor: 3200000 }] },
      { id: "po-4", code: "PO-2026-104", status: "draft", totalMinor: 750000, currency: "USD", supplierId: "sup-4", supplierName: "TechEquip Systems", lines: [{ id: "pol-4", lineNo: 1, description: "Ergonomic Keyboards & Docks", quantity: 15, unitPriceMinor: 50000, lineTotalMinor: 750000 }] },
      { id: "po-5", code: "PO-2026-105", status: "approved", totalMinor: 6400000, currency: "USD", supplierId: "sup-2", supplierName: "CleanCorp Facilities", lines: [{ id: "pol-5", lineNo: 1, description: "Quarterly Deep Sanitize", quantity: 1, unitPriceMinor: 6400000, lineTotalMinor: 6400000 }] },
    ];
    return { data: pos as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 4. RFQs
  if (cleanPath.includes("/rfqs")) {
    const rfqs = [
      { id: "rfq-1", code: "RFQ-2026-042", title: "Global Logistics Freight Forwarding (2027)", status: "sent", supplierCount: 4, responseCount: 3 },
      { id: "rfq-2", code: "RFQ-2026-043", title: "Office Laptop Fleet Refresh", status: "response", supplierCount: 3, responseCount: 3 },
      { id: "rfq-3", code: "RFQ-2026-044", title: "Corrugated Packaging Supply Contract", status: "draft", supplierCount: 2, responseCount: 0 },
    ];
    return { data: rfqs as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 5. Suppliers
  if (cleanPath.includes("/suppliers")) {
    const suppliers = [
      { id: "sup-1", code: "SUP-001", name: "Apex Logistics Global", status: "active", country: "US", currency: "USD", riskTier: "low" },
      { id: "sup-2", code: "SUP-002", name: "CleanCorp Facilities", status: "active", country: "US", currency: "USD", riskTier: "low" },
      { id: "sup-3", code: "SUP-003", name: "TransOcean Cargo", status: "active", country: "SG", currency: "USD", riskTier: "medium" },
      { id: "sup-4", code: "SUP-004", name: "TechEquip Systems", status: "active", country: "DE", currency: "EUR", riskTier: "low" },
      { id: "sup-5", code: "SUP-005", name: "PackWell Solutions", status: "active", country: "US", currency: "USD", riskTier: "low" },
      { id: "sup-6", code: "SUP-006", name: "CyberShield Security Ltd", status: "active", country: "GB", currency: "GBP", riskTier: "low" },
    ];
    return { data: suppliers as unknown as T, pagination: { limit: 15, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 6. Requisitions
  if (cleanPath.includes("/requisitions")) {
    const reqs = [
      { id: "req-1", code: "REQ-2026-089", title: "Data Center Cooling Modernization", status: "approved", totalMinor: 14500000, currency: "USD" },
      { id: "req-2", code: "REQ-2026-090", title: "Q4 Customer Care Headsets", status: "submitted", totalMinor: 890000, currency: "USD" },
      { id: "req-3", code: "REQ-2026-091", title: "Warehouse Pallet Jack Replacements", status: "draft", totalMinor: 3200000, currency: "USD" },
    ];
    return { data: reqs as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 7. Approvals
  if (cleanPath.includes("/approvals")) {
    const approvals = [
      { id: "appr-1", entityType: "purchase_order", entityId: "po-1", code: "PO-2026-101", title: "Apex Logistics Global (Compute Capacity)", totalMinor: 4850000, currency: "USD", tier: "manager", status: "pending" },
      { id: "appr-2", entityType: "requisition", entityId: "req-2", code: "REQ-2026-090", title: "Q4 Customer Care Headsets", totalMinor: 890000, currency: "USD", tier: "finance", status: "pending" },
    ];
    return { data: approvals as unknown as T, pagination: null, requestId: reqId };
  }

  // 8. Notifications
  if (cleanPath.includes("/notifications")) {
    const notifs = [
      { id: "notif-1", title: "Contract Renewal Approaching", body: "TransOcean Cargo contract CNT-2026-003 expires in 18 days.", severity: "warning", createdAt: new Date(Date.now() - 3600000).toISOString() },
      { id: "notif-2", title: "PO Approved", body: "Purchase order PO-2026-101 approved by Finance.", severity: "info", createdAt: new Date(Date.now() - 7200000).toISOString() },
      { id: "notif-3", title: "New RFQ Response", body: "Apex Logistics submitted quote for RFQ-2026-042.", severity: "info", createdAt: new Date(Date.now() - 86400000).toISOString() },
    ];
    return { data: notifs as unknown as T, pagination: null, requestId: reqId };
  }

  // 9. AI / Copilot
  if (cleanPath.includes("/ai/providers")) {
    return { data: { configured: "vantor-copilot-demo", available: ["vantor-copilot-demo"] } as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.includes("/ai/complete")) {
    return {
      data: {
        text: "Based on active contracts and current spend commitments, Q3 spend is running at 94% of budget with $142,000 in negotiated savings.",
        confidence: 0.94,
        grounded: true,
      } as unknown as T,
      pagination: null,
      requestId: reqId,
    };
  }

  // Default fallback for any other list / entity
  return { data: [] as unknown as T, pagination: null, requestId: reqId };
}
