import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SearchBar } from "../components/SearchBar";

describe("SearchBar", () => {
  const defaults = {
    query: "",
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    loading: false,
  };

  it("renders textarea with placeholder", () => {
    render(<SearchBar {...defaults} />);
    expect(screen.getByRole("textbox", { name: "Search query" })).toBeInTheDocument();
  });

  it("renders Ask button", () => {
    render(<SearchBar {...defaults} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("disables button when query is too short", () => {
    render(<SearchBar {...defaults} query="ab" />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  it("enables button when query is long enough", () => {
    render(<SearchBar {...defaults} query="Indiana property law" />);
    expect(screen.getByRole("button", { name: "Ask" })).not.toBeDisabled();
  });

  it("calls onChange when typing", async () => {
    const onChange = vi.fn();
    render(<SearchBar {...defaults} onChange={onChange} />);
    const textarea = screen.getByRole("textbox", { name: "Search query" });
    await userEvent.type(textarea, "test");
    expect(onChange).toHaveBeenCalled();
  });

  it("calls onSubmit when button clicked", async () => {
    const onSubmit = vi.fn();
    render(<SearchBar {...defaults} query="valid query text" onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(onSubmit).toHaveBeenCalled();
  });

  it("shows jurisdiction dropdown when handler provided", () => {
    render(
      <SearchBar
        {...defaults}
        jurisdiction=""
        onJurisdictionChange={vi.fn()}
      />
    );
    expect(screen.getByRole("combobox", { name: "Filter by jurisdiction" })).toBeInTheDocument();
  });

  it("shows loading state", () => {
    render(<SearchBar {...defaults} loading={true} />);
    expect(screen.getByRole("button", { name: "Researching…" })).toBeDisabled();
  });
});
