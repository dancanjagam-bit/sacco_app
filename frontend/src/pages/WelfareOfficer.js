import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
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
  awaiting_provider: "Awaiting provider",
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

export default function WelfareOfficer() {
  const [dashboard, setDashboard] = useState(null);
  const [requests, setRequests] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [actionMode, setActionMode] = useState("");
  const [actionReason, setActionReason] = useState("");
  const [actionError, setActionError] = useState("");
  const [documentError, setDocumentError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const [dashRes, reqRes] = await Promise.all([
        api.get("welfare/officer-dashboard/"),
        api.get("welfare/requests/?scope=committee"),
      ]);
      setDashboard(dashRes.data);
      setRequests(Array.isArray(reqRes.data) ? reqRes.data : []);
      setState("ready");
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "Welfare officer role is not assigned to your account."
          : "Could not load welfare dashboard. Try again."
      );
      setState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = statusFilter ? requests.filter((r) => r.status === statusFilter) : requests;
  const selected = requests.find((r) => r.id === selectedId);

  const handleAction = async () => {
    if (!selected || !actionMode) return;
    setActionError("");
    if (!actionReason.trim()) {
      setActionError("A reason is required.");
      return;
    }
    setSubmitting(true);
    try {
      if (actionMode === "info") {
        await api.post(`welfare/requests/${selected.id}/info/`, { notes: actionReason });
      } else {
        await api.post(`welfare/requests/${selected.id}/decision/`, {
          action: actionMode,
          reason: actionReason,
        });
      }
      setActionMode("");
      setActionReason("");
      setSelectedId(null);
      await load();
    } catch (err) {
      setActionError(err.response?.data?.detail || "Action failed. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const downloadDoc = async (docUrl, docName) => {
    setDocumentError("");
    try {
      const res = await api.get(docUrl.replace(/^\/api\//, ""), { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = docName;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setDocumentError("The supporting document could not be downloaded.");
    }
  };

  return (
    <Layout>
      <div className="welfare-page">
        <PageHeading
          eyebrow="Welfare officer"
          title="Welfare review"
          description="Review assigned support requests, request additional information, approve or reject with reasons, and track payout status."
          actions={<StatusBadge status="active" label="Welfare officer workspace" />}
        />

        {error && (
          <FeedbackMessage tone="danger" title="Dashboard unavailable"
            action={<Button variant="secondary" onClick={load}>Retry</Button>}>
            {error}
          </FeedbackMessage>
        )}
        {state === "loading" && <LoadingState label="Loading welfare review queue…" />}

        {state === "ready" && dashboard && (
          <>
            {/* ── Metrics ── */}
            <section className="welfare-metrics" aria-label="Welfare officer summary">
              <MetricCard label="Awaiting review" value={dashboard.case_counts?.submitted ?? 0} icon="file" helper="Submitted cases" />
              <MetricCard label="Needs information" value={dashboard.case_counts?.needs_information ?? 0} icon="alert" helper="Awaiting member response" />
              <MetricCard label="Pooled fund balance" value={formatKes(dashboard.pooled_fund_balance)} icon="wallet" helper="Welfare fund account" />
              <MetricCard label="Pending payouts" value={dashboard.pending_payouts ?? 0} icon="receipt" helper="Awaiting provider confirmation" />
            </section>

            {dashboard.case_counts?.submitted === 0 && dashboard.case_counts?.needs_information === 0 && (
              <FeedbackMessage tone="success">
                No cases are currently waiting for review.
              </FeedbackMessage>
            )}

            {/* ── Filter bar ── */}
            <div className="welfare-filter-bar">
              <button
                className={`welfare-tab${statusFilter === "" ? " is-active" : ""}`}
                onClick={() => setStatusFilter("")}
              >
                All ({requests.length})
              </button>
              {Object.entries(STATUS_LABELS).map(([key, label]) => {
                const count = requests.filter((r) => r.status === key).length;
                if (count === 0) return null;
                return (
                  <button
                    key={key}
                    className={`welfare-tab${statusFilter === key ? " is-active" : ""}`}
                    onClick={() => setStatusFilter(key)}
                  >
                    {label} ({count})
                  </button>
                );
              })}
            </div>

            {/* ── Two-column: list + detail ── */}
            <div className="welfare-officer-layout">
              {/* Case list */}
              <div className="welfare-officer-list">
                {filtered.length === 0 ? (
                  <div className="ui-empty">
                    <Icon name="heart" size={28} />
                    <p>No cases match this filter.</p>
                  </div>
                ) : (
                  filtered.map((req) => (
                    <button
                      key={req.id}
                      className={`welfare-case-card${selectedId === req.id ? " is-selected" : ""}`}
                      onClick={() => { setSelectedId(req.id); setActionMode(""); setActionReason(""); setActionError(""); setDocumentError(""); }}
                    >
                      <div className="welfare-case-card-head">
                        <span className="welfare-case-category">{req.category}</span>
                        <StatusBadge status={STATUS_TONES[req.status]} label={STATUS_LABELS[req.status] || req.status} />
                      </div>
                      <p className="welfare-case-member">{req.member_name} · {req.member_number}</p>
                      <dl className="welfare-case-facts">
                        <div><dt>Amount</dt><dd>{formatKes(req.requested_amount)}</dd></div>
                        <div><dt>Submitted</dt><dd>{new Date(req.created_at).toLocaleDateString()}</dd></div>
                        {req.payout_status && <div><dt>Payout</dt><dd>{PAYOUT_LABELS[req.payout_status] || req.payout_status}</dd></div>}
                      </dl>
                    </button>
                  ))
                )}
              </div>

              {/* Detail panel */}
              <div className="welfare-officer-detail">
                {!selected ? (
                  <div className="ui-empty welfare-detail-empty">
                    <Icon name="file" size={28} />
                    <p>Select a case to review details.</p>
                  </div>
                ) : (
                  <div className="welfare-detail-body">
                    <div className="welfare-detail-header">
                      <div>
                        <h2>{selected.category}</h2>
                        <p className="welfare-detail-member">{selected.member_name} · {selected.member_number}</p>
                      </div>
                      <StatusBadge status={STATUS_TONES[selected.status]} label={STATUS_LABELS[selected.status] || selected.status} />
                    </div>

                    <dl className="welfare-request-facts">
                      <div><dt>Requested amount</dt><dd>{formatKes(selected.requested_amount)}</dd></div>
                      {selected.approved_amount && <div><dt>Approved amount</dt><dd>{formatKes(selected.approved_amount)}</dd></div>}
                      <div><dt>Submitted</dt><dd>{new Date(selected.created_at).toLocaleDateString()}</dd></div>
                      {selected.policy_version && <div><dt>Policy</dt><dd>{selected.policy_version}</dd></div>}
                      {selected.payout_status && (
                        <div><dt>Payout status</dt><dd>{PAYOUT_LABELS[selected.payout_status] || selected.payout_status}</dd></div>
                      )}
                      {selected.payout_reference && (
                        <div><dt>Payout reference</dt><dd>{selected.payout_reference}</dd></div>
                      )}
                    </dl>

                    <div className="welfare-detail-section">
                      <h3>Description</h3>
                      <p>{selected.description}</p>
                    </div>

                    {selected.review_notes && (
                      <div className="welfare-detail-section">
                        <h3>Previous info request</h3>
                        <p>{selected.review_notes}</p>
                        {selected.reviewed_by && <p className="welfare-review-by">— {selected.reviewed_by}</p>}
                      </div>
                    )}

                    {selected.decision_reason && (
                      <div className="welfare-detail-section">
                        <h3>Decision reason</h3>
                        <p>{selected.decision_reason}</p>
                      </div>
                    )}

                    {/* Documents */}
                    {selected.documents?.length > 0 && (
                      <div className="welfare-detail-section">
                        <h3>Supporting documents</h3>
                        <ul className="welfare-documents">
                          {selected.documents.map((doc) => (
                            <li key={doc.id}>
                              <Button variant="secondary" size="sm" onClick={() => downloadDoc(doc.url, doc.name)}>
                                <Icon name="download" size={14} /> {doc.name}
                              </Button>
                            </li>
                          ))}
                        </ul>
                        <p className="welfare-audit-note">
                          <Icon name="shield" size={12} /> Document access is logged for audit.
                        </p>
                        {documentError && <FeedbackMessage tone="danger">{documentError}</FeedbackMessage>}
                      </div>
                    )}

                    {/* Actions for submitted or needs_information cases */}
                    {(selected.status === "submitted" || selected.status === "needs_information") && (
                      <div className="welfare-actions">
                        <h3>Review action</h3>
                        {actionError && <FeedbackMessage tone="danger">{actionError}</FeedbackMessage>}
                        <div className="welfare-action-buttons">
                          <Button
                            variant={actionMode === "approve" ? "primary" : "secondary"}
                            size="sm"
                            onClick={() => { setActionMode("approve"); setActionError(""); }}
                          >
                            <Icon name="check" size={14} /> Approve
                          </Button>
                          <Button
                            variant={actionMode === "reject" ? "danger" : "secondary"}
                            size="sm"
                            onClick={() => { setActionMode("reject"); setActionError(""); }}
                          >
                            <Icon name="close" size={14} /> Reject
                          </Button>
                          <Button
                            variant={actionMode === "info" ? "primary" : "secondary"}
                            size="sm"
                            onClick={() => { setActionMode("info"); setActionError(""); }}
                          >
                            <Icon name="alert" size={14} /> Request info
                          </Button>
                        </div>

                        {actionMode && (
                          <div className="welfare-action-form">
                            <div className="ui-form-field">
                              <label className="ui-label" htmlFor="welfare-officer-reason">
                                {actionMode === "info" ? "Information requested from member" : "Reason"}
                              </label>
                              <textarea
                                id="welfare-officer-reason"
                                className="ui-input"
                                value={actionReason}
                                onChange={(e) => setActionReason(e.target.value)}
                                rows={3}
                                placeholder={actionMode === "info" ? "Describe what additional information is needed" : "Provide a clear reason for this decision"}
                              />
                            </div>
                            <Button variant="primary" loading={submitting} onClick={handleAction}>
                              <Icon name="check" size={16} />
                              {actionMode === "approve" ? "Approve request" : actionMode === "reject" ? "Reject request" : "Send info request"}
                            </Button>
                          </div>
                        )}
                      </div>
                    )}

                    {selected.status === "approved" && (
                      <div className="welfare-payout-status">
                        <h3>Payout status</h3>
                        <StatusBadge
                          status={selected.payout_status === "confirmed" ? "active" : "warning"}
                          label={PAYOUT_LABELS[selected.payout_status] || selected.payout_status || "Awaiting payout"}
                        />
                        {selected.payout_reference && (
                          <p className="welfare-payout-ref">Reference: {selected.payout_reference}</p>
                        )}
                        <p className="welfare-audit-note">
                          <Icon name="shield" size={12} /> A confirmed payout requires a verified external provider and posted journal entry.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
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
