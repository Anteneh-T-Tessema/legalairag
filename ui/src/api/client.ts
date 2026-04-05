const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("indyleg_token");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

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

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  citations?: string[];
  confidence?: string;
  timestamp: number;
}

export interface IngestRequest {
  source_type: string;
  source_id: string;
  download_url: string;
  metadata?: Record<string, string>;
}

export interface IngestResponse {
  message_id: string;
  source_id: string;
  queued: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE.replace("/api/v1", "")}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = (await res.json()) as LoginResponse;
  localStorage.setItem("indyleg_token", data.access_token);
  return data;
}

export function logout(): void {
  localStorage.removeItem("indyleg_token");
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem("indyleg_token");
}

export async function ask(
  query: string,
  jurisdiction?: string
): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/search/ask`, {
    method: "POST",
    headers: authHeaders(),
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
  top_k = 5,
  jurisdiction?: string
): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ query, top_k, jurisdiction }),
  });
  if (!res.ok) {
    throw new Error(`Search failed (${res.status})`);
  }
  return res.json() as Promise<SearchResponse>;
}

export async function ingestDocument(req: IngestRequest): Promise<IngestResponse> {
  const res = await fetch(`${API_BASE}/documents/ingest`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`Ingest failed (${res.status})`);
  }
  return res.json() as Promise<IngestResponse>;
}
