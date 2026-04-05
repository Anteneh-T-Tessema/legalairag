import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SearchResults } from "../components/SearchResults";

vi.mock("../api/client", () => ({
  search: vi.fn(),
}));

import { search } from "../api/client";

describe("SearchResults", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders search input", () => {
    render(<SearchResults />);
    expect(screen.getByPlaceholderText("Search legal documents...")).toBeInTheDocument();
  });

  it("renders Search button", () => {
    render(<SearchResults />);
    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
  });

  it("disables Search button for short query", () => {
    render(<SearchResults />);
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
  });

  it("enables Search button for valid query", async () => {
    render(<SearchResults />);
    const input = screen.getByPlaceholderText("Search legal documents...");
    await userEvent.type(input, "eviction notice");
    expect(screen.getByRole("button", { name: "Search" })).not.toBeDisabled();
  });

  it("shows results after search", async () => {
    const mockSearch = vi.mocked(search);
    mockSearch.mockResolvedValueOnce({
      query: "eviction",
      results: [
        {
          chunk_id: "c1",
          source_id: "src-1",
          section: "§1",
          content: "Eviction notice requirements under Indiana law.",
          citations: ["Ind. Code § 32-31-1-6"],
          score: 0.95,
        },
      ],
      jurisdiction: null,
      total: 1,
    });

    render(<SearchResults />);
    const input = screen.getByPlaceholderText("Search legal documents...");
    await userEvent.type(input, "eviction");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("1 results found")).toBeInTheDocument();
    expect(screen.getByText("src-1")).toBeInTheDocument();
    expect(screen.getByText(/Eviction notice requirements/)).toBeInTheDocument();
  });

  it("shows error on search failure", async () => {
    const mockSearch = vi.mocked(search);
    mockSearch.mockRejectedValueOnce(new Error("Search failed"));

    render(<SearchResults />);
    const input = screen.getByPlaceholderText("Search legal documents...");
    await userEvent.type(input, "eviction");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Search failed")).toBeInTheDocument();
  });
});
