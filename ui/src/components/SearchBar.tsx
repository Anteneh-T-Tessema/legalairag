import React from "react";

interface Props {
  query: string;
  onChange: (q: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export function SearchBar({ query, onChange, onSubmit, loading }: Props) {
  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="search-bar">
      <textarea
        rows={3}
        placeholder="Ask a legal question, e.g. 'What are the penalties for possession of a controlled substance under Indiana Code?'"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        disabled={loading}
      />
      <button onClick={onSubmit} disabled={loading || query.trim().length < 3}>
        {loading ? "Researching…" : "Ask"}
      </button>
    </div>
  );
}
