import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatInterface } from "../components/ChatInterface";

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = vi.fn();

// Mock the API client
vi.mock("../api/client", () => ({
  ask: vi.fn(),
}));

import { ask } from "../api/client";

describe("ChatInterface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state with suggestions", () => {
    render(<ChatInterface />);
    expect(screen.getByText("Indiana Legal Research Chat")).toBeInTheDocument();
  });

  it("renders suggestion buttons", () => {
    render(<ChatInterface />);
    expect(screen.getByText(/Filing deadlines/)).toBeInTheDocument();
    expect(screen.getByText(/Self-defense/)).toBeInTheDocument();
  });

  it("renders input textarea", () => {
    render(<ChatInterface />);
    expect(screen.getByPlaceholderText("Ask a legal question...")).toBeInTheDocument();
  });

  it("renders disabled Send button for short input", () => {
    render(<ChatInterface />);
    const btn = screen.getByRole("button", { name: "Send" });
    expect(btn).toBeDisabled();
  });

  it("enables Send button for valid input", async () => {
    render(<ChatInterface />);
    const textarea = screen.getByPlaceholderText("Ask a legal question...");
    await userEvent.type(textarea, "What is self defense in Indiana?");
    const btn = screen.getByRole("button", { name: "Send" });
    expect(btn).not.toBeDisabled();
  });

  it("sends message and shows response", async () => {
    const mockAsk = vi.mocked(ask);
    mockAsk.mockResolvedValueOnce({
      query: "test",
      answer: "The answer is X.",
      source_ids: ["s1"],
      citations: ["Cite 1"],
      confidence: "High",
      run_id: "run-123",
      validation_passed: true,
    });

    render(<ChatInterface />);
    const textarea = screen.getByPlaceholderText("Ask a legal question...");
    await userEvent.type(textarea, "What is self defense?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    // User message should appear
    expect(await screen.findByText("What is self defense?")).toBeInTheDocument();
    // Assistant message should appear
    expect(await screen.findByText("The answer is X.")).toBeInTheDocument();
  });

  it("shows error message on API failure", async () => {
    const mockAsk = vi.mocked(ask);
    mockAsk.mockRejectedValueOnce(new Error("Network error"));

    render(<ChatInterface />);
    const textarea = screen.getByPlaceholderText("Ask a legal question...");
    await userEvent.type(textarea, "What is self defense?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/Network error/)).toBeInTheDocument();
  });

  it("passes jurisdiction prop to API", async () => {
    const mockAsk = vi.mocked(ask);
    mockAsk.mockResolvedValueOnce({
      query: "q",
      answer: "A",
      source_ids: [],
      citations: [],
      confidence: "Low",
      run_id: "r",
      validation_passed: true,
    });

    render(<ChatInterface jurisdiction="Marion County" />);
    const textarea = screen.getByPlaceholderText("Ask a legal question...");
    await userEvent.type(textarea, "What is self defense?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("A");
    expect(mockAsk).toHaveBeenCalledWith("What is self defense?", "Marion County");
  });
});
