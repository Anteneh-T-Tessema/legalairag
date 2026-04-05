import type { AskResponse } from "../api/client";

interface Props {
  result: AskResponse;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  High: "#1a7f37",
  Medium: "#9a6700",
  Low: "#cf222e",
};

export function ResultCard({ result }: Props) {
  const color = CONFIDENCE_COLORS[result.confidence] ?? "#444";

  return (
    <div className="result-card">
      <div className="result-header">
        <span className="confidence-badge" style={{ color }}>
          {result.confidence} Confidence
        </span>
        <span className="run-id">Run: {result.run_id.slice(0, 8)}</span>
      </div>

      <div className="answer">{result.answer}</div>

      {result.citations.length > 0 && (
        <div className="citations">
          <strong>Statutes cited:</strong>
          <ul>
            {result.citations.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {result.source_ids.length > 0 && (
        <div className="sources">
          <strong>Sources:</strong>{" "}
          {result.source_ids.join(", ")}
        </div>
      )}

      {!result.validation_passed && (
        <div className="validation-warning">
          ⚠ Validation warning: output may contain unverified claims.
        </div>
      )}
    </div>
  );
}
