import { describe, expect, it } from "vitest";
import { resourceLabel } from "./approvals";

/**
 * The approvals queue mixes document types, and approving a purchase order is
 * not the same act as approving a requisition. The Document column shows the
 * code, so the type has to be stated rather than inferred from a code prefix.
 *
 * These assertions pin the labelling: a type the API introduces later must
 * still render as something a person can read, not as a raw database key.
 */
describe("resourceLabel", () => {
  it("names the types the queue actually contains", () => {
    expect(resourceLabel("requisition")).toBe("Requisition");
    expect(resourceLabel("purchase_order")).toBe("Purchase order");
    expect(resourceLabel("invoice")).toBe("Invoice");
  });

  it("names an AI action request", () => {
    expect(resourceLabel("ai:create_rfq")).toBe("AI: create_rfq");
  });

  it("does not leave an unknown type as a raw key", () => {
    // A new resource type the backend adds must not appear as `some_new_type`
    // in the queue an approver is reading.
    expect(resourceLabel("some_new_type")).toBe("Some new type");
  });

  it("survives an empty type", () => {
    expect(resourceLabel("")).toBe("");
  });
});
