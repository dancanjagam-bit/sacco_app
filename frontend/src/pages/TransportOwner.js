import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import { ROUTES } from "../navigation/routes";
import "../styles/transport-owner.css";

const kes = (value) => value === null || value === undefined
  ? "Unavailable"
  : `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function dateTime(value) {
  return value ? new Date(value).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Nairobi" }) : "Not recorded";
}

const operationalLabels = { active: "Assigned", available: "Available", inactive: "Inactive", former_owner: "Formerly owned" };
const accountingLabels = { posted: "Receipt posted", reversed: "Receipt reversed", awaiting_journal: "Receipt awaiting posting", unverified: "Receipt awaiting confirmation" };
const accountLabel = (category) => ({ savings: "Savings", loan_repayment: "Loan repayment", welfare: "Welfare contribution", welfare_contribution: "Welfare contribution" })[category] || String(category || "Unclassified").replaceAll("_", " ");

export default function TransportOwner() {
  const { vehicleId } = useParams();
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [receiptError, setReceiptError] = useState("");
  const [receiptLoading, setReceiptLoading] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    setReceipt(null);
    setReceiptError("");
    try {
      const response = vehicleId
        ? await api.get(`transport/owner/vehicles/${vehicleId}/`)
        : await api.get("transport/owner/");
      setData(response.data);
      setState("ready");
    } catch (requestError) {
      setData(null);
      setError(requestError.response?.data?.detail || "Vehicle information could not be loaded. Try again.");
      setState("error");
    }
  }, [vehicleId]);

  useEffect(() => { load(); }, [load]);

  async function showReceipt(remittanceId) {
    setReceiptLoading(remittanceId);
    setReceiptError("");
    try {
      const response = await api.get(`transport/remittances/${remittanceId}/receipt/`);
      setReceipt(response.data);
    } catch (requestError) {
      setReceipt(null);
      setReceiptError(requestError.response?.data?.detail || "Receipt details could not be loaded.");
    } finally {
      setReceiptLoading("");
    }
  }

  const vehicles = vehicleId ? (data ? [data] : []) : (Array.isArray(data?.vehicles) ? data.vehicles : []);

  return (
    <Layout>
      <main className="transport-owner-page">
        <PageHeading
          eyebrow="Owner workspace"
          title={vehicleId ? (data?.registration || "Vehicle details") : "My vehicles"}
          description={vehicleId
            ? "Ownership-period activity, crew assignment history, collections, expenses, and remittance receipts."
            : "Reported collections and expenses are shown separately from confirmed remittance receipts."}
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>}
        />
        {vehicleId && <p className="transport-owner-back"><Link to={ROUTES.transportOwner}>← Back to my vehicles</Link></p>}
        {state === "loading" && <LoadingState label="Loading vehicle activity…" />}
        {state === "error" && <FeedbackMessage tone="danger" title="Vehicle workspace unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
        {state === "ready" && !vehicleId && vehicles.length === 0 && (
          <div className="ui-empty"><strong>No vehicles are linked to this owner account.</strong><span>Ask authorized operations staff to review the ownership record.</span></div>
        )}
        {state === "ready" && vehicles.length > 0 && (
          <div className="transport-owner-list">
            {vehicles.map((vehicle) => (
              <VehicleCard key={vehicle.id} vehicle={vehicle} detail={Boolean(vehicleId)} onReceipt={showReceipt} receiptLoading={receiptLoading} />
            ))}
          </div>
        )}
        {receiptError && <FeedbackMessage tone="danger" title="Receipt unavailable">{receiptError}</FeedbackMessage>}
        {receipt && <ReceiptPanel receipt={receipt} onClose={() => setReceipt(null)} />}
      </main>
    </Layout>
  );
}

function VehicleCard({ vehicle, detail, onReceipt, receiptLoading }) {
  const assignment = vehicle.current_assignment;
  const status = vehicle.operational_status || (vehicle.active ? "active" : "inactive");
  return (
    <section className="ui-panel transport-owner-vehicle">
      <div className="ui-panel-header transport-owner-vehicle-heading">
        <div className="transport-owner-title">
          <span className="transport-owner-icon" aria-hidden="true"><Icon name="truck" size={22} /></span>
          <div><p className="ui-eyebrow">Vehicle</p><h2>{vehicle.registration}</h2><span>{vehicle.make_model || "Model not recorded"} · {vehicle.owner_label || "Owner information unavailable"}</span></div>
        </div>
        <StatusBadge status={status} label={operationalLabels[status]} />
      </div>
      <div className="ui-panel-body">
        {assignment ? (
          <div className="transport-owner-assignment">
            <div><span>Current route</span><strong>{assignment.route_name || "Route unavailable"}</strong></div>
            <div><span>Driver</span><strong>{assignment.driver_name || "Not assigned"}</strong></div>
            <div><span>Conductor</span><strong>{assignment.conductor_name || "No conductor assigned"}</strong></div>
            <div><span>Shift</span><StatusBadge status={assignment.shift_status || assignment.status} /></div>
          </div>
        ) : <p className="ui-muted">No current crew assignment is recorded.</p>}
        <div className="transport-owner-metrics">
          <Metric label="Gross collections reported today" value={kes(vehicle.reported_collections_today)} />
          <Metric label="Reported expenses today" value={kes(vehicle.reported_expenses_today)} />
          <Metric label="Approved expenses today" value={kes(vehicle.approved_expenses_today)} />
          <Metric label="Expected remittances" value={kes(vehicle.expected_remittances)} />
          <Metric label="Confirmed remittance receipts" value={kes(vehicle.confirmed_receipts)} />
          <Metric label="Known outstanding remittances" value={kes(vehicle.pending_remittance_amount)} />
        </div>
        {vehicle.expected_amount_unavailable_count > 0 && <FeedbackMessage tone="warning" title="Some expected amounts need review">Shifts with expected remittance unavailable: {vehicle.expected_amount_unavailable_count}.</FeedbackMessage>}
        {!detail && <Link className="ui-button ui-button-secondary" to={`${ROUTES.transportOwner}/vehicles/${vehicle.id}`}>View vehicle activity <Icon name="arrowRight" /></Link>}
        {vehicle.confirmed_payments_with_unavailable_amount > 0 && <FeedbackMessage tone="warning" title="Some older confirmed amounts need review">{vehicle.confirmed_payments_with_unavailable_amount} confirmed payment record(s) do not have a separately stored received amount and are not included in the confirmed total.</FeedbackMessage>}

        {detail && <>
          <section className="transport-owner-section">
            <h3>Assignment history</h3>
            {(vehicle.assignments || []).length === 0 ? <p className="ui-muted">No assignment history recorded for your ownership periods.</p> : (
              <div className="transport-owner-history">
                {vehicle.assignments.map((row) => (
                  <article className="transport-owner-history-row" key={row.id}>
                    <div className="transport-owner-history-heading"><strong>{row.vehicle_registration} · {row.route_name}</strong><StatusBadge status={row.status} /></div>
                    <p>Driver: {row.driver_name || "Not assigned"} · Conductor: {row.conductor_name || "No conductor"}</p>
                    <p>{dateTime(row.starts_at)} – {dateTime(row.ends_at)}</p>
                    <dl><div><dt>Reported collections</dt><dd>{kes(row.collection_total)}</dd></div><div><dt>Reported expenses</dt><dd>{kes(row.expense_total_reported)}</dd></div><div><dt>Shift</dt><dd>{row.shift_status || "Unavailable"}</dd></div></dl>
                    {row.closure && <p><strong>Close:</strong> gross {kes(row.closure.reported_gross)} · approved expenses {kes(row.closure.approved_expenses)} · expected remittance {kes(row.closure.expected_remittance)}</p>}
                    {(row.collections || []).length > 0 && <details><summary>Collection entries ({row.collections.length})</summary><ul>{row.collections.map((item) => <li key={item.id}>{dateTime(item.recorded_at)} · {kes(item.amount)}{item.notes ? ` · ${item.notes}` : ""}</li>)}</ul></details>}
                    {(row.expenses || []).length > 0 && <details><summary>Expense reports ({row.expenses.length})</summary><ul>{row.expenses.map((item) => <li key={item.id}>{dateTime(item.created_at)} · {item.category} · {kes(item.amount)} · {item.status}</li>)}</ul></details>}
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="transport-owner-section">
            <h3>Remittances and receipts</h3>
            {(vehicle.remittances || []).length === 0 ? <p className="ui-muted">No remittance records are available for your ownership periods.</p> : vehicle.remittances.map((remittance) => (
              <article className="transport-owner-remittance" key={remittance.id}>
                <div><strong>{remittance.payment_reference}</strong><StatusBadge status={remittance.status} /></div>
                <p>Expected {kes(remittance.amount)} · Confirmed receipts {kes(remittance.received_amount)} · Outstanding {kes(remittance.outstanding_amount)}</p>
                {(remittance.payments || []).some((payment) => payment.accounting_status || (payment.account_activity || []).length) && (
                  <section className="transport-owner-linked-activity" aria-label="Linked account activity">
                    <h4>Linked account activity</h4>
                    {remittance.payments.map((payment) => <PaymentAccounting key={payment.id} payment={payment} />)}
                  </section>
                )}
                <Button variant="secondary" loading={receiptLoading === remittance.id} onClick={() => onReceipt(remittance.id)}>View remittance receipt</Button>
              </article>
            ))}
          </section>
          {vehicle.ownership_history?.length > 0 && (
            <section className="transport-owner-section">
              <h3>Ownership history</h3>
              <div className="transport-owner-history">
                {vehicle.ownership_history.map((row) => (
                  <article key={row.id} className="transport-owner-history-row">
                    <strong>{row.owner_name}</strong>
                    <p>{dateTime(row.starts_at)} – {row.ends_at ? dateTime(row.ends_at) : "Present"}</p>
                  </article>
                ))}
              </div>
            </section>
          )}
        </>}
      </div>
    </section>
  );
}

function Metric({ label, value }) {
  return <div className="transport-owner-metric"><span>{label}</span><strong>{value}</strong></div>;
}

function PaymentAccounting({ payment }) {
  const allocations = payment.journal_allocations || [];
  const legacyEntries = payment.account_activity || [];
  if (!payment.accounting_status && !allocations.length && !legacyEntries.length) return null;
  return (
    <div>
      <p>{payment.receipt || `Payment #${payment.id}`} · {accountingLabels[payment.accounting_status] || "Linked account activity"}
        {payment.receipt_journal_id && ` · Receipt journal #${payment.receipt_journal_id}`}
        {payment.receipt_reversal_id && ` · Receipt reversal #${payment.receipt_reversal_id}`}
        {payment.allocation_reversal_id && ` · Allocation reversal #${payment.allocation_reversal_id}`}
      </p>
      {(allocations.length > 0 || legacyEntries.length > 0) && <ul aria-label="Linked account entries">
        {allocations.map((entry) => <li key={`${entry.journal_entry_id}-${entry.category}`}>{accountLabel(entry.category)} · {kes(entry.amount)} · Journal #{entry.journal_entry_id}</li>)}
        {legacyEntries.map((entry) => <li key={entry.allocation_id}>{accountLabel(entry.category)} · {kes(entry.allocated_amount)} · Ledger entry #{entry.transaction_id}</li>)}
      </ul>}
    </div>
  );
}

function ReceiptPanel({ receipt, onClose }) {
  return (
    <section className="ui-panel transport-owner-receipt" aria-live="polite">
      <div className="ui-panel-header"><div><p className="ui-eyebrow">Transport receipt</p><h2>{receipt.payment_reference}</h2></div><Button variant="ghost" onClick={onClose} aria-label="Close receipt details"><Icon name="close" /></Button></div>
      <div className="ui-panel-body">
        <p>Status: <StatusBadge status={receipt.status} /></p>
        <dl><div><dt>Reported amount</dt><dd>{kes(receipt.reported_amount)}</dd></div><div><dt>Confirmed receipts</dt><dd>{kes(receipt.received_amount)}</dd></div><div><dt>Outstanding</dt><dd>{kes(receipt.outstanding_amount)}</dd></div></dl>
        <h3>Payment history</h3>
        {(receipt.payments || []).length === 0 ? <p className="ui-muted">No payment attempts have been recorded.</p> : <ul>{receipt.payments.map((payment) => <li key={payment.id}>
          <StatusBadge status={payment.status} /> {payment.method} · reported {kes(payment.reported_amount)} · received {kes(payment.received_amount)} · unallocated {kes(payment.unallocated_amount)} · {payment.receipt || payment.provider_reference || "No provider receipt recorded"}
          <PaymentAccounting payment={payment} />
        </li>)}</ul>}
        {(receipt.payments || []).some((payment) => Number(payment.unallocated_amount || 0) > 0) && <p>Some received funds are awaiting allocation.</p>}
      </div>
    </section>
  );
}
