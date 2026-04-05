import { useState } from "react";
import { SearchBar } from "./components/SearchBar";
import { ResultCard } from "./components/ResultCard";
import { ask } from "./api/client";
import type { AskResponse } from "./api/client";

export default function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (query.trim().length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await ask(query);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>IndyLeg</h1>
        <p>Indiana Legal Research Assistant</p>
      </header>

      <main>
        <SearchBar
          query={query}
          onChange={setQuery}
          onSubmit={handleAsk}
          loading={loading}
        />

        {error && <div className="error">{error}</div>}
        {result && <ResultCard result={result} />}
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
