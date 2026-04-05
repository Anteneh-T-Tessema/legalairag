import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ResultCard } from "../components/ResultCard";
import type { AskResponse } from "../api/client";

const baseResult: AskResponse = {
  query: "What is self defense?",
  answer: "Self defense is defined under Indiana Code...",
  source_ids: ["src-1", "src-2"],
  citations: ["Ind. Code § 35-41-3-2"],
  confidence: "High",
  run_id: "abcdef12-3456-7890-abcd-ef1234567890",
  validation_passed: true,
};

describe("ResultCard", () => {
  it("renders the answer text", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.getByText(/Self defense is defined/)).toBeInTheDocument();
  });

  it("renders confidence badge", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.getByText("High Confidence")).toBeInTheDocument();
  });

  it("renders truncated run id", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.getByText(/Run: abcdef12/)).toBeInTheDocument();
  });

  it("renders citations list", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.getByText("Ind. Code § 35-41-3-2")).toBeInTheDocument();
  });

  it("renders source ids", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.getByText("src-1, src-2")).toBeInTheDocument();
  });

  it("hides citations section when empty", () => {
    const noCtations = { ...baseResult, citations: [] };
    render(<ResultCard result={noCtations} />);
    expect(screen.queryByText("Statutes cited:")).not.toBeInTheDocument();
  });

  it("hides sources section when empty", () => {
    const noSources = { ...baseResult, source_ids: [] };
    render(<ResultCard result={noSources} />);
    expect(screen.queryByText("Sources:")).not.toBeInTheDocument();
  });

  it("shows validation warning when validation fails", () => {
    const failed = { ...baseResult, validation_passed: false };
    render(<ResultCard result={failed} />);
    expect(screen.getByText(/Validation warning/)).toBeInTheDocument();
  });

  it("hides validation warning when validation passes", () => {
    render(<ResultCard result={baseResult} />);
    expect(screen.queryByText(/Validation warning/)).not.toBeInTheDocument();
  });

  it("applies correct confidence class for Medium", () => {
    const medium = { ...baseResult, confidence: "Medium" as const };
    render(<ResultCard result={medium} />);
    expect(screen.getByText("Medium Confidence")).toBeInTheDocument();
  });

  it("applies correct confidence class for Low", () => {
    const low = { ...baseResult, confidence: "Low" as const };
    render(<ResultCard result={low} />);
    expect(screen.getByText("Low Confidence")).toBeInTheDocument();
  });
});
