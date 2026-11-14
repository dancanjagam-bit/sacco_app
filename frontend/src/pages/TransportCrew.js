import React, { useCallback, useEffect, useRef, useState } from "react";
import Layout from "../components/Layout";
import ConfirmModal from "../components/ConfirmModal";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";
import "../styles/transport-crew.css";

function makeClientKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const waitingForSync = "Saved on this phone — waiting to sync";
const nairobiTime = { timeZone: "Africa/Nairobi" };
const storageKey = (userId) => `transport-offline-collections:${userId}`;

function readDrafts(userId) {
  try {
    const value = JSON.parse(window.localStorage.getItem(storageKey(userId)) || "[]");
    return Array.isArray(value) ? value.filter((draft) => draft?.client_key && draft?.assignment) : [];
  } catch {
    return [];
  }
}

export default function TransportCrew() {
  const { user } = useAuth();
  return user?.id ? <CrewWorkspace key={user.id} userId={user.id} /> : null;
}

function CrewWorkspace({ userId }) {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyState, setHistoryState] = useState("loading");
  const [historyError, setHistoryError] = useState("");
  const [shiftState, setShiftState] = useState("loading");
  const [shiftError, setShiftError] = useState("");
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [offlineDrafts, setOfflineDrafts] = useState(() => readDrafts(userId));
  const [syncingKey, setSyncingKey] = useState("");
  const collectionRequest = useRef(false);
  const [remitAmount, setRemitAmount] = useState("");
  const [paymentAmount, setPaymentAmount] = useState({});
  const [paymentAction, setPaymentAction] = useState("");
  const [expense, setExpense] = useState({ category: "", amount: "", notes: "" });
  const [expenseSaving, setExpenseSaving] = useState(false);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [issueMessage, setIssueMessage] = useState("");
  const [issueSaving, setIssueSaving] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [receiptLoading, setReceiptLoading] = useState("");
  const [selectedAssignment, setSelectedAssignment] = useState(null);
  const [refreshNumber, setRefreshNumber] = useState(0);
  const selection = useRef(null);

  const load = useCallback(async () => {
    if (selection.current !== selectedAssignment) return;
    setShiftState("loading");
    setShiftError("");
    setHistoryState("loading");
    setHistoryError("");
    try {
      const path = selectedAssignment ? `transport/crew/assignments/${selectedAssignment}/` : "transport/crew/today/";
      const response = await api.get(path);
      if (selection.current !== selectedAssignment) return;
      setData(response.data);
      setShiftState("ready");
    } catch {
      if (selection.current !== selectedAssignment) return;
      setShiftError("Shift unavailable. Please retry to check the assignment.");
      setShiftState("error");
    }
    try {
      const response = await api.get("transport/crew/history/");
      if (selection.current !== selectedAssignment) return;
      if (!Array.isArray(response.data)) throw new Error("Invalid assignment history response");
      setHistory(response.data);
      setHistoryState("ready");
    } catch (requestError) {
      if (selection.current !== selectedAssignment) return;
      setHistory([]);
      setHistoryError(requestError.response?.data?.detail || "Past assignments could not be loaded.");
      setHistoryState("error");
    }
  }, [selectedAssignment]);

  useEffect(() => { load(); }, [load, refreshNumber]);
  useEffect(() => {
    const refreshDrafts = (event) => {
      if (!event.key || event.key === storageKey(userId)) {
        setOfflineDrafts((current) => [...readDrafts(userId), ...current.filter((draft) => draft.temporary)]);
      }
    };
    window.addEventListener("storage", refreshDrafts);
    return () => window.removeEventListener("storage", refreshDrafts);
  }, [userId]);
  useEffect(() => {
    if (data?.assignment?.closure?.expected_remittance !== null && data?.assignment?.closure?.expected_remittance !== undefined) {
      setRemitAmount(String(data.assignment.closure.expected_remittance));
    }
  }, [data?.assignment?.closure?.expected_remittance]);

  function saveDrafts(next) {
    window.localStorage.setItem(storageKey(userId), JSON.stringify(next));
    setOfflineDrafts((current) => [...next, ...current.filter((draft) => draft.temporary)]);
  }

  const assignment = data?.assignment || null;
  const shiftClosed = assignment?.shift_status === "closed";
  const collectionAllowed = assignment && !shiftClosed && assignment.can_record_collection !== false;

  function showAssignment(id) {
    selection.current = id;
    setError("");
    setNotice("");
    setReceipt(null);
    setConfirmClose(false);
    setAmount("");
    setNotes("");
    setExpense({ category: "", amount: "", notes: "" });
    setRemitAmount("");
    setShiftState("loading");
    setSelectedAssignment(id);
  }

  function removeDraft(draft) {
    if (draft.temporary) {
      setOfflineDrafts((current) => current.filter((item) => item.client_key !== draft.client_key));
      return;
    }
    const remaining = readDrafts(userId).filter((item) => item.client_key !== draft.client_key);
    try {
      saveDrafts(remaining);
    } catch {
      // The server can safely replay the original key if it remains in storage.
      setOfflineDrafts((current) => current.filter((item) => item.client_key !== draft.client_key));
    }
  }

  async function postCollection(draft) {
    const { assignment: assignmentId, amount: draftAmount, notes: draftNotes, client_key: clientKey } = draft;
    const response = await api.post("transport/crew/today/", {
      assignment: assignmentId, amount: draftAmount, notes: draftNotes, client_key: clientKey, recorded_by: userId,
    });
    removeDraft(draft);
    setError("");
    setNotice(response.data?.duplicate
      ? "This collection was already saved. No second record was created."
      : `Collection recorded: KES ${response.data?.amount ?? draft.amount} in reported cash.`);
    setRefreshNumber((count) => count + 1);
  }

  async function submitCollection(event) {
    event.preventDefault();
    if (!collectionAllowed || collectionRequest.current) return;
    setError("");
    setNotice("");
    const draft = {
      assignment: assignment.id,
      vehicle: assignment.vehicle_registration,
      amount: String(amount),
      notes: String(notes || ""),
      client_key: makeClientKey(),
    };
    const online = window.navigator.onLine;
    let savedOnPhone = true;
    try {
      // Preserve the original request and key before sending it so a reload
      // or a lost response can replay the exact same collection.
      saveDrafts([...readDrafts(userId), draft]);
    } catch {
      if (!online) {
        setError("This phone could not save the collection draft. Check browser storage and retry.");
        return;
      }
      savedOnPhone = false;
    }
    setAmount("");
    setNotes("");
    if (!online) {
      setNotice(`${waitingForSync}. Retry when connected.`);
      return;
    }
    collectionRequest.current = true;
    setSubmitting(true);
    try {
      await postCollection(draft);
    } catch (requestError) {
      const status = requestError.response?.status;
      if (status === 400) {
        removeDraft(draft);
        setAmount(draft.amount);
        setNotes(draft.notes);
        setError(requestError.response.data?.detail || "Check the collection details and try again.");
      } else if (!savedOnPhone) {
        setOfflineDrafts((current) => [...current, { ...draft, temporary: true }]);
        setError("The collection could not be confirmed. Retry while this page is open. This phone could not save a copy.");
      } else if (!status || status >= 500) {
        setNotice(`${waitingForSync}. Retry when connected.`);
      } else {
        setError(requestError.response.data?.detail || "Could not record the collection. The saved draft is available to retry.");
      }
    } finally {
      collectionRequest.current = false;
      setSubmitting(false);
    }
  }

  async function retryDraft(draft) {
    if (collectionRequest.current) return;
    if (!window.navigator.onLine) {
      setError("Reconnect to sync the saved collection.");
      return;
    }
    collectionRequest.current = true;
    setSyncingKey(draft.client_key);
    setError("");
    setNotice("");
    try {
      await postCollection(draft);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Sync did not complete. The saved draft is still waiting on this phone.");
    } finally {
      collectionRequest.current = false;
      setSyncingKey("");
    }
  }

  async function createRemittance(event) {
    event.preventDefault();
    if (!assignment) return;
    setError("");
    setNotice("");
    const key = `transport-remittance-key:${userId}:${assignment.id}`;
    const clientKey = window.sessionStorage.getItem(key) || makeClientKey();
    window.sessionStorage.setItem(key, clientKey);
    try {
      const response = await api.post("transport/remittances/", {
        assignment: assignment.id, amount: remitAmount, client_key: clientKey,
      });
      window.sessionStorage.removeItem(key);
      setNotice(`Remittance ${response.data.payment_reference} saved. Reported KES ${response.data.amount}; received KES ${response.data.received_amount}.`);
      setRemitAmount("");
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Could not create the remittance request.");
    }
  }

  async function submitExpense(event) {
    event.preventDefault();
    if (!assignment) return;
    setError(""); setNotice(""); setExpenseSaving(true);
    const key = `transport-expense-key:${userId}:${assignment.id}`;
    const clientKey = window.sessionStorage.getItem(key) || makeClientKey();
    window.sessionStorage.setItem(key, clientKey);
    try {
      const response = await api.post("transport/expenses/", { assignment: assignment.id, ...expense, client_key: clientKey });
      window.sessionStorage.removeItem(key);
      setNotice(response.data?.duplicate ? "This expense was already recorded." : "Expense reported. It will not reduce remittance until reviewed and allowed by the active rule.");
      setExpense({ category: "", amount: "", notes: "" });
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Expense report was not saved. Retry with the same details.");
    } finally { setExpenseSaving(false); }
  }

  async function closeShift() {
    if (!assignment) return;
    setClosing(true); setError(""); setNotice("");
    try {
      const response = await api.post("transport/shifts/close/", { assignment: assignment.id });
      const expected = response.data.expected_remittance === null ? "not calculated" : `KES ${response.data.expected_remittance}`;
      setNotice(`Shift closed. Gross reported collections: KES ${response.data.reported_gross}; expected remittance: ${expected}. Payment settlement is still separate.`);
      setConfirmClose(false);
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The shift could not be closed.");
    } finally { setClosing(false); }
  }

  async function startStk(remittance, amount) {
    const actionKey = `stk:${remittance.id}`;
    if (paymentAction) return;
    setPaymentAction(actionKey);
    setError("");
    try {
      const key = `transport-payment-key:${userId}:${remittance.id}`;
      const clientKey = window.sessionStorage.getItem(key) || makeClientKey();
      window.sessionStorage.setItem(key, clientKey);
      const response = await api.post(`transport/remittances/${remittance.id}/stk/`, { client_key: clientKey, amount });
      // Keep the key on transport/network errors so a retry resolves the same
      // possibly accepted provider request. A successful response allows a
      // later, intentional partial payment to use a new idempotency key.
      window.sessionStorage.removeItem(key);
      setNotice(`M-Pesa request status: ${response.data.status}. Acceptance is not payment confirmation.`);
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The M-Pesa request needs retry or staff review.");
    } finally {
      setPaymentAction("");
    }
  }

  async function submitCashHandover(remittance, amount) {
    const actionKey = `cash:${remittance.id}`;
    if (paymentAction) return;
    setPaymentAction(actionKey);
    setError("");
    try {
      const key = `transport-cash-key:${userId}:${remittance.id}`;
      const clientKey = window.sessionStorage.getItem(key) || makeClientKey();
      window.sessionStorage.setItem(key, clientKey);
      const response = await api.post(`transport/remittances/${remittance.id}/cash/`, { client_key: clientKey, amount });
      // Clear only after the server acknowledges persistence. Network retries
      // retain the same key; a later partial handover gets its own key.
      window.sessionStorage.removeItem(key);
      setNotice(`Cash handover status: ${response.data.status}. A clerk must confirm receipt.`);
      await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Cash handover could not be submitted.");
    } finally {
      setPaymentAction("");
    }
  }

  async function reportAssignmentIssue(event) {
    event.preventDefault();
    setError(""); setNotice(""); setIssueSaving(true);
    try {
      await api.post("transport/issues/", { assignment_id: assignment?.id || null, message: issueMessage.trim() });
      setIssueMessage("");
      setNotice("Assignment issue sent to transport operations for review.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The assignment issue could not be submitted.");
    } finally { setIssueSaving(false); }
  }

  async function viewReceipt(remittance) {
    setReceiptLoading(remittance.id); setError("");
    try {
      const response = await api.get(`transport/remittances/${remittance.id}/receipt/`);
      setReceipt(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The receipt is not available to this account.");
    } finally { setReceiptLoading(""); }
  }

  const collections = Array.isArray(assignment?.collections) ? assignment.collections : [];
  const remittances = Array.isArray(assignment?.remittances) ? assignment.remittances : [];
  const expenses = Array.isArray(assignment?.expenses) ? assignment.expenses : [];
  const zeroDue = assignment?.closure?.calculation_status === "calculated"
    && Number(assignment.closure.expected_remittance) === 0;

  return (
    <Layout>
      <main className="transport-crew-page">
        <PageHeading
          eyebrow="Transport operations"
          title={selectedAssignment ? "Past shift" : "Today’s shift"}
          description="View assigned work and report collections. Reported cash is separate from confirmed receipts."
          actions={selectedAssignment ? <Button variant="secondary" onClick={() => showAssignment(null)}>Back to today’s shift</Button> : undefined}
        />
        {error && <FeedbackMessage tone="danger" title="Action needs attention">{error}</FeedbackMessage>}
        {notice && <FeedbackMessage tone="success">{notice}</FeedbackMessage>}

        {shiftState !== "loading" && shiftState !== "error" && <section className="transport-crew-card" aria-labelledby="assignment-issue-title">
          <h2 id="assignment-issue-title">Report an assignment problem</h2>
          <p>Use this if today’s vehicle, route, or crew assignment is missing or incorrect. An operations clerk must review it.</p>
          <form className="transport-crew-form" onSubmit={reportAssignmentIssue}>
            <label htmlFor="assignment-issue-message">What needs checking?</label>
            <textarea id="assignment-issue-message" rows="3" maxLength="500" required value={issueMessage} onChange={(event) => setIssueMessage(event.target.value)} />
            <Button type="submit" loading={issueSaving} disabled={issueMessage.trim().length < 10}>Send report</Button>
          </form>
        </section>}

        {shiftState === "loading" ? <LoadingState label="Checking your current assignment…" /> : shiftState === "error" ? (
          <FeedbackMessage tone="danger" title="Shift unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>
            {shiftError}
          </FeedbackMessage>
        ) : !assignment ? (
          <section className="transport-crew-card transport-crew-no-assignment">
            <h2>No valid assignment for today</h2>
            <p>{data?.message || "No active assignment was returned for your account today."}</p>
            <p>Contact your operations supervisor or SACCO staff to report a missing or incorrect assignment.</p>
          </section>
        ) : (
          <>
            <section className="transport-crew-card transport-crew-assignment" aria-label={selectedAssignment ? "Past assignment" : "Current assignment"}>
              <div className="transport-crew-assignment-title">
                <Icon name="bus" size={22} />
                <div><h2>{assignment.vehicle_registration} · {assignment.route_name}</h2><span>{assignment.stage_name ? `Stage: ${assignment.stage_name}` : "Route assignment"}</span></div>
                <StatusBadge status={assignment.shift_status || assignment.status} />
              </div>
              <dl className="transport-crew-facts">
                <div><dt>Driver</dt><dd>{assignment.driver_name || "Not assigned"}</dd></div>
                <div><dt>Conductor</dt><dd>{assignment.conductor_name || "No conductor assigned"}</dd></div>
                <div><dt>Assignment</dt><dd><StatusBadge status={assignment.status} /></dd></div>
                <div><dt>Starts (Nairobi time)</dt><dd>{assignment.starts_at ? new Date(assignment.starts_at).toLocaleString("en-KE", nairobiTime) : "Unavailable"}</dd></div>
                <div><dt>Ends (Nairobi time)</dt><dd>{assignment.ends_at ? new Date(assignment.ends_at).toLocaleString("en-KE", nairobiTime) : "Not specified"}</dd></div>
                <div><dt>Reported collections</dt><dd>KES {assignment.collection_total ?? "0.00"}</dd></div>
                <div><dt>Confirmed remittances</dt><dd>KES {assignment.confirmed_remittance_total ?? "0.00"}</dd></div>
                <div><dt>Pending remittance</dt><dd>KES {assignment.pending_remittance_total ?? "0.00"}</dd></div>
                {assignment.closure && <div><dt>Shift close</dt><dd>{assignment.closure.calculation_status.replaceAll("_", " ")}</dd></div>}
              </dl>
              <p className="transport-crew-note">{data?.message || "Shift closure and payment settlement are separate steps."}</p>
            </section>

            <section className="transport-crew-card" aria-labelledby="record-collection-title">
              <h2 id="record-collection-title">Record collection</h2>
              <form onSubmit={submitCollection} className="transport-crew-form">
                <label htmlFor="collection-amount">Amount (KES)</label>
                <input id="collection-amount" type="number" inputMode="decimal" min="0.01" max="9999999999.99" step="0.01" required disabled={!collectionAllowed} value={amount} onChange={(event) => setAmount(event.target.value)} />
                <label htmlFor="collection-notes">Notes (optional)</label>
                <textarea id="collection-notes" rows="3" maxLength="300" disabled={!collectionAllowed} value={notes} onChange={(event) => setNotes(event.target.value)} />
                <Button type="submit" size="lg" loading={submitting} disabled={!collectionAllowed || Boolean(syncingKey)}>Record collection</Button>
                {!collectionAllowed && <p>{shiftClosed ? "This shift is closed." : "This assignment is no longer open for collections."}</p>}
              </form>
            </section>

            <section className="transport-crew-card" aria-labelledby="expense-title">
              <h2 id="expense-title">Report a shift expense</h2>
              <p>Expense reports are not deducted automatically. An authorized reviewer and active deduction rule are required.</p>
              <form onSubmit={submitExpense} className="transport-crew-form">
                <label htmlFor="expense-category">Category</label>
                <input id="expense-category" type="text" maxLength="60" required disabled={shiftClosed} value={expense.category} onChange={(event) => setExpense({ ...expense, category: event.target.value })} />
                <label htmlFor="expense-amount">Expense amount (KES)</label>
                <input id="expense-amount" type="number" min="0.01" step="0.01" required disabled={shiftClosed} value={expense.amount} onChange={(event) => setExpense({ ...expense, amount: event.target.value })} />
                <label htmlFor="expense-notes">Notes</label>
                <textarea id="expense-notes" rows="3" maxLength="300" disabled={shiftClosed} value={expense.notes} onChange={(event) => setExpense({ ...expense, notes: event.target.value })} />
                <Button type="submit" loading={expenseSaving} disabled={shiftClosed}>Report expense</Button>
              </form>
              {expenses.length > 0 && <ul className="transport-crew-activity">{expenses.map((item) => <li key={item.id}>{item.category} · KES {item.amount} · {item.status}{item.notes ? ` · ${item.notes}` : ""}</li>)}</ul>}
            </section>

            <section className="transport-crew-card" aria-labelledby="close-shift-title">
              <h2 id="close-shift-title">Close shift</h2>
              {assignment.closure ? (
                <>
                  <dl className="transport-crew-facts">
                    <div><dt>Reported gross collections</dt><dd>KES {assignment.closure.reported_gross}</dd></div>
                    <div><dt>Approved expenses</dt><dd>KES {assignment.closure.approved_expenses}</dd></div>
                    <div><dt>Deductible under configured rule</dt><dd>KES {assignment.closure.deductible_expenses}</dd></div>
                    <div><dt>Expected remittance</dt><dd>{assignment.closure.expected_remittance === null ? "Not calculated" : `KES ${assignment.closure.expected_remittance}`}</dd></div>
                  </dl>
                  {assignment.closure.calculation_status === "rule_required" && (
                    <FeedbackMessage tone="warning" title="Deduction rule not yet configured">
                      Expected remittance cannot be calculated until an operations supervisor activates a deduction rule. Contact transport operations.
                    </FeedbackMessage>
                  )}
                  {assignment.closure.calculation_status === "review_required" && (
                    <FeedbackMessage tone="warning" title="Shift flagged for supervisor review">
                      This shift has been flagged for supervisor review before closure. Contact transport operations to proceed.
                    </FeedbackMessage>
                  )}
                  {assignment.closure.calculation_status === "calculated" && (
                    <FeedbackMessage tone="success" title="Remittance calculated">
                      Expected remittance is KES {assignment.closure.expected_remittance}. You can proceed to the remittance section below.
                    </FeedbackMessage>
                  )}
                  {assignment.closure.calculation_status !== "calculated" && assignment.closure.calculation_status !== "rule_required" && assignment.closure.calculation_status !== "review_required" && (
                    <FeedbackMessage tone="warning" title="Remittance calculation needs configuration">{assignment.closure.calculation_note}</FeedbackMessage>
                  )}
                  <p>Closing the shift does not confirm payment or create an account credit.</p>
                </>
              ) : (
                <>
                  <p>Collections: KES {assignment.collection_total}. Reported expenses: KES {assignment.expense_total_reported}. Only approved expense categories in an active rule can reduce the expected remittance.</p>
                  {assignment.can_close_shift !== false && <Button variant="secondary" disabled={shiftClosed} onClick={() => setConfirmClose(true)}>Review and close shift</Button>}
                </>
              )}
            </section>

            <section className="transport-crew-card" aria-labelledby="remittance-title">
              <h2 id="remittance-title">Remit reported cash</h2>
              <p>Shift closure and payment settlement are separate. An M-Pesa request stays pending until provider confirmation; cash stays pending until a clerk confirms receipt.</p>
              {!assignment.closure && <p>Close the shift first to calculate the remittance amount.</p>}
              {assignment.closure?.calculation_status === "rule_required" && <FeedbackMessage tone="warning" title="Approved deduction rule required">The shift is closed, but remittance cannot be calculated until an approved deduction rule is configured by an operations supervisor. Contact transport operations to proceed.</FeedbackMessage>}
              {assignment.closure?.calculation_status === "review_required" && <FeedbackMessage tone="warning" title="Shift close flagged for supervisor review">This shift has been flagged for supervisor review before closure. Contact transport operations.</FeedbackMessage>}
              {zeroDue && <p>No payment due for this shift.</p>}
              {assignment.closure?.calculation_status === "calculated" && remittances.length === 0 && Number(assignment.closure.expected_remittance) > 0 && <form onSubmit={createRemittance} className="transport-crew-form">
                <label htmlFor="remittance-amount">Calculated remittance (KES)</label>
                <input id="remittance-amount" type="number" readOnly value={remitAmount || assignment.closure.expected_remittance} />
                <Button type="submit" variant="secondary">Create remittance request</Button>
              </form>}
              {assignment.closure?.calculation_status === "calculated" && Number(assignment.closure.expected_remittance) === 0 && <p>No remittance is due from this shift.</p>}
              {remittances.map((remittance) => {
                const outstanding = remittance.outstanding_amount;
                const available = remittance.available_to_pay;
                const currentAmount = paymentAmount[remittance.id] ?? available ?? "";
                const amountValid = Number(currentAmount) > 0 && Number(currentAmount) <= Number(available);
                return (
                  <div className="transport-remittance" key={remittance.id}>
                    <p><strong>{remittance.payment_reference}</strong> · <StatusBadge status={remittance.status} /></p>
                    <p>Expected KES {remittance.amount} · Confirmed receipts KES {remittance.received_amount} · Outstanding KES {outstanding}</p>
                    {remittance.can_pay ? (
                      <div className="transport-crew-form">
                        <label htmlFor={`payment-amount-${remittance.id}`}>Payment amount (KES)</label>
                        <input id={`payment-amount-${remittance.id}`} type="number" inputMode="decimal" min="0.01" max={available} step="0.01" value={currentAmount} onChange={(event) => setPaymentAmount({ ...paymentAmount, [remittance.id]: event.target.value })} />
                        <div className="transport-crew-actions">
                          <Button variant="secondary" loading={paymentAction === `stk:${remittance.id}`} disabled={Boolean(paymentAction) || !amountValid} onClick={() => startStk(remittance, currentAmount)}>Request M-Pesa STK</Button>
                          <Button variant="secondary" loading={paymentAction === `cash:${remittance.id}`} disabled={Boolean(paymentAction) || !amountValid} onClick={() => submitCashHandover(remittance, currentAmount)}>Submit cash handover</Button>
                        </div>
                      </div>
                    ) : Number(outstanding) > 0 && <p>Check the status of existing payment attempts or contact transport staff for review.</p>}
                    {(remittance.payments || []).map((payment) => <p key={payment.id}>Payment {payment.method} · <StatusBadge status={payment.status} /> · Reported KES {payment.reported_amount} · Received {payment.received_amount == null ? "awaiting confirmation" : `KES ${payment.received_amount}`}{payment.receipt ? ` · receipt ${payment.receipt}` : ""}</p>)}
                    {Number(remittance.received_amount) > 0 && <Button variant="secondary" loading={receiptLoading === remittance.id} onClick={() => viewReceipt(remittance)}>View receipt</Button>}
                  </div>
                );
              })}
              {receipt && <section className="transport-crew-receipt" aria-live="polite"><h3>Confirmed receipt</h3><dl><div><dt>Reference</dt><dd>{receipt.payment_reference}</dd></div><div><dt>Vehicle</dt><dd>{receipt.vehicle}</dd></div><div><dt>Route</dt><dd>{receipt.route}</dd></div><div><dt>Reported amount</dt><dd>KES {receipt.reported_amount}</dd></div><div><dt>Confirmed received</dt><dd>KES {receipt.received_amount}</dd></div><div><dt>Status</dt><dd>{receipt.status}</dd></div></dl>{(receipt.payments || []).map((payment) => <p key={payment.id}>Payment {payment.method}: {payment.receipt || "Provider receipt unavailable"} · {payment.status} · Received {payment.received_amount === null ? "not confirmed" : `KES ${payment.received_amount}`}</p>)}</section>}
            </section>

            <section className="transport-crew-card" aria-labelledby="recent-activity-title">
              <h2 id="recent-activity-title">Recent activity</h2>
              {collections.length ? <ul className="transport-crew-activity">{collections.map((item) => <li key={item.id}>KES {item.amount} · {item.recorded_at ? new Date(item.recorded_at).toLocaleString("en-KE", nairobiTime) : "Time unavailable"}{item.notes ? ` · ${item.notes}` : ""} · Reported</li>)}</ul> : <p>No collections have been recorded for this assignment yet.</p>}
            </section>
          </>
        )}
        {offlineDrafts.length > 0 && (
          <section className="transport-crew-card" aria-label="Collections waiting to sync">
            <h2>Collections waiting to sync</h2>
            {offlineDrafts.map((draft) => (
              <div className="transport-offline-draft" key={draft.client_key}>
                <div>
                  <p><strong>KES {draft.amount}</strong> · {draft.vehicle || `Assignment #${draft.assignment}`}{draft.notes ? ` · ${draft.notes}` : ""}</p>
                  <p>{draft.temporary ? "Waiting to sync while this page is open" : waitingForSync}</p>
                </div>
                <Button variant="secondary" size="lg" loading={syncingKey === draft.client_key} disabled={submitting || Boolean(syncingKey)} onClick={() => retryDraft(draft)}>Retry sync</Button>
              </div>
            ))}
          </section>
        )}
        {shiftState !== "loading" && shiftState !== "error" && <section className="transport-crew-card" aria-labelledby="crew-history-title">
          <div className="transport-crew-assignment-title">
            <div><h2 id="crew-history-title">Past assignments</h2><span>Vehicles and shifts previously assigned to your account</span></div>
            <Button variant="secondary" onClick={load} loading={historyState === "loading"}>Refresh</Button>
          </div>
          {historyState === "loading" && <LoadingState label="Loading your assignment history…" />}
          {historyState === "error" && <FeedbackMessage tone="danger" title="Assignment history unavailable" action={<Button variant="secondary" onClick={load} loading={historyState === "loading"}>Retry</Button>}>{historyError}</FeedbackMessage>}
          {historyState === "ready" && history.filter((item) => item.id !== assignment?.id).length === 0 && <p>No earlier assignments are recorded for your account.</p>}
          {historyState === "ready" && history.filter((item) => item.id !== assignment?.id).length > 0 && <ul className="transport-crew-activity">
            {history.filter((item) => item.id !== assignment?.id).map((item) => <li key={item.id}>
              <strong>{item.vehicle_registration} · {item.route_name}</strong> · {item.starts_at ? new Date(item.starts_at).toLocaleDateString("en-KE", nairobiTime) : "Date unavailable"} · {item.status}<br />
              Reported collections KES {item.collection_total} · Confirmed receipts KES {item.confirmed_remittance_total} · Pending KES {item.pending_remittance_total}
              <div className="transport-crew-actions"><Button variant="secondary" onClick={() => showAssignment(item.id)}>View shift {item.vehicle_registration}</Button></div>
            </li>)}
          </ul>}
        </section>}
        {confirmClose && <ConfirmModal title="Close this shift?" message="This stops new collections on this assignment. Any remittance remains pending until confirmed separately." confirmLabel="Close shift" onCancel={() => setConfirmClose(false)} onConfirm={closeShift} loading={closing} />}
      </main>
    </Layout>
  );
}
