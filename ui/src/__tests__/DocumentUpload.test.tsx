import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DocumentUpload } from "../components/DocumentUpload";

vi.mock("../api/client", () => ({
  ingestDocument: vi.fn(),
}));

import { ingestDocument } from "../api/client";

describe("DocumentUpload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders heading", () => {
    render(<DocumentUpload />);
    expect(screen.getByText("Ingest Document")).toBeInTheDocument();
  });

  it("renders source type dropdown", () => {
    render(<DocumentUpload />);
    expect(screen.getByLabelText("Source Type")).toBeInTheDocument();
  });

  it("renders source id input", () => {
    render(<DocumentUpload />);
    expect(screen.getByLabelText("Source ID / Case Number")).toBeInTheDocument();
  });

  it("renders document URL input", () => {
    render(<DocumentUpload />);
    expect(screen.getByLabelText("Document URL")).toBeInTheDocument();
  });

  it("disables submit when fields are empty", () => {
    render(<DocumentUpload />);
    expect(screen.getByRole("button", { name: /Queue for Ingestion/ })).toBeDisabled();
  });

  it("enables submit when fields are filled", async () => {
    render(<DocumentUpload />);
    await userEvent.type(screen.getByLabelText("Source ID / Case Number"), "CASE-1");
    await userEvent.type(screen.getByLabelText("Document URL"), "https://example.com/doc.pdf");
    expect(screen.getByRole("button", { name: /Queue for Ingestion/ })).not.toBeDisabled();
  });

  it("submits and shows success message", async () => {
    const mockIngest = vi.mocked(ingestDocument);
    mockIngest.mockResolvedValueOnce({
      message_id: "msg-123",
      source_id: "CASE-1",
      queued: true,
    });

    render(<DocumentUpload />);
    await userEvent.type(screen.getByLabelText("Source ID / Case Number"), "CASE-1");
    await userEvent.type(screen.getByLabelText("Document URL"), "https://example.com/doc.pdf");
    await userEvent.click(screen.getByRole("button", { name: /Queue for Ingestion/ }));

    expect(await screen.findByText(/Queued for processing/)).toBeInTheDocument();
  });

  it("shows error on failure", async () => {
    const mockIngest = vi.mocked(ingestDocument);
    mockIngest.mockRejectedValueOnce(new Error("Upload failed"));

    render(<DocumentUpload />);
    await userEvent.type(screen.getByLabelText("Source ID / Case Number"), "CASE-1");
    await userEvent.type(screen.getByLabelText("Document URL"), "https://example.com/doc.pdf");
    await userEvent.click(screen.getByRole("button", { name: /Queue for Ingestion/ }));

    expect(await screen.findByText("Upload failed")).toBeInTheDocument();
  });

  it("clears form fields on success", async () => {
    const mockIngest = vi.mocked(ingestDocument);
    mockIngest.mockResolvedValueOnce({
      message_id: "msg-1",
      source_id: "X",
      queued: true,
    });

    render(<DocumentUpload />);
    const sourceInput = screen.getByLabelText("Source ID / Case Number") as HTMLInputElement;
    const urlInput = screen.getByLabelText("Document URL") as HTMLInputElement;

    await userEvent.type(sourceInput, "CASE-1");
    await userEvent.type(urlInput, "https://x.com/d.pdf");
    await userEvent.click(screen.getByRole("button", { name: /Queue for Ingestion/ }));

    await screen.findByText(/Queued for processing/);
    expect(sourceInput.value).toBe("");
    expect(urlInput.value).toBe("");
  });
});
