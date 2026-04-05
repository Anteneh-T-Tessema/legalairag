import { useState } from "react";
import { search } from "../api/client";
import type { SearchResultItem, SearchResponse } from "../api/client";

interface Props {
  jurisdiction?: string;
}

export function SearchResults({ jurisdiction }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<SearchResultItem | null>(null);

  const handleSearch = async () => {
    if (query.trim().length < 3) return;
    setLoading(true);
    setError(null);
    try {
      const res: SearchResponse = await search(query, 10, jurisdiction || undefined);
      setResults(res.results);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="search-results-page">
      <div className="search-input-row">
        <input
          type="text"
          placeholder="Search legal documents..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          disabled={loading}
        />
        <button onClick={handleSearch} disabled={loading || query.trim().length < 3}>
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {results.length > 0 && (
        <div className="results-layout">
          <div className="results-list">
            <p className="results-count">{total} results found</p>
            {results.map((item) => (
              <div
                key={item.chunk_id}
                className={`result-item ${selectedChunk?.chunk_id === item.chunk_id ? "result-item--selected" : ""}`}
                onClick={() => setSelectedChunk(item)}
              >
                <div className="result-item-header">
                  <span className="source-badge">{item.source_id}</span>
                  <span className="section-badge">{item.section}</span>
                  <span className="score-badge">{(item.score * 100).toFixed(1)}%</span>
                </div>
                <p className="result-item-content">{item.content}</p>
                {item.citations.length > 0 && (
                  <div className="result-item-citations">
                    {item.citations.map((c) => (
                      <span key={c} className="citation-tag">{c}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {selectedChunk && (
            <div className="document-preview">
              <h3>Document Viewer</h3>
              <div className="preview-meta">
                <p><strong>Source:</strong> {selectedChunk.source_id}</p>
                <p><strong>Section:</strong> {selectedChunk.section}</p>
                <p><strong>Relevance:</strong> {(selectedChunk.score * 100).toFixed(1)}%</p>
              </div>
              <div className="preview-content">
                {selectedChunk.content}
              </div>
              {selectedChunk.citations.length > 0 && (
                <div className="preview-citations">
                  <strong>Citations:</strong>
                  <ul>
                    {selectedChunk.citations.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
