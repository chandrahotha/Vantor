import { test, expect, type Page } from "@playwright/test";

/**
 * The complete procurement day, driven through the real browser against a
 * live backend (SQLite, AUTH_MODE=local) rather than mocked fetches.
 *
 * Create requisition -> submit -> approve -> PO (requisition goes "ordered")
 * -> approve PO -> send -> receive goods -> record invoice -> approve invoice
 * (3-way match) -> final state verified in the UI.
 *
 * This is the one path `journey.spec.ts` never exercises (that file only
 * reaches the sign-in screen). It needs AUTH_MODE=local because it uses local
 * persona-switching to clear segregation-of-duties approvals with one browser
 * session: a requester can never approve their own document (`APPROVAL_SOD`),
 * so the same physical test run signs in as "Buyer" to raise things and
 * "Approver" to clear them — see `backend/app/core/localauth.py::PERSONAS`.
 */

async function signInAs(page: Page, personaLabel: string) {
  await expect(page.getByRole("button", { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });
  const select = page.getByRole("combobox", { name: /local identity/i });
  // Only present under AUTH_MODE=local; this spec requires that mode, so if it
  // is missing the next assertion fails loudly rather than silently signing
  // in as whatever the single default identity is.
  await expect(select, "local persona picker not found — is AUTH_MODE=local?").toBeVisible({ timeout: 5_000 });
  await select.selectOption({ label: personaLabel });
  await page.getByRole("button", { name: /log in to vantor/i }).click();
  await expect(page.locator(".userchip-card")).toBeVisible({ timeout: 15_000 });
}

async function signOut(page: Page) {
  await page.locator(".userchip-logout").click();
  await page.getByRole("alertdialog").getByRole("button", { name: /^sign out$/i }).click();
  await expect(page.getByRole("button", { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });
}

test("the full requisition-to-invoice workflow completes through the real UI", async ({ page }) => {
  const unique = Date.now().toString(36).toUpperCase();
  const reqCode = `REQ-${unique}`;
  const supCode = `SUP-${unique}`;
  const poCode = `PO-${unique}`;
  const invCode = `INV-${unique}`;
  const supplierLabel = `${supCode} — Acme ${unique} Industrial`;
  const reqLabel = `${reqCode} — E2E workflow smoke`;

  const consoleErrors: string[] = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await test.step("sign in as Buyer", async () => {
    await page.goto("/");
    await signInAs(page, "Buyer");
  });

  await test.step("create a supplier", async () => {
    await page.getByRole("link", { name: "Suppliers" }).click();
    await page.locator("summary", { hasText: /new supplier/i }).click().catch(() => {});
    await page.getByLabel("Supplier code").fill(supCode);
    await page.getByLabel("Supplier name").fill(`Acme ${unique} Industrial`);
    await page.getByLabel("Currency").fill("INR");
    await page.getByRole("button", { name: /create supplier/i }).click();
    await expect(page.locator("tr", { hasText: supCode })).toBeVisible({ timeout: 15_000 });
  });

  await test.step("create and submit a requisition", async () => {
    await page.getByRole("link", { name: "Requisitions" }).click();
    await page.locator("summary", { hasText: /new requisition/i }).click().catch(() => {});
    await page.getByLabel("Requisition code").fill(reqCode);
    await page.getByLabel("Requisition title").fill("E2E workflow smoke");
    await page.getByLabel("Line description").fill("M10 hex bolt");
    await page.getByLabel("Quantity").fill("50");
    await page.getByLabel("Estimated unit price").fill("5.00");
    await page.getByRole("button", { name: /create requisition/i }).click();
    const reqRow = page.locator("tr", { hasText: reqCode });
    await expect(reqRow).toBeVisible({ timeout: 15_000 });

    await reqRow.getByRole("button", { name: /submit/i }).click();
    await expect(reqRow).toContainText("submitted", { timeout: 15_000 });
  });

  await test.step("approve the requisition as a different persona (SoD)", async () => {
    await signOut(page);
    await signInAs(page, "Approver");
    await page.getByRole("link", { name: "Approvals" }).click();
    const approvalRow = page.locator("tr", { hasText: "requisition" }).first();
    await expect(approvalRow).toBeVisible({ timeout: 15_000 });
    await approvalRow.getByRole("button", { name: /approve/i }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: /^approve$/i }).click();
    await expect(page.getByText(/approval approved/i).first()).toBeVisible({ timeout: 15_000 });
  });

  await test.step("raise a PO against the approved requisition; it goes 'ordered'", async () => {
    await signOut(page);
    await signInAs(page, "Buyer");
    await page.getByRole("link", { name: "Purchase orders" }).click();
    await page.locator("summary", { hasText: /new purchase order/i }).click().catch(() => {});
    await page.getByLabel("PO code").fill(poCode);
    await page.getByLabel("PO supplier").selectOption({ label: supplierLabel });
    await page.getByLabel("Linked requisition").selectOption({ label: reqLabel });
    await page.getByLabel("PO currency").fill("INR");
    await page.getByLabel("PO line description").fill("M10 hex bolt");
    await page.getByLabel("PO quantity").fill("50");
    await page.getByLabel("PO unit price").fill("5.00");
    await page.getByRole("button", { name: /^create po$/i }).click();
    await expect(page.locator("tr", { hasText: poCode })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("link", { name: "Requisitions" }).click();
    await expect(page.locator("tr", { hasText: reqCode })).toContainText("ordered", { timeout: 15_000 });
  });

  await test.step("approve the PO as a different persona (SoD)", async () => {
    await signOut(page);
    await signInAs(page, "Approver");
    await page.getByRole("link", { name: "Purchase orders" }).click();
    const poRow = page.locator("tr", { hasText: poCode });
    await poRow.getByRole("button", { name: /approve/i }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: /approve/i }).click();
    await expect(poRow).toContainText("approved", { timeout: 15_000 });
  });

  await test.step("as Buyer: send, receive goods and record the invoice", async () => {
    // Send/receive/invoice are operational steps, not approval decisions, but
    // the invoice still has to be approved by someone other than whoever
    // raised it — doing these as Buyer (who raised the PO) keeps that approval
    // meaningful in the next step, matching backend/tests/test_e2e_workflow.py.
    await signOut(page);
    await signInAs(page, "Buyer");
    await page.getByRole("link", { name: "Purchase orders" }).click();
    const poRow = page.locator("tr", { hasText: poCode });
    await poRow.getByRole("button", { name: /send to supplier/i }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: /send to supplier/i }).click();
    await expect(poRow).toContainText("sent", { timeout: 15_000 });

    await poRow.getByRole("button", { name: /^open$/i }).click();
    await page.getByRole("button", { name: /receive all goods/i }).click();
    await expect(page.getByText(/goods received/i).first()).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Invoice code").fill(invCode);
    await page.getByLabel("Invoice quantity").fill("50");
    await page.getByLabel("Invoice unit price").fill("5.00");
    await page.getByRole("button", { name: /record invoice/i }).click();
    await expect(page.locator("tr", { hasText: invCode })).toBeVisible({ timeout: 15_000 });
  });

  await test.step("approve the invoice as a different persona (3-way match) and verify the final state", async () => {
    await signOut(page);
    await signInAs(page, "Approver");
    await page.getByRole("link", { name: "Purchase orders" }).click();
    const poRow = page.locator("tr", { hasText: poCode });
    await poRow.getByRole("button", { name: /^open$/i }).click();
    const invRow = page.locator("tr", { hasText: invCode });
    await invRow.getByRole("button", { name: /approve/i }).click();
    await expect(invRow).toContainText("approved", { timeout: 15_000 });

    await page.getByRole("link", { name: "Purchase orders" }).click();
    await expect(poRow).toContainText("invoiced", { timeout: 15_000 });
    await expect(poRow).toContainText("250.00");

    await page.getByRole("link", { name: "Requisitions" }).click();
    await expect(page.locator("tr", { hasText: reqCode })).toContainText("ordered", { timeout: 15_000 });
  });

  expect(consoleErrors, `unexpected console/page errors during the run:\n${consoleErrors.join("\n")}`).toEqual([]);
});
