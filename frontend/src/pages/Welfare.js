import React, { useCallback, useEffect, useRef, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import MetricCard from "../components/ui/MetricCard";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import "../styles/welfare.css";

const STATUS_LABELS = {
  submitted: "Submitted",
  needs_information: "Needs information",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
};

const STATUS_TONES = {
  submitted: "neutral",
  needs_information: "warning",
  under_review: "neutral",
  approved: "active",
  rejected: "danger",
};

const PAYOUT_LABELS = {
  awaiting_provider: "Awaiting payout provider",
  pending: "Pending confirmation",
  uncertain: "Needs review",
  sending: "Sending",
  confirmed: "Confirmed",
  failed: "Failed",
  reversed: "Reversed",
};

function formatKes(value) {
  if (value == null) return "KES 0.00";
  const num = Number(value);
  if (isNaN(num)) return "KES 0.00";
  return `KES ${num.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function Welfare() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [requests, setRequests] = useState([]);
  const [contributions, setContributions] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("cases");

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [requestedAmount, setRequestedAmount] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [resubmitTarget, setResubmitTarget] = useState(null);
  const [resubmitting, setResubmitting] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const [dashRes, reqRes, contribRes] = await Promise.all([
        api.get("welfare/member-dashboard/"),
        api.get("welfare/requests/"),
        api.get("welfare/contributions/"),
      ]);
      setDashboard(dashRes.data);
      setRequests(Array.isArray(reqRes.data) ? reqRes.data : []);
      setContributions(Array.isArray(contribRes.data) ? contribRes.data : []);
      setState("ready");
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "Welfare access is not available for your account."
          : "Could not load welfare information. Try again."
      );
      setState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submitRequest = async (e) => {
    e.preventDefault();
    setFormError("");
    if (!category.trim() || !description.trim() || !requestedAmount) {
      setFormError("Category, description, and requested amount are required.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("welfare/requests/", {
        category: category.trim(),
        description: description.trim(),
        requested_amount: requestedAmount,
      });
      setCategory("");
      setDescription("");
      setRequestedAmount("");
      setShowForm(false);
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Could not submit request. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpload = async (requestId, file) => {
    setUploadError("");
    if (!file) return;
    const formData = new FormData();
    formData.append("document", file);
    try {
      await api.post(`welfare/requests/${requestId}/documents/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await load();
    } catch (err) {
      setUploadError(err.response?.data?.detail || "Could not upload document.");
    }
  };

  const handleResubmit = async (requestId) => {
    setResubmitting(true);
    setUploadError("");
    try {
      await api.post(`welfare/requests/${requestId}/resubmit/`);
      setResubmitTarget(null);
      await load();
    } catch (err) {
      setUploadError(err.response?.data?.detail || "Could not resubmit request.");
    } finally {
      setResubmitting(false);
    }
  };

  const firstName = user?.first_name || user?.username || "Member";

  return (
    <Layout>
      <div className="welfare-page">
        <PageHeading
          eyebrow="Member services"
          title={`Welfare${firstName ? ` — ${firstName}` : ""}`}
          description="View your welfare contributions, submit support requests, and track case decisions."
          actions={
            <Button variant="primary" onClick={() => setShowForm(!showForm)}>
              <Icon name="plus" size={16} /> {showForm ? "Cancel" : "New request"}
            </Button>
          }
        />

        {error && (
          <FeedbackMessage tone="danger" title="Welfare unavailable"
            action={<Button variant="secondary" onClick={load}>Retry</Button>}>
            {error}
          </FeedbackMessage>
        )}
        {state === "loading" && <LoadingState label="Loading welfare information…" />}

        {state === "ready" && dashboard && (
          <>
            {/* ── Summary metrics ── */}
            <section className="welfare-metrics" aria-label="Welfare summary">
              <MetricCard label="Total contributions" value={formatKes(dashboard.total_contributions)} icon="wallet" helper="Your attributed welfare contributions" />
              <MetricCard label="Submitted cases" value={dashboard.case_counts?.submitted ?? 0} icon="file" helper="Awaiting officer review" />
              <MetricCard label="Needs information" value={dashboard.case_counts?.needs_information ?? 0} icon="alert" helper="Officer requested details" />
              <MetricCard label="Approved" value={dashboard.case_counts?.approved ?? 0} icon="check" helper="Approved welfare benefits" />
            </section>

            {/* ── Policy info ── */}
            {dashboard.categories?.length > 0 && (
              <section className="welfare-policy-info" aria-label="Welfare policy">
                <div className="ui-panel-header">
                  <div>
                    <h2 className="ui-panel-title">Configured benefit categories</h2>
                    <p className="ui-panel-subtitle">Policy {dashboard.active_policy_version}</p>
                  </div>
                </div>
                <div className="welfare-category-grid">
                  {dashboard.categories.map((cat) => (
                    <div key={cat.category} className="welfare-category-card">
                      <p className="welfare-category-name">{cat.category}</p>
                      <dl className="welfare-category-facts">
                        <div><dt>Max benefit</dt><dd>{formatKes(cat.maximum_benefit)}</dd></div>
                        <div><dt>Min contributions</dt><dd>{formatKes(cat.minimum_contributions)}</dd></div>
                      </dl>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* ── New request form ── */}
            {showForm && (
              <section className="welfare-form" aria-label="Submit welfare request">
                <div className="ui-panel-header">
                  <h2 className="ui-panel-title">Submit a support request</h2>
                </div>
                {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
                <form onSubmit={submitRequest}>
                  <div className="ui-form-field">
                    <label htmlFor="welfare-category" className="ui-label">Category</label>
                    <input
                      id="welfare-category"
                      type="text"
                      className="ui-input"
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                      placeholder="e.g. medical, funeral, education"
                      list="welfare-categories"
                    />
                    <datalist id="welfare-categories">
                      {dashboard.categories?.map((cat) => (
                        <option key={cat.category} value={cat.category} />
                      ))}
                    </datalist>
                  </div>
                  <div className="ui-form-field">
                    <label htmlFor="welfare-amount" className="ui-label">Requested amount (KES)</label>
                    <input
                      id="welfare-amount"
                      type="number"
                      className="ui-input"
                      value={requestedAmount}
                      onChange={(e) => setRequestedAmount(e.target.value)}
                      placeholder="0.00"
                      min="0.01"
                      step="0.01"
                    />
                  </div>
                  <div className="ui-form-field">
                    <label htmlFor="welfare-description" className="ui-label">Description</label>
                    <textarea
                      id="welfare-description"
                      className="ui-input"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={4}
                      placeholder="Describe your support request"
                    />
                  </div>
                  <Button type="submit" variant="primary" loading={submitting}>
                    <Icon name="check" size={16} /> Submit request
                  </Button>
                </form>
              </section>
            )}

            {/* ── Tabs ── */}
            <div className="welfare-tabs" role="tablist">
              <button
                role="tab"
                aria-selected={tab === "cases"}
                className={`welfare-tab${tab === "cases" ? " is-active" : ""}`}
                onClick={() => setTab("cases")}
              >
                My cases ({requests.length})
              </button>
              <button
                role="tab"
                aria-selected={tab === "contributions"}
                className={`welfare-tab${tab === "contributions" ? " is-active" : ""}`}
                onClick={() => setTab("contributions")}
              >
                Contributions ({contributions.length})
              </button>
            </div>

            {uploadError && <FeedbackMessage tone="danger">{uploadError}</FeedbackMessage>}

            {/* ── Cases tab ── */}
            {tab === "cases" && (
              <section className="welfare-list" aria-label="My welfare cases">
                {requests.length === 0 ? (
                  <div className="ui-empty">
                    <Icon name="heart" size={32} />
                    <p>No welfare requests yet. Click "New request" to submit one.</p>
                  </div>
                ) : (
                  requests.map((req) => (
                    <div key={req.id} className="welfare-request">
                      <div className="welfare-request-heading">
                        <h3>{req.category}</h3>
                        <StatusBadge status={STATUS_TONES[req.status]} label={STATUS_LABELS[req.status] || req.status} />
                      </div>
                      <dl className="welfare-request-facts">
                        <div><dt>Requested</dt><dd>{formatKes(req.requested_amount)}</dd></div>
                        {req.approved_amount && <div><dt>Approved</dt><dd>{formatKes(req.approved_amount)}</dd></div>}
                        {req.policy_version && <div><dt>Policy</dt><dd>{req.policy_version}</dd></div>}
                        <div><dt>Submitted</dt><dd>{new Date(req.created_at).toLocaleDateString()}</dd></div>
                        {req.payout_status && (
                          <div>
                            <dt>Payout</dt>
                            <dd>{PAYOUT_LABELS[req.payout_status] || req.payout_status}</dd>
                          </div>
                        )}
                      </dl>
                      <p className="welfare-request-description">{req.description}</p>
                      {req.decision_reason && (
                        <p className="welfare-request-decision">
                          <strong>Decision:</strong> {req.decision_reason}
                        </p>
                      )}
                      {req.review_notes && (
                        <div className="welfare-review-notes">
                          <p className="welfare-review-notes-title">
                            <Icon name="alert" size={14} /> Officer requested information:
                          </p>
                          <p>{req.review_notes}</p>
                          {req.reviewed_by && <p className="welfare-review-by">— {req.reviewed_by}</p>}
                        </div>
                      )}

                      {/* Documents */}
                      {req.documents?.length > 0 && (
                        <ul className="welfare-documents">
                          {req.documents.map((doc) => (
                            <li key={doc.id}>
                              <Button
                                as="a"
                                href={doc.url}
                                variant="secondary"
                                size="sm"
                                onClick={(e) => {
                                  e.preventDefault();
                                  setUploadError("");
                                  api.get(`welfare/documents/${doc.id}/`, { responseType: "blob" }).then((res) => {
                                    const url = URL.createObjectURL(res.data);
                                    const a = document.createElement("a");
                                    a.href = url;
                                    a.download = doc.name;
                                    a.click();
                                    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                                  }).catch(() => setUploadError("The supporting document could not be downloaded."));
                                }}
                              >
                                <Icon name="file" size={14} /> {doc.name}
                              </Button>
                            </li>
                          ))}
                        </ul>
                      )}

                      {/* Upload action for submitted or needs_information requests */}
                      {(req.status === "submitted" || req.status === "needs_information") && (
                        <div className="welfare-request-actions">
                          {req.status === "needs_information" && (
                            <Button
                              variant="primary"
                              size="sm"
                              loading={resubmitting && resubmitTarget === req.id}
                              onClick={() => handleResubmit(req.id)}
                            >
                              <Icon name="refresh" size={14} /> Resubmit
                            </Button>
                          )}
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setUploadTarget(uploadTarget === req.id ? null : req.id)}
                          >
                            <Icon name="plus" size={14} /> Upload document
                          </Button>
                        </div>
                      )}

                      {uploadTarget === req.id && (
                        <div className="welfare-upload-inline">
                          <input
                            ref={fileInputRef}
                            type="file"
                            aria-label="Supporting document"
                            accept="image/png,image/jpeg,image/gif,application/pdf"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) handleUpload(req.id, file);
                              setUploadTarget(null);
                            }}
                          />
                          <p className="welfare-upload-hint">PNG, JPEG, GIF, or PDF. Up to 5 documents per request.</p>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </section>
            )}

            {/* ── Contributions tab ── */}
            {tab === "contributions" && (
              <section className="welfare-list" aria-label="My welfare contributions">
                {contributions.length === 0 ? (
                  <div className="ui-empty">
                    <Icon name="wallet" size={32} />
                    <p>No attributed welfare contributions yet. Contributions are recorded when your welfare deposits are confirmed.</p>
                  </div>
                ) : (
                  <div className="ui-table-wrap">
                    <table className="ui-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Amount</th>
                          <th>Reference</th>
                        </tr>
                      </thead>
                      <tbody>
                        {contributions.map((contrib) => (
                          <tr key={contrib.id}>
                            <td>{contrib.posted_at ? new Date(contrib.posted_at).toLocaleDateString() : "—"}</td>
                            <td>{formatKes(contrib.amount)}</td>
                            <td>{contrib.source_reference || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
          </>
        )}

        {/* Refresh */}
        {state !== "loading" && (
          <div className="welfare-refresh">
            <Button variant="secondary" size="sm" onClick={load}>
              <Icon name="refresh" size={15} /> Refresh
            </Button>
          </div>
        )}
      </div>
    </Layout>
  );
}
