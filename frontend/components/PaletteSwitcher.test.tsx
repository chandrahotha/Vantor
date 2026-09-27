import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PaletteSwitcher from "./PaletteSwitcher";
import { PALETTES } from "../lib/palette";

/**
 * The palette cards are five independent toggles, and the semantics have to match
 * that.
 *
 * The first version used `role="radio"` inside a `role="radiogroup"`. That
 * obliges the author to implement roving tabindex and arrow-key navigation,
 * because a screen reader announces "radio group" and the user's next keypress
 * is expected to be an arrow. Only Tab and Enter worked, so the declared
 * semantics were a promise the component did not keep — and `role="radio"` on a
 * `<button>` also discards the native button role. A control whose announced
 * behaviour does not match its behaviour is worse than one with weaker
 * semantics, because the user is told what to expect and is then wrong.
 */

vi.mock("../lib/useTenantBrandOverride", () => ({
  useTenantBrandOverride: () => ({}),
}));

describe("palette switcher accessibility", () => {
  it("offers one real button per palette", () => {
    render(<PaletteSwitcher />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(PALETTES.length);
    // Every one is a native button, so it is focusable and Enter/Space works.
    for (const button of buttons) {
      expect(button.tagName).toBe("BUTTON");
      expect(button).toHaveAttribute("type", "button");
    }
  });

  it("does not claim to be a radio group", () => {
    const { container } = render(<PaletteSwitcher />);
    expect(container.querySelector('[role="radiogroup"]')).toBeNull();
    expect(container.querySelector('[role="radio"]')).toBeNull();
    // A plain group, which promises nothing beyond the grouping.
    expect(screen.getByRole("group", { name: /colour palette/i })).toBeInTheDocument();
  });

  it("marks the active palette with aria-pressed, not colour alone", () => {
    render(<PaletteSwitcher />);
    const pressed = screen.getAllByRole("button", { pressed: true });
    expect(pressed).toHaveLength(1);
    // The default is Graphite.
    expect(pressed[0]).toHaveAttribute("data-palette-card", "graphite");
    // And the choice is stated in text as well, so it does not depend on colour.
    expect(pressed[0].textContent).toMatch(/active/i);
  });

  it("is fully operable from the keyboard", async () => {
    const user = userEvent.setup();
    render(<PaletteSwitcher />);

    const amber = screen.getByRole("button", { name: /Spend Amber/ });
    amber.focus();
    expect(amber).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(amber).toHaveAttribute("aria-pressed", "true");

    const others = screen.getAllByRole("button", { pressed: true });
    expect(others).toHaveLength(1);
    expect(others[0]).toHaveAttribute("data-palette-card", "amber");
  });

  it("selects with a click too, and updates the summary", async () => {
    const user = userEvent.setup();
    render(<PaletteSwitcher />);
    await user.click(screen.getByRole("button", { name: /Contract Sapphire/ }));
    expect(screen.getByRole("button", { pressed: true }))
      .toHaveAttribute("data-palette-card", "sapphire");
    // The summary paragraph restates the choice in prose. Matched on the "Active:"
    // prefix because the name also appears on the card itself.
    const summary = screen.getByText(/^Active:/);
    expect(summary.textContent).toMatch(/Contract Sapphire/);
  });

  it("names the purpose of a palette in text, not just in colour", () => {
    render(<PaletteSwitcher />);
    for (const palette of PALETTES) {
      const card = screen.getByRole("button", { name: new RegExp(palette.name, "i") });
      expect(card.textContent).toMatch(new RegExp(palette.tagline.split(" ")[0], "i"));
    }
  });

  it("groups the cards so the set is announced as one control", () => {
    const { container } = render(<PaletteSwitcher />);
    const group = container.querySelector('[role="group"]') as HTMLElement;
    expect(within(group).getAllByRole("button").length).toBe(PALETTES.length);
  });
});
