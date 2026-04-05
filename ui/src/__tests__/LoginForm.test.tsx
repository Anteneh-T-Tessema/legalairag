import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LoginForm } from "../components/LoginForm";

// Mock the API client
vi.mock("../api/client", () => ({
  login: vi.fn(),
}));

import { login } from "../api/client";

describe("LoginForm", () => {
  const mockOnLogin = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders username and password fields", () => {
    render(<LoginForm onLogin={mockOnLogin} />);
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders IndyLeg heading", () => {
    render(<LoginForm onLogin={mockOnLogin} />);
    expect(screen.getByText("IndyLeg")).toBeInTheDocument();
  });

  it("renders sign in button", () => {
    render(<LoginForm onLogin={mockOnLogin} />);
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
  });

  it("calls onLogin after successful login", async () => {
    (login as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    render(<LoginForm onLogin={mockOnLogin} />);

    await userEvent.type(screen.getByLabelText("Username"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "admin123");
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(mockOnLogin).toHaveBeenCalled();
    });
  });

  it("shows error on failed login", async () => {
    (login as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("bad"));
    render(<LoginForm onLogin={mockOnLogin} />);

    await userEvent.type(screen.getByLabelText("Username"), "bad");
    await userEvent.type(screen.getByLabelText("Password"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(screen.getByText("Invalid username or password")).toBeInTheDocument();
    });
  });

  it("disables button while loading", async () => {
    let resolveLogin: () => void;
    (login as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise<void>((r) => { resolveLogin = r; })
    );
    render(<LoginForm onLogin={mockOnLogin} />);

    await userEvent.type(screen.getByLabelText("Username"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
    resolveLogin!();
  });
});
