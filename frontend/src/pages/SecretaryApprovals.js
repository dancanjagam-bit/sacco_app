import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";

const STAGE_LABELS = {
  secretary_review: "Secretary review",
  committee_approval: "Committee approval",
  activated: "Activated",
  rejected: "Rejected",
};

export default function SecretaryApprovals() {
  const [approvals, setApprovals] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [decisionFilter, setDecisionFilter] = useState("all");

  // Per-row action state
  const [acting, setActing] = useState(null); // approval id
  const [reasons, setReasons] = useState({}); // id -> string
  const [actionError, setActionError] = useState({});
  const [actionSuccess, setActionSuccess] = useState({});

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const params = new URLSearchParams();
      if (stageFilter && stageFilter !== "all") params.set("stage", stageFilter);
      if (decisionFilter && decisionFilter !== "all") params.set("decision", decisionFilter);
      const res = await api.get(`members/approvals/${params.toString() ? "?" + params.toString() : ""}`);
      if (!Array.isArray(res.data)) throw new Error("Unexpected response.");
      setApprovals(res.data);
      setState("ready");
    } catch (err) {
      setState("error");
      setError(err.response?.data?.detail || "Applications could not be loaded.");
    }
  }, [stageFilter, decisionFilter]);

  useEffect(() => { load(); }, [load]);

  async function decide(approval, decision) {
    setActing(approval.id);
    setActionError((prev) => ({ ...prev, [approval.id]: "" }));
    setActionSuccess((prev) => ({ ...prev, [approval.id]: "" }));
    try {
      await api.post("members/approvals/", {
        applicant_id: approval.applicant_id,
        stage: approval.stage,
        decision,
        notes: reasons[approval.id] || "",
      });
      setActionSuccess((prev) => ({ ...prev, [approval.id]: `${decision === "approved" ? "Approved" : "Rejected"} successfully.` }));
      await load();
    } catch (err) {
      setActionError((prev) => ({
        ...prev,
        [approval.id]: err.response?.data?.detail || "Action failed.",
      }));
    } finally {
      setActing(null);
    }
  }

  const pending = approvals.filter((a) => a.decision === "pending");
  const others = approvals.filter((a) => a.decision !== "pending");

  return (
    <Layout>
      <main style={{ display: "grid", gap: "var(--grid-gap)", maxWidth: "72rem", margin: "0 auto", width: "100%", minWidth: 0 }}>
        <PageHeading
          eyebrow="Secretary workspace"
          title="Membership applications"
          description="Review and decide membership approval steps. Each stage must be decided before the next is created."
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" size={15} /> Refresh</Button>}
        />

        <section className="ui-panel" aria-labelledby="approvals-note-title">
          <div className="ui-panel-body">
            <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
              <Icon name="shield" size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />
              Approval is distinct from identity verification status. A member may be approved here while their identity documents are still under review.
            </p>
          </div>
        </section>

        {/* Filter pills */}
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", marginRight: 4 }}>Stage:</span>
          {[["all", "All stages"], ["secretary_review", "Secretary review"], ["committee_approval", "Committee approval"], ["activated", "Activated"], ["rejected", "Rejected"]].map(([v, l]) => (
            <button key={v} className={`ui-filter-pill${stageFilter === v ? " is-active" : ""}`} onClick={() => setStageFilter(v)}>{l}</button>
          ))}
          <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", marginLeft: 12, marginRight: 4 }}>Decision:</span>
          {[["all", "All"], ["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"]].map(([v, l]) => (
            <button key={v} className={`ui-filter-pill${decisionFilter === v ? " is-active" : ""}`} onClick={() => setDecisionFilter(v)}>{l}</button>
          ))}
        </div>

        {state === "loading" && <LoadingState label="Loading membership applications…" />}
        {state === "error" && (
          <FeedbackMessage tone="danger" title="Could not load applications" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>
        )}
        {state === "ready" && approvals.length === 0 && (
          <div className="ui-empty"><strong>No applications found.</strong><span>Adjust the filters above to see more records.</span></div>
        )}

        {state === "ready" && pending.length > 0 && (
          <section className="ui-panel" aria-labelledby="pending-approvals-title">
            <div className="ui-panel-header">
              <div>
                <p className="ui-eyebrow">Action required</p>
                <h2 className="ui-panel-title" id="pending-approvals-title">Pending decisions ({pending.length})</h2>
              </div>
              <Icon name="users" />
            </div>
            <div className="ui-panel-body" style={{ display: "grid", gap: "var(--space-4)" }}>
              {pending.map((a) => (
                <ApprovalRow
                  key={a.id}
                  approval={a}
                  reason={reasons[a.id] || ""}
                  onReasonChange={(v) => setReasons((prev) => ({ ...prev, [a.id]: v }))}
                  onDecide={(decision) => decide(a, decision)}
                  acting={acting === a.id}
                  error={actionError[a.id]}
                  success={actionSuccess[a.id]}
                />
              ))}
            </div>
          </section>
        )}

        {state === "ready" && others.length > 0 && (
          <section className="ui-panel" aria-labelledby="decided-approvals-title">
            <div className="ui-panel-header">
              <div>
                <p className="ui-eyebrow">History</p>
                <h2 className="ui-panel-title" id="decided-approvals-title">Decided applications</h2>
              </div>
            </div>
            <div className="ui-panel-body" style={{ display: "grid", gap: "var(--space-3)" }}>
              {others.map((a) => (
                <ApprovalRow key={a.id} approval={a} readonly />
              ))}
            </div>
          </section>
        )}
      </main>
    </Layout>
  );
}

