import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";
import "../styles/transport-clerk-cash.css";

const money = (value) => value == null ? "Unavailable" : `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function TransportClerkCash() {
  const [items, setItems] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(null);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("transport/payment-queue/");
      if (!Array.isArray(response.data)) throw new Error("Unexpected cash queue response.");
      setItems(response.data.filter((item) => item.kind === "payment" && item.method === "cash"));
      setState("ready");
    } catch (requestError) {
      setItems([]); setState("error");
      setError(requestError.response?.data?.detail || "Assigned cash handovers could not be loaded.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function confirm(item, receivedAmount, reason) {
    setSaving(item.id); setError(""); setNotice("");
    try {
      const { data } = await api.post("transport/payment-queue/", {
        payment_id: item.id, confirm: true, received_amount: receivedAmount, reason,
      });
      setNotice(`Cash received: ${money(data.received_amount ?? receivedAmount)}.${data.status === "needs_review" ? " This handover needs treasury review." : ""}`);
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Cash confirmation could not be saved.");
    } finally { setSaving(null); }
  }

  return <Layout><main className="transport-clerk-cash-page">
    <PageHeading eyebrow="Assigned clerk duties" title="Cash handovers" description="Confirm only the physical amount counted for crew assignments assigned to you. Electronic payments require provider confirmation." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>} />
    {error && state !== "error" && <FeedbackMessage tone="danger" title="Cash handover action unavailable">{error}</FeedbackMessage>}
    {notice && <FeedbackMessage tone="success">{notice}</FeedbackMessage>}
    {state === "loading" && <LoadingState label="Loading assigned handovers…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Cash queue unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {state === "ready" && items.length === 0 && <div className="ui-empty transport-clerk-cash-empty"><strong>No assigned cash handovers are waiting.</strong>Only pending handovers for your effective clerk assignments will appear here.</div>}
    {state === "ready" && items.map((item) => <CashHandoverCard key={item.id} item={item} busy={saving !== null} saving={saving === item.id} onConfirm={(amount, reason) => confirm(item, amount, reason)} />)}
  </main></Layout>;
}

function CashHandoverCard({ item, busy, saving, onConfirm }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [showForm, setShowForm] = useState(false);
  const canConfirm = item.can_confirm_cash && item.status === "pending";
  const amountValid = Number.isFinite(Number(amount)) && Number(amount) > 0;
  return <article className="ui-panel transport-clerk-cash-card">
    <div className="transport-clerk-cash-head"><div><p className="ui-eyebrow">Cash handover · {item.id}</p><h2>{item.reference || "Reference not recorded"}</h2></div><StatusBadge status={item.status} /></div>
    <dl className="transport-clerk-cash-facts"><div><dt>Reported by crew</dt><dd>{money(item.reported_amount)}</dd></div><div><dt>Physically counted</dt><dd>{money(item.received_amount)}</dd></div><div><dt>Payment receipt</dt><dd>{item.receipt || "Cash handover"}</dd></div><div><dt>Submitted (Nairobi time)</dt><dd>{item.created_at ? new Date(item.created_at).toLocaleString("en-KE", { timeZone: "Africa/Nairobi" }) : "Unavailable"}</dd></div></dl>
    {item.review_reason && <p className="transport-clerk-cash-note">{item.review_reason}</p>}
    {canConfirm && !showForm && <Button onClick={() => setShowForm(true)}>Count and confirm receipt</Button>}
    {canConfirm && showForm && <div className="transport-clerk-cash-form">
      <p>Confirmation records the counted cash as received. Any difference from the crew’s reported amount remains for treasury review.</p>
      <FormField label="Amount physically received (KES)" htmlFor={`cash-count-${item.id}`}><input id={`cash-count-${item.id}`} className="ui-input" type="number" inputMode="decimal" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} /></FormField>
      <FormField label="Count note / discrepancy reason" htmlFor={`cash-reason-${item.id}`}><textarea id={`cash-reason-${item.id}`} className="ui-textarea" rows="3" maxLength="500" value={reason} onChange={(event) => setReason(event.target.value)} required /></FormField>
      <div className="transport-clerk-cash-actions"><Button variant="secondary" disabled={busy} onClick={() => setShowForm(false)}>Cancel</Button><Button loading={saving} disabled={busy || !amountValid || !reason.trim()} onClick={() => onConfirm(amount, reason.trim())}>Confirm amount received</Button></div>
    </div>}
    {!canConfirm && <p className="transport-clerk-cash-note">This handover cannot be confirmed from this screen. It may already be settled, unmatched, outside your current duty, or awaiting treasury review.</p>}
  </article>;
}
