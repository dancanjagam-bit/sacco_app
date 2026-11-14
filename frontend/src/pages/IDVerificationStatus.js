import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import "../styles/member-kyc.css";

const statusCopy = {
  not_submitted: "No documents submitted",
  draft: "Draft — review your details before submitting",
  submitted: "Submitted — awaiting review",
  verification_pending: "Verification pending",
  verified: "Verified after staff review",
  needs_review: "Needs staff review",
  provider_unavailable: "Awaiting manual review",
  pending: "Pending staff review",
  flagged: "Needs staff review",
  failed: "Review required",
};

const fieldStyle = {
  display: "block", width: "100%", boxSizing: "border-box", minHeight: 46,
  padding: "10px 12px", fontSize: 16, color: "var(--text)",
  border: "1px solid var(--control-border)", borderRadius: "var(--radius-md)", margin: "6px 0 14px",
};

export default function IDVerificationStatus() {
  const [data, setData] = useState(null);
  const [front, setFront] = useState(null);
  const [back, setBack] = useState(null);
  const [consent, setConsent] = useState(false);
  const [fields, setFields] = useState({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await api.get("id-verification/status/");
      if (!response?.data || typeof response.data.status !== "string") {
        throw new Error("Invalid identity status response");
      }
      setData(response.data);
      setFields(response.data.reviewed_fields || {});
    } catch {
      setLoadError("Verification status could not be loaded");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function upload(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData();
    if (front) form.append("id_document_front", front);
    if (back) form.append("id_document_back", back);
    form.append("consent", String(consent || Boolean(data?.member_consent)));
    try {
      await api.post("id-verification/documents/", form, { headers: { "Content-Type": "multipart/form-data" } });
      await load();
      setMessage("Document saved. Review the suggested details before submitting for staff review.");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Upload failed. Check the file and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await api.post("id-verification/submit/", { reviewed_fields: fields });
      await load();
      setMessage(response.data.message || "Your documents were submitted for staff review.");
    } catch (error) {
      setMessage(error.response?.data?.detail || "Submission failed. Please check the details and retry.");
    } finally {
      setBusy(false);
    }
  }

  const canReview = ["draft", "needs_review", "provider_unavailable", "not_submitted"].includes(data?.status);

  return (
    <Layout>
      <div className="member-kyc-page">
        <PageHeading
          eyebrow="Account and security"
          title="Identity verification"
          description="Review your document status and any details that need correction."
        />

        {loading && !data ? <LoadingState label="Loading verification status…" /> : loadError && !data ? (
          <FeedbackMessage
            tone="danger"
            title="Verification status unavailable"
            action={<Button variant="secondary" onClick={load}>Retry</Button>}
          >
            {loadError}
          </FeedbackMessage>
        ) : data ? (
          <>
            {loadError && <FeedbackMessage tone="danger" title="Status refresh failed">{loadError}</FeedbackMessage>}
            <section className="member-kyc-status" aria-label="Verification status">
              <h2>{statusCopy[data.status] || "Status under review"}</h2>
              <p>Uploaded documents and OCR suggestions do not by themselves verify your identity. A staff review is recorded separately.</p>
              {data.failure_reason && <p role="status">{data.failure_reason}</p>}
              {data.verified_at && <p>Reviewed: {new Date(data.verified_at).toLocaleString("en-KE")}</p>}
              {data.status === "provider_unavailable" && <p>Your submission is waiting for manual review.</p>}
            </section>

            {message && <FeedbackMessage tone="info">{message}</FeedbackMessage>}

            {canReview && (
              <>
                <section className="member-kyc-panel">
                  <h2>Identity document</h2>
                  <p>Upload a clear front image and the back where applicable. JPEG, PNG, GIF, or PDF; up to 5 MB per file.</p>
                  <form onSubmit={upload}>
                    <label htmlFor="id-document-front">Front of ID</label>
                    <input id="id-document-front" required={!data?.ocr_result?.fields} style={fieldStyle} type="file" accept="image/jpeg,image/png,image/gif,application/pdf" onChange={(event) => setFront(event.target.files?.[0] || null)} />
                    <label htmlFor="id-document-back">Back of ID (optional)</label>
                    <input id="id-document-back" style={fieldStyle} type="file" accept="image/jpeg,image/png,image/gif,application/pdf" onChange={(event) => setBack(event.target.files?.[0] || null)} />
                    <label className="member-kyc-consent">
                      <input type="checkbox" checked={consent || Boolean(data?.member_consent)} onChange={(event) => setConsent(event.target.checked)} />
                      <span>I authorize secure storage of these documents for membership identity review. OCR is advisory; no selfie or liveness check is being performed.</span>
                    </label>
                    <Button type="submit" loading={busy}>Save document draft</Button>
                  </form>
                </section>

                <section className="member-kyc-panel">
                  <h2>Review your details</h2>
                  <p>Compare the suggested values with your ID and correct any reading errors. Staff will review the submitted information.</p>
                  {data.ocr_result?.fields && Object.keys(data.ocr_result.fields).length > 0 && (
                    <div className="member-kyc-suggestions">
                      <strong>OCR suggestions</strong>
                      {Object.entries(data.ocr_result.fields).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")}: {String(value || "Not detected")}</p>)}
                    </div>
                  )}
                  <form onSubmit={submit}>
                    {[["first_name", "First name"], ["last_name", "Last name"], ["national_id", "National ID number"], ["date_of_birth", "Date of birth (YYYY-MM-DD)"]].map(([key, label]) => (
                      <label key={key} htmlFor={`kyc-${key}`}>
                        {label}
                        <input id={`kyc-${key}`} required style={fieldStyle} value={fields[key] || ""} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} />
                      </label>
                    ))}
                    <Button type="submit" loading={busy} disabled={busy || !data?.ocr_result}>Confirm details and submit</Button>
                  </form>
                </section>
              </>
            )}
          </>
        ) : null}
      </div>
    </Layout>
  );
}
