import { describe, expect, it } from "vitest";
import { getDemoResponse, getDemoSession, setDemoFlag, isDemoSession } from "./demoData";
import type { Approval } from "../app/copilot/approvals";
import type { ProviderList } from "./ai";

type SpendSummary = {
  poTotalMinor: number;
  bySupplier: { supplierId: string }[];
};

type SpendIntel = {
  cube: { supplierId: string }[];
  concentration: { topSupplierId: string };
};

type AuditVerify = {
  valid: boolean;
  message: string;
};

type Category = {
  id: string;
  code: string;
};

type ContractDetail = {
  id: string;
  obligations: { id: string }[];
};

type PODetail = {
  id: string;
  lines: { id: string }[];
  invoices: { id: string }[];
};

type NotificationItem = {
  id: string;
  kind: string;
  read: boolean;
};

type IntegrationTypes = {
  types: string[];
};

type WebhookTest = {
  delivery: { status: string };
};

type DecideResult = {
  id: string;
  status: string;
  resourceStatus: string;
};

describe("demoData provider", () => {
  it("provides valid demo session", () => {
    const s = getDemoSession("approver");
    expect(s.persona).toBe("demo");
    expect(s.roles).toContain("approver");
    expect(s.roles).toContain("admin");
  });

  it("handles demo flag in localStorage", () => {
    setDemoFlag(true);
    expect(isDemoSession()).toBe(true);
    setDemoFlag(false);
  });

  it("returns properly shaped spend summary and intelligence", () => {
    const summary = getDemoResponse<SpendSummary>("/api/v1/spend/summary");
    expect(summary.data.poTotalMinor).toBeGreaterThan(0);
    expect(summary.data.bySupplier.length).toBeGreaterThan(0);

    const intel = getDemoResponse<SpendIntel>("/api/v1/spend/intelligence");
    expect(intel.data.cube.length).toBeGreaterThan(0);
    expect(intel.data.concentration.topSupplierId).toBe("sup-1");
  });

  it("returns approvals with non-empty resource and resourceId", () => {
    const approvals = getDemoResponse<Approval[]>("/api/v1/approvals?status=requested&limit=25");
    expect(Array.isArray(approvals.data)).toBe(true);
    expect(approvals.data.length).toBeGreaterThan(0);
    for (const a of approvals.data) {
      expect(typeof a.id).toBe("string");
      expect(typeof a.resource).toBe("string");
      expect(typeof a.resourceId).toBe("string");
      expect(a.resourceId.length).toBeGreaterThan(0);
      expect(a.resourceId.slice(0, 8)).toBeDefined();
    }
  });

  it("handles approval decision mutation", () => {
    const decide = getDemoResponse<DecideResult>("/api/v1/approvals/appr-1/decide", { method: "POST" });
    expect(decide.data.status).toBe("approved");
    expect(decide.data.resourceStatus).toBe("approved");
  });

  it("returns valid audit chain verification and catalog categories", () => {
    const verify = getDemoResponse<AuditVerify>("/api/v1/audit-events/verify");
    expect(verify.data.valid).toBe(true);
    expect(verify.data.message).toBeDefined();

    const cats = getDemoResponse<Category[]>("/api/v1/catalog/categories");
    expect(cats.data.length).toBeGreaterThan(0);
    expect(cats.data[0].code).toBeDefined();
  });

  it("returns single contract when queried by ID", () => {
    const c = getDemoResponse<ContractDetail>("/api/v1/contracts/cnt-1");
    expect(c.data.id).toBe("cnt-1");
    expect(Array.isArray(c.data.obligations)).toBe(true);
  });

  it("returns single purchase order when queried by ID", () => {
    const po = getDemoResponse<PODetail>("/api/v1/purchase-orders/po-1");
    expect(po.data.id).toBe("po-1");
    expect(Array.isArray(po.data.lines)).toBe(true);
    expect(Array.isArray(po.data.invoices)).toBe(true);
  });

  it("returns notifications with required fields", () => {
    const n = getDemoResponse<NotificationItem[]>("/api/v1/notifications?limit=25");
    expect(n.data.length).toBeGreaterThan(0);
    expect(n.data[0].kind).toBeDefined();
    expect(typeof n.data[0].read).toBe("boolean");
  });

  it("returns integrations types and webhooks", () => {
    const types = getDemoResponse<IntegrationTypes>("/api/v1/integrations/types");
    expect(Array.isArray(types.data.types)).toBe(true);

    const testPing = getDemoResponse<WebhookTest>("/api/v1/webhooks/test", { method: "POST" });
    expect(testPing.data.delivery.status).toBe("delivered");
  });

  it("returns AI providers in object shape", () => {
    const providers = getDemoResponse<ProviderList>("/api/v1/ai/providers");
    expect(providers.data.active).toBe("vantor-copilot-demo");
    expect(Array.isArray(providers.data.available)).toBe(true);
    expect(providers.data.available[0].name).toBe("vantor-copilot-demo");
    expect(providers.data.available[0].configured).toBe(true);
  });
});
