import type { AskResponse } from "../api/client";

interface Props {
  result: AskResponse;
}

const CONFIDENCE_CLASSES: Record<string, string> = {
  High: "confidence-high",
  Medium: "confidence-medium",
  Low: "confidence-low",
};

export function ResultCard({ result }: Props) {
  const cls = CONFIDENCE_CLASSES[result.confidence] ?? "";

  return (
    <div className="result-card">
      <div className="result-header">
        <span className={`confidence-badge ${cls}`}>
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