function ApprovalRow({ approval, reason, onReasonChange, onDecide, acting, error, success, readonly }) {
  return (
    <article style={{ borderBottom: "1px solid var(--border)", paddingBottom: "var(--space-4)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <div>
          <strong>{approval.applicant_name}</strong>
          <span style={{ marginLeft: 8, fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>@{approval.applicant_username}</span>
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
          <StatusBadge status={approval.stage} label={STAGE_LABELS[approval.stage] || approval.stage} />
          <StatusBadge status={approval.decision} label={approval.decision} />
        </div>
      </div>
      {approval.notes && (
        <p style={{ margin: "var(--space-2) 0 0", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
          Notes: {approval.notes}
        </p>
      )}
      <p style={{ margin: "var(--space-1) 0 0", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
        Submitted: {new Date(approval.created_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" })}
        {approval.decided_at && ` · Decided: ${new Date(approval.decided_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" })}`}
        {approval.reviewer_name && ` · By: ${approval.reviewer_name}`}
      </p>
      {!readonly && approval.decision === "pending" && (
        <div style={{ marginTop: "var(--space-3)", display: "grid", gap: "var(--space-2)", maxWidth: 480 }}>
          <FormField label="Reason / notes (required for rejection)" htmlFor={`reason-${approval.id}`}>
            <textarea
              id={`reason-${approval.id}`}
              className="ui-textarea"
              rows="2"
              maxLength="500"
              value={reason}
              onChange={(e) => onReasonChange(e.target.value)}
              placeholder="Optional for approval, required for rejection"
            />
          </FormField>
          {error && <FeedbackMessage tone="danger">{error}</FeedbackMessage>}
          {success && <FeedbackMessage tone="success">{success}</FeedbackMessage>}
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button size="sm" loading={acting} onClick={() => onDecide("approved")}>
              <Icon name="check" size={14} /> Approve
            </Button>
            <Button variant="secondary" size="sm" loading={acting} onClick={() => onDecide("rejected")} disabled={!reason.trim()}>
              <Icon name="close" size={14} /> Reject
            </Button>
          </div>
          {!reason.trim() && <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Enter a reason to enable rejection.</p>}
        </div>
      )}
    </article>
  );
}
