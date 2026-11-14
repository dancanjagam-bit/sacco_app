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
import "../styles/transport-reconciliation.css";

const kes = (value) => value === null || value === undefined
  ? "Not separately recorded"
  : `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function TransportReconciliation() {
  const [queue, setQueue] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [actioning, setActioning] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const response = await api.get("transport/payment-queue/");
      if (!Array.isArray(response.data)) throw new Error("Unexpected payment queue response.");
      setQueue(response.data);
      setState("ready");
    } catch (requestError) {
      setQueue([]);
      setError(requestError.response?.data?.detail || "The reconciliation queue could not be loaded.");
      setState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function reconcile(item, action, reason, { receivedAmount, remittanceId }) {
    const actionKey = paymentKey(item);
    setActioning(actionKey);
    setActionError("");
    setNotice("");
    try {
      if (action === "allocate") {
        await api.post(`transport/accounting/payments/${item.id}/allocate/`, { reason });
      } else {
        const actions = {
          confirm: { confirm: true, received_amount: receivedAmount },
          match: { remittance_id: remittanceId },
          review: { review: true },
          resolve: { resolve: true },
          post_receipt: { post_receipt: true },
          release_attempt: { action: "release_attempt" },
        };
        const payload = item.kind === "duplicate_callback"
          ? { event_id: item.event_id, reason }
          : { payment_id: item.id, ...actions[action], reason };
        await api.post("transport/payment-queue/", payload);
      }
      setNotice(action === "allocate" ? "Payment allocation posted." : "Reconciliation action saved.");
      await load();
    } catch (requestError) {
      setActionError(requestError.response?.data?.detail || "The review could not be saved. Try again.");
    } finally {
      setActioning("");
    }
  }

  return (
    <Layout>
      <main className="transport-reconciliation-page">
        <PageHeading eyebrow="Staff workspace" title="Transport reconciliation" description="Match payments to remittances and review receipt discrepancies." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>} />
        {actionError && <FeedbackMessage tone="danger" title="Review not saved">{actionError}</FeedbackMessage>}
        {notice && <FeedbackMessage tone="success">{notice}</FeedbackMessage>}
        {state === "loading" && <LoadingState label="Loading reconciliation items…" />}
        {state === "error" && <FeedbackMessage tone="danger" title="Queue unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
        {state === "ready" && queue.length === 0 && <div className="ui-empty"><strong>No items need reconciliation.</strong><span>Unmatched receipts and pending, partial, late, or uncertain payments will appear here.</span></div>}
        {state === "ready" && queue.length > 0 && <div className="transport-reconciliation-list">{queue.map((item) => (
          <PaymentCard key={paymentKey(item)} item={item} actioning={actioning === paymentKey(item)} busy={Boolean(actioning)}
            onAction={(action, reason, details) => reconcile(item, action, reason, details)} />
        ))}</div>}
      </main>
    </Layout>
  );
}

const paymentKey = (item) => item.kind === "duplicate_callback" ? `event-${item.event_id}` : `payment-${item.id}`;

function PaymentCard({ item, actioning, busy, onAction }) {
  const [reason, setReason] = useState("");
  const [receivedAmount, setReceivedAmount] = useState("");
  const [remittanceId, setRemittanceId] = useState("");
  const [actionsOpen, setActionsOpen] = useState(false);
  const isEvent = item.kind === "duplicate_callback";
  const validReceivedAmount = Number.isFinite(Number(receivedAmount)) && Number(receivedAmount) > 0;
  const hasActions = isEvent || item.can_confirm_cash || item.can_match || item.can_review || item.can_resolve
    || item.can_post_receipt || item.can_allocate || item.can_release_attempt;
  const submit = (action) => onAction(action, reason.trim(), { receivedAmount, remittanceId: remittanceId.trim() });
  const invalidReason = busy || !reason.trim();
  return (
    <article className="ui-panel transport-reconciliation-card">
      <div className="ui-panel-body">
        <div className="transport-reconciliation-card-head">
          <div><p className="ui-eyebrow">{isEvent ? "Provider callback exception" : `Payment ${item.id}`}</p><h2>{item.method}</h2></div>
          <StatusBadge status={item.status} />
        </div>
        <ul className="transport-reconciliation-reasons" aria-label="Reasons for review">
          {(item.queue_reasons || []).map((reasonItem) => <li key={reasonItem}>{reasonItem.replaceAll("_", " ")}</li>)}
        </ul>
        <dl className="transport-reconciliation-facts">
          <div><dt>Reported</dt><dd>{kes(item.reported_amount)}</dd></div>
          <div><dt>Received</dt><dd>{kes(item.received_amount)}</dd></div>
          <div><dt>Provider receipt</dt><dd>{item.receipt || "Not recorded"}</dd></div>
          <div><dt>Reference</dt><dd>{item.reference || "Not matched"}</dd></div>
          {!isEvent && <div><dt>Remittance</dt><dd>{item.remittance || "Unmatched"}{item.remittance_status ? ` · ${item.remittance_status}` : ""}</dd></div>}
          {item.accounting_status && <div><dt>Accounting</dt><dd><StatusBadge status={item.accounting_status} /></dd></div>}
          {item.receipt_journal_id && <div><dt>Receipt journal</dt><dd>#{item.receipt_journal_id}{item.receipt_reversal_id && ` · reversal #${item.receipt_reversal_id}`}</dd></div>}
          {item.allocation_journal_id && <div><dt>Allocation journal</dt><dd>#{item.allocation_journal_id}{item.allocation_reversal_id && ` · reversal #${item.allocation_reversal_id}`}</dd></div>}
        </dl>
        {item.review_reason && <p className="transport-reconciliation-note">{item.review_reason}</p>}
        {isEvent && <p className="transport-reconciliation-note">This callback was not posted as a second receipt. Verify the reference with the provider and existing payment record.</p>}
        {hasActions && <div className="transport-reconciliation-actions">
          <Button variant="secondary" onClick={() => setActionsOpen((open) => !open)} aria-expanded={actionsOpen}>
            {isEvent ? "Review exception" : "Add review"}
          </Button>
        </div>}
        {actionsOpen && <div className="transport-reconciliation-review">
          {item.can_match && <FormField label="Remittance reference" htmlFor={`payment-remittance-${item.id}`} hint="Enter the reference printed on the remittance or its ID.">
            <input id={`payment-remittance-${item.id}`} className="ui-input" value={remittanceId} onChange={(event) => setRemittanceId(event.target.value)} />
          </FormField>}
          {item.can_confirm_cash && <FormField label="Counted amount received (KES)" htmlFor={`payment-received-${item.id}`}>
            <input id={`payment-received-${item.id}`} className="ui-input" type="number" inputMode="decimal" min="0.01" step="0.01" value={receivedAmount} onChange={(event) => setReceivedAmount(event.target.value)} />
          </FormField>}
          <FormField label="Review reason" htmlFor={`${paymentKey(item)}-reason`} hint={item.can_release_attempt ? "To release a payment attempt, document the provider or clerk evidence." : undefined}>
            <textarea id={`${paymentKey(item)}-reason`} className="ui-textarea" rows="3" maxLength="500" value={reason} onChange={(event) => setReason(event.target.value)} required />
          </FormField>
          <div className="transport-reconciliation-actions">
            {item.can_confirm_cash && <Button loading={actioning} disabled={invalidReason || !validReceivedAmount} onClick={() => submit("confirm")}>Confirm cash received</Button>}
            {item.can_match && <Button loading={actioning} disabled={invalidReason || !remittanceId.trim()} onClick={() => submit("match")}>Match payment</Button>}
            {item.can_review && <Button variant="secondary" disabled={invalidReason} onClick={() => submit("review")}>Mark disputed</Button>}
            {(isEvent || item.can_resolve) && <Button variant="secondary" disabled={invalidReason} onClick={() => submit("resolve")}>{isEvent ? "Resolve exception" : "Resolve discrepancy"}</Button>}
            {item.can_release_attempt && <Button variant="secondary" disabled={invalidReason} onClick={() => submit("release_attempt")}>Release payment attempt</Button>}
            {item.can_post_receipt && <Button variant="secondary" disabled={invalidReason} onClick={() => submit("post_receipt")}>Retry receipt posting</Button>}
            {item.can_allocate && <Button variant="secondary" disabled={invalidReason} onClick={() => submit("allocate")}>Post configured allocation</Button>}
          </div>
        </div>}
      </div>
    </article>
  );
}
