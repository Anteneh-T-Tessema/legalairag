import { useState } from "react";
import { analyzeFraud } from "../api/client";
import type { FraudAnalysisResponse, FraudIndicator } from "../api/client";

const RISK_CLASSES: Record<string, string> = {
  none: "risk-none",
  low: "risk-low",
  medium: "risk-medium",
  high: "risk-high",
  critical: "risk-critical",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`severity-badge severity-badge-${severity}`}>
      {severity.toUpperCase()}
    </span>
  );
}

function IndicatorCard({ indicator }: { indicator: FraudIndicator }) {
  return (
    <div className="indicator-card">
      <div className="indicator-header">
        <SeverityBadge severity={indicator.severity} />
        <span className="indicator-type">{indicator.indicator_type.replace(/_/g, " ")}</span>
        <span className="indicator-confidence">
          {(indicator.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>
      <p className="indicator-description">{indicator.description}</p>
      {indicator.evidence.length > 0 && (
        <div className="indicator-evidence">
          <strong>Evidence:</strong>
          <ul>
            {indicator.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function FraudAnalysis() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<FraudAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    if (query.trim().length < 3) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await analyzeFraud(query);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fraud-analysis">
      <div className="fraud-input-section">
        <h3>Fraud Pattern Analysis</h3>
        <p className="fraud-description">
          Analyze Indiana legal filings for anomalous patterns such as burst filing,
          identity reuse, deed fraud, and suspicious entities.
        </p>
        <div className="fraud-input-row">
          <input
            type="text"
            placeholder="Enter a party name, case number, or address..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
            disabled={loading}
          />
          <button onClick={handleAnalyze} disabled={loading || query.trim().length < 3}>
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="fraud-results">
          <div className={`fraud-risk-banner ${RISK_CLASSES[result.risk_level] ?? ""}`}>
            <div className="risk-level-display">
              <span className="risk-label">Risk Level</span>
              <span className="risk-value">{result.risk_level.toUpperCase()}</span>
            </div>
            <div className="risk-stats">
              <span>{result.total_filings_analyzed} filings analyzed</span>
              <span>{result.indicators.length} indicator(s) found</span>
              <span>Run: {result.run_id.slice(0, 8)}</span>
            </div>
            {result.requires_human_review && (
              <div className="human-review-badge">⚠ Requires Human Review</div>
            )}
          </div>

          <div className="fraud-summary">
            <h4>Summary</h4>
            <p>{result.summary}</p>
          </div>

          {result.indicators.length > 0 && (
            <div className="fraud-indicators">
              <h4>Detected Indicators</h4>
              {result.indicators.map((ind, i) => (
                <IndicatorCard key={i} indicator={ind} />
              ))}
            </div>
          )}

          {result.flagged_source_ids.length > 0 && (
            <div className="fraud-flagged-sources">
              <h4>Flagged Sources</h4>
              <div className="flagged-ids">
                {result.flagged_source_ids.map((id) => (
                  <span key={id} className="flagged-id-tag">{id}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
