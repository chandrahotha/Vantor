import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  Button,
  ConfirmDialog,
  Drawer,
  FilterBar,
  IconButton,
  MetricCard,
  Progress,
  Segmented,
  Timeline,
  ToastProvider,
  useToast,
} from "./ui";

/**
 * The Grade-5 primitives from
 * docs/05-frontend/grade5/DESIGN_SYSTEM.md.
 *
 * The design rule these tests exist to protect is that colour is never the only
 * signal. A red button that says "Reject" is safe; a red button with a glyph
 * and no label is not. So almost every assertion here is about the accessible
 * name, the role and the text — not about the class that carries the colour.
 */

describe("Button", () => {
  it("carries its variant and size as classes, not as inline colour", () => {
    const { container } = render(<Button variant="danger" size="lg">Reject</Button>);
    const b = container.querySelector("button");
    expect(b).toHaveClass("btn", "btn-danger", "btn-lg");
  });

  it("keeps its label while loading and blocks a second submit", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Create supplier
      </Button>,
    );
    const b = screen.getByRole("button", { name: /Create supplier/ });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("aria-busy", "true");
    // The label is still there, so the button does not resize and shift the
    // layout out from under the cursor while the request is in flight.
    expect(b).toHaveTextContent("Create supplier");
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not mark itself busy when idle", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button")).not.toHaveAttribute("aria-busy");
  });

  it("still fires when not loading", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("IconButton", () => {
  it("requires and exposes a text label — a glyph is not a name", () => {
    render(<IconButton label="Close panel" icon="✕" />);
    const b = screen.getByRole("button", { name: "Close panel" });
    // The glyph is decorative, so it must not be announced as the name.
    expect(b.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});

describe("Segmented", () => {
  const OPTIONS = [
    { value: "all" as const, label: "All" },
    { value: "open" as const, label: "Open" },
    { value: "closed" as const, label: "Closed" },
  ];

  it("is a radiogroup with one tab stop and roving arrow-key navigation", async () => {
    const onChange = vi.fn();
    render(<Segmented label="Filter" value="all" options={OPTIONS} onChange={onChange} />);

    const group = screen.getByRole("radiogroup", { name: "Filter" });
    expect(group).toBeTruthy();
    const radios = screen.getAllByRole("radio");
    // Exactly one tab stop: the selected item.
    expect(radios.filter((r) => r.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");

    radios[0].focus();
    fireEvent.keyDown(radios[0], { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("open");
  });

  it("wraps around at both ends", () => {
    const onChange = vi.fn();
    render(<Segmented label="Filter" value="all" options={OPTIONS} onChange={onChange} />);
    const radios = screen.getAllByRole("radio");
    fireEvent.keyDown(radios[0], { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("closed");
  });

  it("announces the selected option by checked state, not by styling", () => {
    render(<Segmented label="Filter" value="open" options={OPTIONS} onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Open" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "false");
  });
});

describe("Drawer", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <Drawer open={false} title="Supplier" onClose={vi.fn()}>
        body
      </Drawer>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("is a labelled modal dialog when open", () => {
    render(
      <Drawer open title="SUP-001" onClose={vi.fn()}>
        body
      </Drawer>,
    );
    const d = screen.getByRole("dialog", { name: "SUP-001" });
    expect(d).toHaveAttribute("aria-modal", "true");
    expect(d).toHaveTextContent("body");
  });

  it("closes on Escape and on the close control", async () => {
    const onClose = vi.fn();
    render(
      <Drawer open title="Supplier" onClose={onClose}>
        body
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("ConfirmDialog", () => {
  it("names the consequence and repeats the verb on the confirm button", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Award this RFQ?"
        body="Awarding books savings to the ledger and locks the award."
        confirmLabel="Award RFQ"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    // An alertdialog, because a confirmation interrupts.
    expect(screen.getByRole("alertdialog", { name: "Award this RFQ?" })).toBeInTheDocument();
    expect(screen.getByText(/books savings to the ledger/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Award RFQ" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("cancels without confirming", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog open title="t" body="b" confirmLabel="Do it" onConfirm={onConfirm} onCancel={onCancel} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("Toast", () => {
  function Trigger() {
    const toast = useToast();
    return (
      <>
        <button onClick={() => toast("ok", "Supplier SUP-001 created")}>succeed</button>
        <button onClick={() => toast("bad", "Create failed")}>fail</button>
      </>
    );
  }

  it("announces success politely and failure assertively", async () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText("succeed"));
    expect(screen.getByRole("status")).toHaveTextContent("Supplier SUP-001 created");

    await userEvent.click(screen.getByText("fail"));
    // An error must not be missed, so it is an alert rather than a status.
    expect(screen.getByRole("alert")).toHaveTextContent("Create failed");
  });
});

/**
 * Two things that once sat in `globals.css` and should not come back.
 *
 * Both are the same failure mode: a stylesheet that renders correctly while
 * describing a product that does not exist. The font tokens named a webfont
 * that was never shipped, and the persona sign-in surface kept its rules long
 * after the component that used them was deleted — so the styling for a
 * control that could mint a client-side Admin session was still sitting in the
 * stylesheet, waiting for someone to paste the markup back.
 */
describe("Grade-5 stylesheet: nothing describes a product that does not exist", () => {
  const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");
  const layout = readFileSync(join(process.cwd(), "app", "layout.tsx"), "utf8");

  // `next/font` emits these onto `<html>`; nothing in `globals.css` declares
  // them, so the "is it declared somewhere?" test below has to know where.
  const NEXT_FONT_VARIABLES = ["--font-inter", "--font-jetbrains"];

  it("resolves every custom property the font tokens reference", () => {
    // `--font-ui: var(--font-inter), system-ui, …` with no `@font-face` and no
    // font file resolves to `system-ui` and renders fine. It only *claims* a
    // webfont. An undefined custom property inside `var()` is invalid at
    // computed-value time, so the declaration silently falls through.
    for (const token of ["--font-ui", "--font-mono"]) {
      const value = css.match(new RegExp(`${token}:([^;]+);`))?.[1] ?? "";
      expect(value, `${token} is not declared`).not.toBe("");
      for (const [, referenced] of value.matchAll(/var\((--[a-z0-9-]+)\)/gi)) {
        const declared = new RegExp(`${referenced}\\s*:`).test(css);
        const fontFace = new RegExp(
          `@font-face[\\s\\S]{0,400}?${referenced}\\s*:`,
          "i",
        ).test(css);
        const fromNextFont = NEXT_FONT_VARIABLES.includes(referenced)
          && new RegExp(`variable:\\s*"${referenced}"`).test(layout);
        expect(
          declared || fontFace || fromNextFont,
          `${token} references ${referenced}, which is neither declared in ` +
            "globals.css, loaded by an @font-face, nor a next/font variable in " +
            "layout.tsx, so the token silently falls back",
        ).toBe(true);
      }
    }
  });

  it("renders the webfonts next/font actually ships", () => {
    // The inverse of the test above, and the one that catches the real defect.
    // B-24's first fix removed the *claim* from these tokens instead of making
    // the claim true: they named the raw system stack, while `layout.tsx` kept
    // downloading Inter and JetBrains Mono and applying them to `<html>`. Two
    // webfonts on every page load, neither rendered, and a stylesheet header
    // comment asserting the opposite. Deleting the assertion is not the same as
    // fixing the stylesheet, so the tokens have to name the shipped fonts.
    for (const variable of NEXT_FONT_VARIABLES) {
      expect(layout, `layout.tsx no longer provides ${variable}`).toMatch(
        new RegExp(`variable:\\s*"${variable}"`),
      );
    }
    for (const [token, variable] of [
      ["--font-ui", "--font-inter"],
      ["--font-mono", "--font-jetbrains"],
    ]) {
      const value = css.match(new RegExp(`${token}:([^;]+);`))?.[1] ?? "";
      expect(
        value,
        `${token} must reference ${variable}, or the webfont is dead weight`,
      ).toContain(`var(${variable})`);
    }
  });

  it("keeps no rules for the removed client-side identity switcher", () => {
    // `SignInModal` minted a session from a name and a role chosen in a
    // dropdown. It is gone, and so is every rule that would style it.
    const removed = [
      ".persona-",
      ".personas-list",
      ".custom-login-form",
      ".custom-submit-btn",
      ".userchip-switch",
      ".authscreen-demo-cta",
      ".authscreen-sso-cta",
      ".authscreen-kbd-note",
    ];
    for (const selector of removed) {
      expect(css, `dead rule for removed control: ${selector}`).not.toContain(selector);
    }
  });
});

describe("MetricCard", () => {
  it("shows direction as a signed value with a glyph, never colour alone", () => {
    render(<MetricCard label="Leakage" value="12,000 INR" tone="bad" trend={{ value: "-8.2%", dir: "down" }} />);
    expect(screen.getByText("-8.2%")).toBeInTheDocument();
    // Tone is present as a data attribute for styling, but the text carries it.
    expect(screen.getByText("12,000 INR")).toBeInTheDocument();
  });

  it("explains itself when a hint is given, as visible text tied to the metric", () => {
    // The definition must not be hover-only — that is the point of this
    // assertion, and it still holds. It is no longer given `role="tooltip"`:
    // that role describes a popup, and this has always been permanently
    // rendered text. The binding is `aria-describedby`, which is what actually
    // associates a description with the thing it describes.
    const { container } = render(<MetricCard label="Committed" value="1.0M" hint="Approved POs only" />);
    const hint = screen.getByText("Approved POs only");
    expect(hint).toBeVisible();
    const metric = container.querySelector(".metric");
    expect(metric).toHaveAttribute("aria-describedby", hint.id);
    expect(hint.id).toBeTruthy();
  });
});

describe("Progress", () => {
  it("exposes the value numerically, not only as a filled div", () => {
    render(<Progress value={42.4} label="Budget used" />);
    const bar = screen.getByRole("progressbar", { name: "Budget used" });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps out-of-range values rather than rendering a broken bar", () => {
    const { rerender } = render(<Progress value={-20} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    rerender(<Progress value={480} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});

describe("FilterBar and Timeline", () => {
  it("marks the filter surface as a search region", () => {
    render(
      <FilterBar>
        <label>Search</label>
      </FilterBar>,
    );
    expect(screen.getByRole("search")).toBeInTheDocument();
  });
  it("renders an empty timeline as an empty state, not a bare gap", () => {
    render(<Timeline items={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("No activity yet");
  });

  it("renders entries with their metadata", () => {
    render(<Timeline items={[{ title: "RFQ_AWARDED", meta: "2 minutes ago", tone: "ok" }]} />);
    expect(screen.getByText("RFQ_AWARDED")).toBeInTheDocument();
    expect(screen.getByText("2 minutes ago")).toBeInTheDocument();
  });
});

/**
 * Contrast is a property of the stylesheet, not of any React component, so it
 * cannot be asserted from a render. These read `globals.css` directly.
 *
 * The trap they guard is specific and easy to walk into: every palette declares
 * an `--accent` that is deliberately *vivid* — sapphire's is #0ea5e9, which is
 * 2.77:1 on white. That is fine for a 3:1 non-text boundary and it is what the
 * large gradient fills are for. It is not fine behind a button label, which
 * needs 4.5:1. A gradient ending on `--accent` therefore looked correct and
 * shipped unreadable white text.
 */
describe("Grade-5 stylesheet: text contrast", () => {
  const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

  it("does not paint a text-bearing fill with a palette accent", () => {
    // The rule body for .btn-primary, up to its closing brace.
    const rule = css.match(/\.btn-primary\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/background:[^;]*var\(--primary\)/);
    // The accent may still tint the border; it may not be the fill. Matched
    // without the closing paren so a `var(--accent, fallback)` form is caught
    // too — pinning `var(--accent)` exactly let that through.
    expect(rule).not.toMatch(/background:[^;]*var\(--accent/);
  });

  it("uses the AA-checked primary steps for the sign-in CTA too", () => {
    const rule = css.match(/\[data-palette\]\s*\.authscreen-cta\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/background:[^;]*var\(--primary\)/);
    expect(rule).not.toMatch(/background:[^;]*var\(--accent/);
  });

  it("keeps the outcome colours palette-independent", () => {
    // A red "rejected" badge is a fact about the world, so it must not move
    // when a tenant changes palette. These are defined once in :root and never
    // re-declared per palette.
    const perPalette = css.match(/\[data-palette="[a-z]+"\][^{]*\{[^}]*--status-rejected/g) ?? [];
    expect(perPalette).toHaveLength(0);
  });
});
