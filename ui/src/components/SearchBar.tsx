import React from "react";

interface Props {
  query: string;
  onChange: (q: string) => void;
  onSubmit: () => void;
  loading: boolean;
  jurisdiction?: string;
  onJurisdictionChange?: (j: string) => void;
}

const JURISDICTIONS = [
  "Indiana", "Marion County", "Hamilton County", "Allen County",
  "Lake County", "St. Joseph County", "Vanderburgh County", "Tippecanoe County",
  "Elkhart County", "Monroe County", "Hendricks County",
];

export function SearchBar({ query, onChange, onSubmit, loading, jurisdiction, onJurisdictionChange }: Props) {
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
        aria-label="Search query"
      />
      <div className="search-controls">
        {onJurisdictionChange && (
          <select
            value={jurisdiction ?? ""}
            onChange={(e) => onJurisdictionChange(e.target.value)}
            aria-label="Filter by jurisdiction"
            className="jurisdiction-select"
          >
            <option value="">All jurisdictions</option>
            {JURISDICTIONS.map((j) => (
              <option key={j} value={j}>{j}</option>
            ))}
          </select>
        )}
        <button onClick={onSubmit} disabled={loading || query.trim().length < 3}>
          {loading ? "Researching…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
