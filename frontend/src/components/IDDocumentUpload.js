import React, { useState, useRef } from "react";

const MAX_SIZE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/gif", "application/pdf"];

function IDDocumentUpload({ onChange, disabled = false }) {
  const [preview, setPreview] = useState(null);
  const [isPdf, setIsPdf] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const errorId = "id-doc-error";

  function handleChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > MAX_SIZE_BYTES) {
      setError("File exceeds the 5 MB size limit.");
      setPreview(null); setIsPdf(false);
      if (onChange) onChange(null);
      return;
    }
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError(`Unsupported file type '${file.type}'. Upload a JPEG, PNG, GIF, or PDF.`);
      setPreview(null); setIsPdf(false);
      if (onChange) onChange(null);
      return;
    }
    setError("");
    setIsPdf(file.type === "application/pdf");
    if (file.type !== "application/pdf") {
      setPreview(URL.createObjectURL(file));
    } else {
      setPreview(null);
    }
    if (onChange) onChange(file);
  }

  return (
    <div className="id-document-upload">
      <label htmlFor="id-document-input" className="form-label fw-semibold">
        National ID Document <span className="text-muted small">(JPEG, PNG, GIF, or PDF — max 5 MB)</span>
      </label>
      <input
        id="id-document-input"
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,application/pdf"
        onChange={handleChange}
        disabled={disabled}
        className="form-control"
        aria-describedby={error ? errorId : undefined}
      />
      {error && (
        <div id={errorId} className="text-danger small mt-1" role="alert">{error}</div>
      )}
      {isPdf && !error && (
        <div className="mt-2 d-flex align-items-center gap-2">
          <span style={{ fontSize: "2rem" }}>📄</span>
          <span className="text-muted small">PDF selected</span>
        </div>
      )}
      {preview && !isPdf && !error && (
        <div className="mt-2">
          <img src={preview} alt="ID document preview"
            style={{ maxWidth: "100%", maxHeight: "180px", borderRadius: "6px", border: "1px solid #dee2e6" }} />
        </div>
      )}
    </div>
  );
}

export default IDDocumentUpload;
