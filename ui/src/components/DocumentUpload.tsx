import { useState } from "react";
import { ingestDocument } from "../api/client";

export function DocumentUpload() {
  const [sourceType, setSourceType] = useState("s3_upload");
  const [sourceId, setSourceId] = useState("");
  const [downloadUrl, setDownloadUrl] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceId || !downloadUrl) return;

    setStatus("submitting");
    try {
      const res = await ingestDocument({
        source_type: sourceType,
        source_id: sourceId,
        download_url: downloadUrl,
      });
      setStatus("success");
      setMessage(`Queued for processing (ID: ${res.message_id})`);
      setSourceId("");
      setDownloadUrl("");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  };

  return (
    <div className="document-upload">
      <h3>Ingest Document</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="source-type">Source Type</label>
          <select id="source-type" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="s3_upload">S3 Upload</option>
            <option value="indiana_courts">Indiana Courts API</option>
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="source-id">Source ID / Case Number</label>
          <input
            id="source-id"
            type="text"
            placeholder="e.g. 49D01-2024-CT-001234"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="download-url">Document URL</label>
          <input
            id="download-url"
            type="url"
            placeholder="https://..."
            value={downloadUrl}
            onChange={(e) => setDownloadUrl(e.target.value)}
          />
        </div>
        <button type="submit" disabled={status === "submitting" || !sourceId || !downloadUrl}>
          {status === "submitting" ? "Queuing…" : "Queue for Ingestion"}
        </button>
      </form>

      {status === "success" && <div className="success-message">{message}</div>}
      {status === "error" && <div className="error">{message}</div>}
    </div>
  );
}
