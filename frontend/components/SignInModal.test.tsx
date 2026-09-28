import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SignInModal from "./SignInModal";
import * as auth from "../lib/auth";

describe("SignInModal component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(<SignInModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders certified executive personas when open", () => {
    render(<SignInModal isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByText("Sign In & Role Delegation")).toBeInTheDocument();
    expect(screen.getByText("Sarah Chen")).toBeInTheDocument();
    expect(screen.getByText("Marcus Vance")).toBeInTheDocument();
    expect(screen.getByText("Elena Rostova")).toBeInTheDocument();
    expect(screen.getByText("David Park")).toBeInTheDocument();
  });

  it("switches persona and calls onClose when a persona is selected", () => {
    const onClose = vi.fn();
    const switchSpy = vi.spyOn(auth, "switchPersona");
    render(<SignInModal isOpen={true} onClose={onClose} />);

    const marcusBtn = screen.getByRole("button", { name: /Marcus Vance/i });
    fireEvent.click(marcusBtn);

    expect(switchSpy).toHaveBeenCalledWith("category_lead");
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(<SignInModal isOpen={true} onClose={onClose} />);

    const closeBtn = screen.getByLabelText("Close sign-in modal");
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it("allows switching to custom enterprise identity tab and submitting", () => {
    const onClose = vi.fn();
    const loginSpy = vi.spyOn(auth, "login");
    render(<SignInModal isOpen={true} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Custom Enterprise Identity" }));
    expect(screen.getByText("Corporate Email")).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText("e.g. Jordan Hayes");
    fireEvent.change(nameInput, { target: { value: "Jordan Hayes" } });

    const submitBtn = screen.getByRole("button", { name: /Sign In to Enterprise Workspace/i });
    fireEvent.click(submitBtn);

    expect(loginSpy).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ name: "Jordan Hayes", tenant: "vantor-corp" }),
    );
    expect(onClose).toHaveBeenCalled();
  });
});
