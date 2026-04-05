import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FraudAnalysis } from "../components/FraudAnalysis";

vi.mock("../api/client", () => ({
  analyzeFraud: vi.fn(),
}));

import { analyzeFraud } from "../api/client";

const mockResult = {
  run_id: "run-001",
  query_context: "John Doe",
  risk_level: "high",
  requires_human_review: true,
  total_filings_analyzed: 42,
  flagged_source_ids: ["IND-2024-001"],
  summary: "Suspicious burst filing detected.",
  indicators: [
    {
      indicator_type: "burst_filing",
      severity: "high",
      description: "12 filings in 3 days",
      evidence: ["IND-2024-001", "IND-2024-002"],
      confidence: 0.92,
    },
  ],
};

describe("FraudAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders heading and input", () => {
    render(<FraudAnalysis />);
    expect(screen.getByText("Fraud Pattern Analysis")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/party name/)).toBeInTheDocument();
  });

  it("disables analyze button when query is too short", () => {
    render(<FraudAnalysis />);
    expect(screen.getByRole("button", { name: "Analyze" })).toBeDisabled();
  });

  it("enables button when query is typed", async () => {
    render(<FraudAnalysis />);
    await userEvent.type(screen.getByPlaceholderText(/party name/), "John Doe");
    expect(screen.getByRole("button", { name: "Analyze" })).not.toBeDisabled();
  });

  it("shows results after successful analysis", async () => {
    (analyzeFraud as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockResult);
    render(<FraudAnalysis />);

    await userEvent.type(screen.getByPlaceholderText(/party name/), "John Doe");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));

    await waitFor(() => {
      expect(screen.getByText("Risk Level")).toBeInTheDocument();
    });
    expect(screen.getByText("Suspicious burst filing detected.")).toBeInTheDocument();
    expect(screen.getByText("burst filing")).toBeInTheDocument();
  });

  it("shows error on failed analysis", async () => {
    (analyzeFraud as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("Server down"));
    render(<FraudAnalysis />);

    await userEvent.type(screen.getByPlaceholderText(/party name/), "test query");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));

    await waitFor(() => {
      expect(screen.getByText("Server down")).toBeInTheDocument();
    });
  });

  it("shows loading state during analysis", async () => {
    let resolveAnalyze: (v: typeof mockResult) => void;
    (analyzeFraud as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise((r) => { resolveAnalyze = r; })
    );
    render(<FraudAnalysis />);

    await userEvent.type(screen.getByPlaceholderText(/party name/), "test query");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));

    expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
    resolveAnalyze!(mockResult);
  });
});
