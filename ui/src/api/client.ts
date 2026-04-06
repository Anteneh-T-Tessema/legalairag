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

export interface FraudIndicator {
  indicator_type: string;
  severity: "low" | "medium" | "high" | "critical";
  description: string;
  evidence: string[];
  confidence: number;
}

export interface FraudAnalysisResponse {
  run_id: string;
  query_context: string;
  risk_level: "none" | "low" | "medium" | "high" | "critical";
  requires_human_review: boolean;
  total_filings_analyzed: number;
  flagged_source_ids: string[];
  summary: string;
  indicators: FraudIndicator[];
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: string;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = (await res.json()) as LoginResponse;
  localStorage.setItem("indyleg_token", data.access_token);
  localStorage.setItem("indyleg_refresh", data.refresh_token ?? "");
  return data;
}

export function logout(): void {
  localStorage.removeItem("indyleg_token");
  localStorage.removeItem("indyleg_refresh");
}

export function isAuthenticated(): boolean {
  return !!localStorage.getItem("indyleg_token");
}

export async function validateToken(): Promise<boolean> {
  const token = localStorage.getItem("indyleg_token");
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
    if (res.ok) return true;
    if (res.status === 401 && (await refreshAccessToken())) return true;
    logout();
    return false;
  } catch {
    return false;
  }
}

async function refreshAccessToken(): Promise<boolean> {
  const refresh = localStorage.getItem("indyleg_refresh");
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { access_token: string; refresh_token: string };
    localStorage.setItem("indyleg_token", data.access_token);
    localStorage.setItem("indyleg_refresh", data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

export async function ask(
  query: string,
  jurisdiction?: string
): Promise<AskResponse> {
  let res = await fetch(`${API_BASE}/search/ask`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ query, jurisdiction }),
  });
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await fetch(`${API_BASE}/search/ask`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ query, jurisdiction }),
    });
  }
  if (!res.ok) {
    if (res.status === 401) { logout(); window.location.reload(); return undefined as never; }
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
  let res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ query, top_k, jurisdiction }),
  });
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await fetch(`${API_BASE}/search`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ query, top_k, jurisdiction }),
    });
  }
  if (!res.ok) {
    if (res.status === 401) { logout(); window.location.reload(); return undefined as never; }
    throw new Error(`Search failed (${res.status})`);
  }
  return res.json() as Promise<SearchResponse>;
}

export async function ingestDocument(req: IngestRequest): Promise<IngestResponse> {
  let res = await fetch(`${API_BASE}/documents/ingest`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(req),
  });
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await fetch(`${API_BASE}/documents/ingest`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(req),
    });
  }
  if (!res.ok) {
    if (res.status === 401) { logout(); window.location.reload(); return undefined as never; }
    throw new Error(`Ingest failed (${res.status})`);
  }
  return res.json() as Promise<IngestResponse>;
}

export async function analyzeFraud(query: string): Promise<FraudAnalysisResponse> {
  let res = await fetch(`${API_BASE}/fraud/analyze`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ query }),
  });
  if (res.status === 401 && (await refreshAccessToken())) {
    res = await fetch(`${API_BASE}/fraud/analyze`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ query }),
    });
  }
  if (!res.ok) {
    if (res.status === 401) { logout(); window.location.reload(); return undefined as never; }
    const detail = await res.text();
    throw new Error(`Fraud analysis failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<FraudAnalysisResponse>;
}
