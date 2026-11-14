import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import "../styles/transport-reconciliation.css";

const kes = (value) => `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function TransportExpenseReview() {
  const [items, setItems] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("transport/expenses/review-queue/");
      if (!Array.isArray(response.data)) throw new Error("Unexpected expense queue response.");
      setItems(response.data); setState("ready");
    } catch (requestError) {
      setItems([]); setError(requestError.response?.data?.detail || "Expense reports could not be loaded."); setState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function review(item, action, reason) {
    setSavingId(item.id); setActionError("");
    try {
      await api.post(`transport/expenses/${item.id}/review/`, { action, reason });
      await load();
    } catch (requestError) {
      setActionError(requestError.response?.data?.detail || "The expense review could not be saved.");
    } finally { setSavingId(null); }
  }

  return (
    <Layout>
      <main className="transport-reconciliation-page">
        <PageHeading eyebrow="Staff workspace" title="Transport expense review" description="Approval records whether a reported expense is valid. Only categories allowed by the active approved rule reduce a shift remittance." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}>Refresh</Button>} />
        {actionError && <FeedbackMessage tone="danger" title="Review not saved">{actionError}</FeedbackMessage>}
        {state === "loading" && <LoadingState label="Loading reported expenses…" />}
        {state === "error" && <FeedbackMessage tone="danger" title="Expense queue unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
        {state === "ready" && items.length === 0 && <div className="ui-empty"><strong>No reported expenses are waiting for review.</strong><span>New crew expense reports will appear here.</span></div>}
        {state === "ready" && items.map((item) => <ExpenseCard key={item.id} item={item} saving={savingId === item.id} onReview={review} />)}
      </main>
    </Layout>
  );
}

function ExpenseCard({ item, saving, onReview }) {
  const [reason, setReason] = useState("");
  return (
    <article className="ui-panel transport-reconciliation-card">
      <div className="ui-panel-body">
        <div className="transport-reconciliation-card-head"><div><p className="ui-eyebrow">Expense {item.id}</p><h2>{item.vehicle_registration} · {item.route_name}</h2></div><StatusBadge status={item.status} /></div>
        <dl className="transport-reconciliation-facts">
          <div><dt>Category</dt><dd>{item.category}</dd></div><div><dt>Reported amount</dt><dd>{kes(item.amount)}</dd></div>
          <div><dt>Reported by</dt><dd>{item.reported_by}</dd></div><div><dt>Reported</dt><dd>{new Date(item.created_at).toLocaleString("en-KE")}</dd></div>
        </dl>
        {item.notes && <p>{item.notes}</p>}
        <FormField label="Review reason" htmlFor={`expense-reason-${item.id}`} hint="Required and stored with the audit record.">
          <textarea id={`expense-reason-${item.id}`} className="ui-textarea" rows="3" maxLength="500" value={reason} onChange={(event) => setReason(event.target.value)} />
        </FormField>
        <div className="transport-reconciliation-actions">
          <Button loading={saving} disabled={!reason.trim()} onClick={() => onReview(item, "approve", reason.trim())}>Approve report</Button>
          <Button variant="secondary" loading={saving} disabled={!reason.trim()} onClick={() => onReview(item, "reject", reason.trim())}>Reject report</Button>
        </div>
      </div>
    </article>
  );
}
