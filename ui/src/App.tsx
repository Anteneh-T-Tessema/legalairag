import { useState } from "react";
import { SearchBar } from "./components/SearchBar";
import { ResultCard } from "./components/ResultCard";
import { ChatInterface } from "./components/ChatInterface";
import { SearchResults } from "./components/SearchResults";
import { DocumentUpload } from "./components/DocumentUpload";
import { FraudAnalysis } from "./components/FraudAnalysis";
import { LoginForm } from "./components/LoginForm";
import { ask, isAuthenticated, logout } from "./api/client";
import type { AskResponse } from "./api/client";

type Tab = "ask" | "search" | "chat" | "fraud" | "documents";

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [tab, setTab] = useState<Tab>("ask");
  const [query, setQuery] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!authed) {
    return <LoginForm onLogin={() => setAuthed(true)} />;
  }

  const handleAsk = async () => {
    if (query.trim().length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await ask(query, jurisdiction || undefined);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    setAuthed(false);
  };

  return (
    <div className="app">
      <header>
        <div className="header-top">
          <div>
            <h1>IndyLeg</h1>
            <p>Indiana Legal Research Platform</p>
          </div>
          <button className="logout-btn" onClick={handleLogout}>Sign Out</button>
        </div>
        <nav className="tabs">
          <button className={tab === "ask" ? "active" : ""} onClick={() => setTab("ask")}>
            Ask
          </button>
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>
            Search
          </button>
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button className={tab === "fraud" ? "active" : ""} onClick={() => setTab("fraud")}>
            Fraud Analysis
          </button>
          <button className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}>
            Documents
          </button>
        </nav>
      </header>

      <main>
        {tab === "ask" && (
          <>
            <SearchBar
              query={query}
              onChange={setQuery}
              onSubmit={handleAsk}
              loading={loading}
              jurisdiction={jurisdiction}
              onJurisdictionChange={setJurisdiction}
            />
            {error && <div className="error">{error}</div>}
            {result && <ResultCard result={result} />}
          </>
        )}

        {tab === "search" && <SearchResults jurisdiction={jurisdiction} />}
        {tab === "chat" && <ChatInterface jurisdiction={jurisdiction} />}
        {tab === "fraud" && <FraudAnalysis />}
        {tab === "documents" && <DocumentUpload />}
      </main>

      <footer>
        <small>
          Outputs are AI-generated research aids, not legal advice. Always verify
          with a licensed Indiana attorney.
        </small>
      </footer>
    </div>
  );
}
