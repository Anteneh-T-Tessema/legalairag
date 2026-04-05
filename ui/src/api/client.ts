const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

export interface AskResponse {
  query: string;
  answer: string;
  source_ids: string[];
  citations: string[];
  confidence: "High" | "Medium" | "Low";
  run_id: string;
  validation_passed: boolean;
}

export interface SearchResultItem {
  chunk_id: string;
  source_id: string;
  section: string;
  content: string;
  citations: string[];
  score: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
  jurisdiction: string | null;
  total: number;
}

export async function ask(
  query: string,
  jurisdiction?: string
): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/search/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, jurisdiction }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Ask failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<AskResponse>;
}

export async function search(
  query: string,
  top_k = 5
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k }),
  });
  if (!res.ok) {
    throw new Error(`Search failed (${res.status})`);
  }
  return res.json() as Promise<SearchResponse>;
}
