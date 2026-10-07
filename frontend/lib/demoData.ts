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

export type DemoPagination = { limit: number; nextCursor: string; hasMore: boolean; [k: string]: unknown } | null;

export function getDemoResponse<T>(path: string, _init?: unknown): { data: T; pagination: DemoPagination; requestId: string } {
  void _init;
  const reqId = `demo-${Date.now().toString(36)}`;
  const cleanPath = path.split("?")[0];

  // 1. Spend Summary & Intelligence
  if (cleanPath.endsWith("/spend/summary")) {
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
      bySupplier: [
        { supplierId: "sup-1", supplierName: "Apex Logistics Global", currency: "USD", poTotalMinor: 48500000, poCount: 12 },
        { supplierId: "sup-2", supplierName: "CleanCorp Facilities", currency: "USD", poTotalMinor: 12000000, poCount: 4 },
        { supplierId: "sup-3", supplierName: "TransOcean Cargo", currency: "USD", poTotalMinor: 35000000, poCount: 8 },
        { supplierId: "sup-4", supplierName: "TechEquip Systems", currency: "USD", poTotalMinor: 8500000, poCount: 3 },
        { supplierId: "sup-5", supplierName: "PackWell Solutions", currency: "USD", poTotalMinor: 21000000, poCount: 6 },
      ],
    };
    return { data: summary as unknown as T, pagination: null, requestId: reqId };
  }

  if (cleanPath.endsWith("/spend/intelligence")) {
    const intel = {
      cube: [
        { supplierId: "sup-1", supplierName: "Apex Logistics Global", categoryId: "cat-cloud", categoryName: "Cloud Infrastructure", currency: "USD", totalMinor: 48500000, poCount: 12 },
        { supplierId: "sup-2", supplierName: "CleanCorp Facilities", categoryId: "cat-facil", categoryName: "Facilities Management", currency: "USD", totalMinor: 12000000, poCount: 4 },
        { supplierId: "sup-3", supplierName: "TransOcean Cargo", categoryId: "cat-freight", categoryName: "Freight & Shipping", currency: "USD", totalMinor: 35000000, poCount: 8 },
        { supplierId: "sup-4", supplierName: "TechEquip Systems", categoryId: "cat-it", categoryName: "IT Hardware", currency: "USD", totalMinor: 8500000, poCount: 3 },
        { supplierId: "sup-5", supplierName: "PackWell Solutions", categoryId: "cat-pack", categoryName: "Packaging & Boxes", currency: "USD", totalMinor: 21000000, poCount: 6 },
      ],
      leakageTotalMinor: 3200000,
      concentration: {
        topShareBp: 3265,
        topSupplierId: "sup-1",
        topSupplierName: "Apex Logistics Global",
        singleSourceRisk: false,
      },
    };
    return { data: intel as unknown as T, pagination: null, requestId: reqId };
  }

  if (cleanPath.includes("/spend/price-cases")) {
    if (cleanPath.includes("/resolve")) {
      return { data: { id: "case-1", status: "handed_off" } as unknown as T, pagination: null, requestId: reqId };
    }
    const cases = [
      { id: "case-1", item: "Corrugated Packaging 24x18x12 (per 1000)", baselineMinor: 160000, quotedMinor: 198000, varianceBp: 2375, samples: 14, status: "open" },
      { id: "case-2", item: "Enterprise Compute Capacity Node A", baselineMinor: 450000, quotedMinor: 485000, varianceBp: 777, samples: 28, status: "open" },
    ];
    return { data: cases as unknown as T, pagination: null, requestId: reqId };
  }

  if (cleanPath.includes("/spend/should-cost")) {
    return {
      data: {
        breakdown: { should_minor: 142000 },
        gap: { gap_minor: 18000, verdict: "favorable" },
      } as unknown as T,
      pagination: null,
      requestId: reqId,
    };
  }

  if (cleanPath.includes("/spend/price-evaluate")) {
    return {
      data: { opened: [], skipped: [] } as unknown as T,
      pagination: null,
      requestId: reqId,
    };
  }

  // 2. Contracts
  const demoContracts = [
    {
      id: "cnt-1",
      code: "CNT-2026-001",
      title: "Enterprise Cloud Hosting & Compute",
      status: "active",
      endDate: "2026-11-15",
      supplierName: "Apex Logistics Global",
      supplierId: "sup-1",
      valueMinor: 48000000,
      currency: "USD",
      obligations: [
        { id: "ob-1", title: "Quarterly SOC2 compliance report submission", status: "open", dueDate: "2026-11-01", owner: "Security Team" },
        { id: "ob-2", title: "99.95% SLA verification & penalty reconciliation", status: "open", dueDate: "2026-11-10", owner: "DevOps Lead" },
      ],
    },
    {
      id: "cnt-2",
      code: "CNT-2026-002",
      title: "Facilities Management & Cleaning",
      status: "active",
      endDate: "2026-12-31",
      supplierName: "CleanCorp Facilities",
      supplierId: "sup-2",
      valueMinor: 12000000,
      currency: "USD",
      obligations: [
        { id: "ob-3", title: "Green chemical certification audit", status: "open", dueDate: "2026-12-15", owner: "Facility Mgr" },
      ],
    },
    {
      id: "cnt-3",
      code: "CNT-2026-003",
      title: "Global Freight & Customs Brokerage",
      status: "expiring",
      endDate: "2026-10-25",
      supplierName: "TransOcean Cargo",
      supplierId: "sup-3",
      valueMinor: 35000000,
      currency: "USD",
      obligations: [
        { id: "ob-4", title: "Annual maritime fuel index true-up", status: "open", dueDate: "2026-10-20", owner: "Logistics Lead" },
      ],
    },
    {
      id: "cnt-4",
      code: "CNT-2026-004",
      title: "Office IT Equipment Hardware Lease",
      status: "active",
      endDate: "2027-03-01",
      supplierName: "TechEquip Systems",
      supplierId: "sup-4",
      valueMinor: 8500000,
      currency: "USD",
      obligations: [],
    },
    {
      id: "cnt-5",
      code: "CNT-2026-005",
      title: "Packaging Materials Annual Agreement",
      status: "active",
      endDate: "2027-06-30",
      supplierName: "PackWell Solutions",
      supplierId: "sup-5",
      valueMinor: 21000000,
      currency: "USD",
      obligations: [],
    },
  ];

  if (cleanPath.startsWith("/api/v1/contracts")) {
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      const contractId = parts[3];
      const match = demoContracts.find((c) => c.id === contractId) || demoContracts[0];
      return { data: match as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: demoContracts as unknown as T, pagination: { limit: 100, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 3. Purchase Orders
  const demoOrders = [
    {
      id: "po-1",
      code: "PO-2026-101",
      status: "approved",
      totalMinor: 4850000,
      currency: "USD",
      supplierId: "sup-1",
      supplierName: "Apex Logistics Global",
      lines: [
        { id: "pol-1", lineNo: 1, description: "Compute Capacity Node A", quantity: 10, unitPriceMinor: 485000, lineTotalMinor: 4850000 }
      ],
      invoices: [
        { id: "inv-1", code: "INV-2026-081", status: "approved" }
      ],
    },
    {
      id: "po-2",
      code: "PO-2026-102",
      status: "sent",
      totalMinor: 12500000,
      currency: "USD",
      supplierId: "sup-3",
      supplierName: "TransOcean Cargo",
      lines: [
        { id: "pol-2", lineNo: 1, description: "Ocean Freight 40ft TEU", quantity: 5, unitPriceMinor: 2500000, lineTotalMinor: 12500000 }
      ],
      invoices: [],
    },
    {
      id: "po-3",
      code: "PO-2026-103",
      status: "received",
      totalMinor: 3200000,
      currency: "USD",
      supplierId: "sup-5",
      supplierName: "PackWell Solutions",
      lines: [
        { id: "pol-3", lineNo: 1, description: "Recycled Corrugated Boxes", quantity: 2000, unitPriceMinor: 1600, lineTotalMinor: 3200000 }
      ],
      invoices: [
        { id: "inv-2", code: "INV-2026-083", status: "matched" }
      ],
    },
    {
      id: "po-4",
      code: "PO-2026-104",
      status: "draft",
      totalMinor: 750000,
      currency: "USD",
      supplierId: "sup-4",
      supplierName: "TechEquip Systems",
      lines: [
        { id: "pol-4", lineNo: 1, description: "Ergonomic Keyboards & Docks", quantity: 15, unitPriceMinor: 50000, lineTotalMinor: 750000 }
      ],
      invoices: [],
    },
    {
      id: "po-5",
      code: "PO-2026-105",
      status: "approved",
      totalMinor: 6400000,
      currency: "USD",
      supplierId: "sup-2",
      supplierName: "CleanCorp Facilities",
      lines: [
        { id: "pol-5", lineNo: 1, description: "Quarterly Deep Sanitize", quantity: 1, unitPriceMinor: 6400000, lineTotalMinor: 6400000 }
      ],
      invoices: [],
    },
  ];

  if (cleanPath.startsWith("/api/v1/purchase-orders")) {
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      const poId = parts[3];
      const match = demoOrders.find((p) => p.id === poId) || demoOrders[0];
      return { data: match as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: demoOrders as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 4. Invoices
  if (cleanPath.startsWith("/api/v1/invoices")) {
    const invoices = [
      { id: "inv-1", code: "INV-2026-081", status: "approved", totalMinor: 4850000, currency: "USD", poCode: "PO-2026-101" },
      { id: "inv-2", code: "INV-2026-083", status: "matched", totalMinor: 3200000, currency: "USD", poCode: "PO-2026-103" },
    ];
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      return { data: { id: parts[3], status: "approved" } as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: invoices as unknown as T, pagination: null, requestId: reqId };
  }

  // 5. RFQs
  const demoRfqs = [
    {
      id: "rfq-1",
      code: "RFQ-2026-042",
      title: "Global Logistics Freight Forwarding (2027)",
      status: "sent",
      currency: "USD",
      supplierCount: 4,
      responseCount: 3,
      lineCount: 2,
      lines: [
        { id: "rfql-1", lineNo: 1, description: "40ft High Cube Container Freight", quantity: 50, uom: "containers" },
        { id: "rfql-2", lineNo: 2, description: "Customs Clearance & Brokerage", quantity: 50, uom: "shipments" },
      ],
    },
    {
      id: "rfq-2",
      code: "RFQ-2026-043",
      title: "Office Laptop Fleet Refresh",
      status: "response",
      currency: "USD",
      supplierCount: 3,
      responseCount: 3,
      lineCount: 1,
      lines: [
        { id: "rfql-3", lineNo: 1, description: "Enterprise 16-inch Laptops (32GB / 1TB)", quantity: 45, uom: "units" },
      ],
    },
    {
      id: "rfq-3",
      code: "RFQ-2026-044",
      title: "Corrugated Packaging Supply Contract",
      status: "draft",
      currency: "USD",
      supplierCount: 2,
      responseCount: 0,
      lineCount: 1,
      lines: [
        { id: "rfql-4", lineNo: 1, description: "24x18x12 Recycled Corrugated Boxes", quantity: 10000, uom: "boxes" },
      ],
    },
  ];

  if (cleanPath.startsWith("/api/v1/rfqs")) {
    if (cleanPath.includes("/comparison")) {
      const comp = [
        { quoteId: "q-1", supplierId: "sup-3", supplierName: "TransOcean Cargo", status: "submitted", currency: "USD", totalMinor: 34500000, lineCount: 2 },
        { quoteId: "q-2", supplierId: "sup-1", supplierName: "Apex Logistics Global", status: "submitted", currency: "USD", totalMinor: 36200000, lineCount: 2 },
      ];
      return { data: comp as unknown as T, pagination: null, requestId: reqId };
    }
    if (cleanPath.includes("/optimize")) {
      const plan = {
        allocations: [
          { supplier_id: "sup-3", supplier_name: "TransOcean Cargo", quote_id: "q-1", share_bp: 7000, cost_minor: 24150000, reason: "Lowest total lane cost for primary ocean route" },
          { supplier_id: "sup-1", supplier_name: "Apex Logistics Global", quote_id: "q-2", share_bp: 3000, cost_minor: 10860000, reason: "Secondary carrier redundancy buffer" },
        ],
        total_minor: 35010000,
        share_sum_bp: 10000,
        violations: [],
      };
      return { data: plan as unknown as T, pagination: null, requestId: reqId };
    }
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      const rfqId = parts[3];
      const match = demoRfqs.find((r) => r.id === rfqId) || demoRfqs[0];
      return { data: match as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: demoRfqs as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 6. Suppliers
  const demoSuppliers = [
    { id: "sup-1", code: "SUP-001", name: "Apex Logistics Global", status: "active", country: "US", currency: "USD", riskTier: "low", categoryId: "cat-cloud", categoryName: "Cloud Infrastructure" },
    { id: "sup-2", code: "SUP-002", name: "CleanCorp Facilities", status: "active", country: "US", currency: "USD", riskTier: "low", categoryId: "cat-facil", categoryName: "Facilities Management" },
    { id: "sup-3", code: "SUP-003", name: "TransOcean Cargo", status: "active", country: "SG", currency: "USD", riskTier: "medium", categoryId: "cat-freight", categoryName: "Freight & Shipping" },
    { id: "sup-4", code: "SUP-004", name: "TechEquip Systems", status: "active", country: "DE", currency: "EUR", riskTier: "low", categoryId: "cat-it", categoryName: "IT Hardware" },
    { id: "sup-5", code: "SUP-005", name: "PackWell Solutions", status: "active", country: "US", currency: "USD", riskTier: "low", categoryId: "cat-pack", categoryName: "Packaging & Boxes" },
    { id: "sup-6", code: "SUP-006", name: "CyberShield Security Ltd", status: "active", country: "GB", currency: "GBP", riskTier: "low", categoryId: "cat-sec", categoryName: "Cybersecurity" },
  ];

  if (cleanPath.startsWith("/api/v1/suppliers")) {
    if (cleanPath.includes("/contacts")) {
      const contacts = [
        { id: "con-1", fullName: "James Wilson", email: "j.wilson@supplier.example", phone: "+1 415 555 0192", role: "Key Account Director" },
        { id: "con-2", fullName: "Elena Rostova", email: "e.rostova@supplier.example", phone: "+1 415 555 0193", role: "Technical Operations Lead" },
      ];
      return { data: contacts as unknown as T, pagination: null, requestId: reqId };
    }
    if (cleanPath.includes("/scorecard")) {
      const scorecard = {
        supplierId: "sup-1",
        score: 87,
        grade: "A",
        risk_tier: "low",
        dims: { financial: 4, quality: 5, delivery: 4, service: 4, compliance: 5 },
      };
      return { data: scorecard as unknown as T, pagination: null, requestId: reqId };
    }
    if (cleanPath.includes("/certifications")) {
      const certs = [
        { id: "cert-1", name: "ISO 9001:2015 Quality Management", issuer: "Bureau Veritas", validUntil: "2027-12-31", status: "verified" },
        { id: "cert-2", name: "SOC 2 Type II Security Report", issuer: "Ernst & Young", validUntil: "2026-11-30", status: "verified" },
      ];
      return { data: certs as unknown as T, pagination: null, requestId: reqId };
    }
    if (cleanPath.includes("/qualification")) {
      const qual = {
        status: "qualified",
        exists: true,
        checklist: [
          { key: "kyc", label: "Anti-Bribery & Sanctions Check", done: true },
          { key: "tax", label: "W-9 / Tax Residency Certification", done: true },
          { key: "nda", label: "Master NDA Executed", done: true },
          { key: "esg", label: "Supplier Code of Conduct & ESG Pledge", done: true },
        ],
      };
      return { data: qual as unknown as T, pagination: null, requestId: reqId };
    }
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      const supId = parts[3];
      const match = demoSuppliers.find((s) => s.id === supId) || demoSuppliers[0];
      return { data: match as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: demoSuppliers as unknown as T, pagination: { limit: 15, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 7. Requisitions
  if (cleanPath.startsWith("/api/v1/requisitions")) {
    const reqs = [
      { id: "req-1", code: "REQ-2026-089", title: "Data Center Cooling Modernization", status: "approved", requester: "operator@vantor.internal", createdAt: "2026-10-05T08:30:00Z" },
      { id: "req-2", code: "REQ-2026-090", title: "Q4 Customer Care Headsets", status: "submitted", requester: "david.miller@vantor.internal", createdAt: "2026-10-06T11:45:00Z" },
      { id: "req-3", code: "REQ-2026-091", title: "Warehouse Pallet Jack Replacements", status: "draft", requester: "sarah.chen@vantor.internal", createdAt: "2026-10-07T14:10:00Z" },
    ];
    const parts = cleanPath.split("/").filter(Boolean);
    if (parts.length >= 4) {
      return { data: { id: parts[3], status: "submitted" } as unknown as T, pagination: null, requestId: reqId };
    }
    return { data: reqs as unknown as T, pagination: { limit: 10, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 8. Approvals (Queue & Decisions)
  if (cleanPath.startsWith("/api/v1/approvals")) {
    if (cleanPath.includes("/decide")) {
      const parts = cleanPath.split("/").filter(Boolean);
      const apprId = parts[3] || "appr-1";
      return {
        data: { id: apprId, status: "approved", resourceStatus: "approved" } as unknown as T,
        pagination: null,
        requestId: reqId,
      };
    }
    const approvals = [
      {
        id: "appr-1",
        resource: "purchase_order",
        resourceId: "po-1",
        resourceCode: "PO-2026-101",
        status: "requested",
        tier: "finance",
        requestedBy: "sarah.chen@vantor.internal",
        decidedBy: "",
        reason: "High-value compute infrastructure allocation",
        requiresHumanReview: true,
        createdAt: "2026-10-06T14:22:00Z",
      },
      {
        id: "appr-2",
        resource: "requisition",
        resourceId: "req-2",
        resourceCode: "REQ-2026-090",
        status: "requested",
        tier: "manager",
        requestedBy: "david.miller@vantor.internal",
        decidedBy: "",
        reason: "Department equipment quarterly refresh",
        requiresHumanReview: false,
        createdAt: "2026-10-07T09:15:00Z",
      },
      {
        id: "appr-3",
        resource: "purchase_order",
        resourceId: "po-5",
        resourceCode: "PO-2026-105",
        status: "requested",
        tier: "procurement",
        requestedBy: "alex.kumar@vantor.internal",
        decidedBy: "",
        reason: "Annual facilities maintenance renewal",
        requiresHumanReview: true,
        createdAt: "2026-10-07T11:00:00Z",
      },
    ];
    return { data: approvals as unknown as T, pagination: null, requestId: reqId };
  }

  // 9. Notifications & Unread Count
  if (cleanPath.startsWith("/api/v1/notifications")) {
    if (cleanPath.includes("/unread-count")) {
      return { data: { unread: 2 } as unknown as T, pagination: null, requestId: reqId };
    }
    if (cleanPath.includes("/read")) {
      return { data: { ok: true } as unknown as T, pagination: null, requestId: reqId };
    }
    const notifs = [
      { id: "notif-0", kind: "system", title: "Live Vercel Deployment Active", body: "Exploring VANTOR at https://vantor-os.vercel.app/ in standalone demo mode.", link: "https://vantor-os.vercel.app/", read: false, createdAt: new Date().toISOString() },
      { id: "notif-1", kind: "contract", title: "Contract Renewal Approaching", body: "TransOcean Cargo contract CNT-2026-003 expires in 18 days.", link: "/contracts", read: false, createdAt: new Date(Date.now() - 3600000).toISOString() },
      { id: "notif-2", kind: "approval", title: "PO Approval Pending", body: "Purchase order PO-2026-101 requires executive sign-off.", link: "/approvals", read: false, createdAt: new Date(Date.now() - 7200000).toISOString() },
      { id: "notif-3", kind: "rfq", title: "New RFQ Response", body: "Apex Logistics submitted quote for RFQ-2026-042.", link: "/rfqs", read: true, createdAt: new Date(Date.now() - 86400000).toISOString() },
    ];
    return { data: notifs as unknown as T, pagination: null, requestId: reqId };
  }

  // 10. Governance, Audit Trail & Catalog
  if (cleanPath.includes("/audit-events/verify")) {
    return {
      data: { valid: true, message: "Hash chain verified (SHA-256 genesis linked)", truncated: false } as unknown as T,
      pagination: null,
      requestId: reqId,
    };
  }
  if (cleanPath.startsWith("/api/v1/audit-events")) {
    const events = [
      { id: "ev-1", actor: "sarah.chen@vantor.internal", action: "po.created", resource: "purchase_order", resourceId: "po-1", occurredAt: "2026-10-07T14:30:00Z", reason: "Quarterly compute provisioning", source: "web", hash: "a9f8b4c2d1e0f3456789abcdef0123456789", prevHash: "000000000000000000000000000000000000" },
      { id: "ev-2", actor: "finance.lead@vantor.internal", action: "approval.granted", resource: "purchase_order", resourceId: "po-1", occurredAt: "2026-10-07T15:00:00Z", reason: "Budget compliance verified", source: "copilot", hash: "b8e7c3d2f1a0e4567890abcdef0123456789", prevHash: "a9f8b4c2d1e0f3456789abcdef0123456789" },
      { id: "ev-3", actor: "system.ledger", action: "spend.committed", resource: "purchase_order", resourceId: "po-1", occurredAt: "2026-10-07T15:00:01Z", reason: "Ledger commit executed", source: "worker", hash: "c7d6e5f4a3b2c123456789abcdef01234567", prevHash: "b8e7c3d2f1a0e4567890abcdef0123456789" },
    ];
    return { data: events as unknown as T, pagination: { limit: 50, nextCursor: "", hasMore: false }, requestId: reqId };
  }
  if (cleanPath.includes("/catalog/categories")) {
    const cats = [
      { id: "cat-cloud", code: "CAT-CLOUD", name: "Cloud Infrastructure & Compute", parentId: "" },
      { id: "cat-freight", code: "CAT-LOGISTICS", name: "Freight, Shipping & Customs", parentId: "" },
      { id: "cat-facil", code: "CAT-FACILITIES", name: "Facilities & Maintenance", parentId: "" },
      { id: "cat-pack", code: "CAT-PACKAGING", name: "Corrugated Packaging & Materials", parentId: "" },
      { id: "cat-it", code: "CAT-IT", name: "Workstations & Peripherals", parentId: "" },
    ];
    return { data: cats as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.includes("/catalog/items")) {
    const items = [
      { id: "item-1", code: "ITM-SRV-01", name: "Standard 64-Core Cloud Compute Node", uom: "instance-month", refPriceMinor: 485000, currency: "USD", categoryId: "cat-cloud" },
      { id: "item-2", code: "ITM-BOX-24", name: "Heavy Duty Corrugated Box 24x18x12", uom: "1000-pack", refPriceMinor: 160000, currency: "USD", categoryId: "cat-pack" },
      { id: "item-3", code: "ITM-FRT-40", name: "Trans-Pacific Ocean TEU 40ft Freight", uom: "container", refPriceMinor: 2500000, currency: "USD", categoryId: "cat-freight" },
    ];
    return { data: items as unknown as T, pagination: null, requestId: reqId };
  }

  // 11. Integrations & Webhooks
  if (cleanPath.endsWith("/integrations/types")) {
    return { data: { types: ["erp", "accounting", "warehouse", "slack"] } as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.endsWith("/integrations")) {
    const integrations = [
      { id: "int-1", name: "SAP S/4HANA ERP Connector", itype: "erp", status: "active", createdAt: "2026-09-01T00:00:00Z" },
      { id: "int-2", name: "NetSuite General Ledger Sync", itype: "accounting", status: "active", createdAt: "2026-09-15T00:00:00Z" },
      { id: "int-3", name: "Slack Procurement Approvals Bot", itype: "slack", status: "active", createdAt: "2026-10-01T00:00:00Z" },
    ];
    return { data: integrations as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.endsWith("/webhooks/endpoints")) {
    const endpoints = [
      { id: "wh-1", url: "https://hooks.slack.com/services/T00/B00/XXXX", events: ["po.approved", "invoice.received"], status: "active" },
      { id: "wh-2", url: "https://erp-gateway.internal/events/procurement", events: ["po.created", "contract.signed"], status: "active" },
    ];
    return { data: endpoints as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.endsWith("/webhooks/deliveries")) {
    const deliveries = [
      { id: "del-1", event: "po.approved", status: "delivered", attempts: 1 },
      { id: "del-2", event: "invoice.received", status: "delivered", attempts: 1 },
      { id: "del-3", event: "contract.signed", status: "delivered", attempts: 1 },
    ];
    return { data: deliveries as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.endsWith("/webhooks/test")) {
    return { data: { delivery: { status: "delivered", attempts: 1 } } as unknown as T, pagination: null, requestId: reqId };
  }

  // 12. Documents
  if (cleanPath.includes("/documents/search")) {
    const hits = [
      { documentId: "doc-1", chunkNo: 3, excerpt: "Section 4.2: Committed minimum compute reservation guarantees 99.95% uptime availability across all operational regions." },
      { documentId: "doc-2", chunkNo: 1, excerpt: "Schedule B: Peak shipping surcharge waiver applied for high cube 40ft containers originating from Singapore terminal." },
    ];
    return { data: hits as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.startsWith("/api/v1/documents")) {
    const docs = [
      { id: "doc-1", filename: "Master_Cloud_Agreement_2026.pdf", sizeBytes: 1428500, status: "ready" },
      { id: "doc-2", filename: "Global_Freight_Carrier_Tariffs_Q3.xlsx", sizeBytes: 489200, status: "ready" },
      { id: "doc-3", filename: "Facilities_Service_Level_Agreement.pdf", sizeBytes: 812400, status: "ready" },
    ];
    return { data: docs as unknown as T, pagination: { limit: 15, nextCursor: "", hasMore: false }, requestId: reqId };
  }

  // 13. AI / Copilot
  if (cleanPath.includes("/ai/providers")) {
    const providers = {
      active: "vantor-copilot-demo",
      available: [
        { name: "vantor-copilot-demo", configured: true, needsKey: false, active: true },
        { name: "anthropic-claude", configured: false, needsKey: true, active: false },
        { name: "openai-gpt4", configured: false, needsKey: true, active: false },
      ],
    };
    return { data: providers as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.includes("/ai/negotiate")) {
    const nego = {
      result: "deal",
      score: 88,
      rounds: [
        { round: 1, buyer: 7000000, supplier: 9500000, event: "counter" },
        { round: 2, buyer: 8000000, supplier: 8800000, event: "counter" },
        { round: 3, buyer: 8800000, supplier: 8800000, event: "deal_accepted" },
      ],
      reason: "Agreement reached at 88,000 INR after 3 iterative concession rounds.",
      settled_minor: 8800000,
    };
    return { data: nego as unknown as T, pagination: null, requestId: reqId };
  }
  if (cleanPath.includes("/ai/complete")) {
    return {
      data: {
        answer: "Based on active contracts and current spend commitments, Q3 spend is running at 94% of budget with $142,000 in negotiated savings.",
        confidence: 0.94,
        evidence: [{ resource: "purchase_order", id: "po-1" }, { resource: "contract", id: "cnt-1" }],
        data_timestamp: new Date().toISOString(),
        requires_human_review: false,
        provider: "vantor-copilot-demo",
        model: "vantor-v2",
      } as unknown as T,
      pagination: null,
      requestId: reqId,
    };
  }

  // Default fallback for any other list / entity
  return { data: [] as unknown as T, pagination: null, requestId: reqId };
}
