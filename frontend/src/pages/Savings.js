import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import MpesaPayModal from "../components/MpesaPayModal";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import AccountCard from "../components/ui/AccountCard";
import Button from "../components/ui/Button";
import DataTable from "../components/ui/DataTable";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import "../styles/savings.css";

const money = (value) => {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const amount = Number(value);
  return Number.isFinite(amount) ? `KES ${amount.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "Unavailable";
};
const date = (value) => value ? new Date(value).toLocaleDateString("en-KE") : "—";

export default function Savings() {
  const { user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [collateral, setCollateral] = useState(null);
  const [balanceLoading, setBalanceLoading] = useState(true);
  const [balanceError, setBalanceError] = useState(false);
  const [withdrawals, setWithdrawals] = useState([]);
  const [withdrawalsLoading, setWithdrawalsLoading] = useState(true);
  const [withdrawalsError, setWithdrawalsError] = useState(false);
  const [statement, setStatement] = useState(null);
  const [statementState, setStatementState] = useState("idle");
  const [exitRequest, setExitRequest] = useState(null);
  const [exitLoading, setExitLoading] = useState(false);
  const [exitError, setExitError] = useState(false);
  const [exitReason, setExitReason] = useState("");
  const [depositAmount, setDepositAmount] = useState("");
  const [depositAccount, setDepositAccount] = useState("bosa");
  const [paymentAmount, setPaymentAmount] = useState(null);
  const [depositError, setDepositError] = useState("");
  const [depositBusy, setDepositBusy] = useState(false);

  const loadBalances = useCallback(async () => {
    setBalanceLoading(true);
    setBalanceError(false);
    try {
      const response = await api.get("collateral/status/");
      if (!response.data || typeof response.data !== "object") throw new Error("Invalid balance response");
      setCollateral(response.data);
    } catch {
      setCollateral(null);
      setBalanceError(true);
    } finally {
      setBalanceLoading(false);
    }
  }, []);

  const loadWithdrawals = useCallback(async () => {
    setWithdrawalsLoading(true);
    setWithdrawalsError(false);
    try {
      const response = await api.get("withdrawals/");
      const rows = Array.isArray(response.data) ? response.data : response.data?.results;
      if (!Array.isArray(rows)) throw new Error("Invalid withdrawal response");
      setWithdrawals(rows);
    } catch {
      setWithdrawals([]);
      setWithdrawalsError(true);
    } finally {
      setWithdrawalsLoading(false);
    }
  }, []);

  const loadExit = useCallback(async () => {
    setExitLoading(true);
    setExitError(false);
    try {
      const response = await api.get("exit-request/");
      setExitRequest(response.data?.exit_request || null);
    } catch {
      setExitError(true);
    } finally {
      setExitLoading(false);
    }
  }, []);

  const loadStatement = useCallback(async () => {
    setStatementState("loading");
    try {
      const response = await api.get("savings/statement/");
      if (!Array.isArray(response.data?.entries)) throw new Error("Invalid statement response");
      setStatement(response.data);
      setStatementState("success");
    } catch {
      setStatement(null);
      setStatementState("error");
    }
  }, []);

  useEffect(() => { loadBalances(); loadWithdrawals(); loadExit(); }, [loadBalances, loadWithdrawals, loadExit]);
  useEffect(() => { if (tab === "statement") loadStatement(); }, [tab, loadStatement]);

  const depositValue = Number(depositAmount);
  const validDeposit = Number.isFinite(depositValue) && depositValue > 0;
  const format = (value) => value === null || value === undefined ? "Unavailable" : money(value);
  const pendingHold = collateral?.fosa_withdrawals_pending ?? collateral?.pending_withdrawals ?? null;

  const openDeposit = () => {
    setDepositError("");
    if (!validDeposit) { setDepositError("Enter an amount greater than zero."); return; }
    setPaymentAmount(depositValue);
  };

  const submitExit = async () => {
    setDepositBusy(true);
    setDepositError("");
    try {
      await api.post("exit-request/", { reason: exitReason });
      setExitReason("");
      await loadExit();
    } catch (error) {
      setDepositError(error.response?.data?.error || "Your exit request could not be submitted. Try again.");
    } finally { setDepositBusy(false); }
  };

  const cancelExit = async () => {
    if (!exitRequest || !window.confirm("Cancel your exit request?")) return;
    setDepositBusy(true);
    try {
      await api.post(`exit-request/${exitRequest.id}/cancel/`);
      await loadExit();
    } catch (error) {
      setDepositError(error.response?.data?.error || "Your request could not be cancelled.");
    } finally { setDepositBusy(false); }
  };

  return (
    <Layout>
      {() => (
        <div className="savings-page">
          <PageHeading
            eyebrow="Member accounts"
            title="Savings"
            description="Review recorded account balances, available funds, and pending withdrawal requests."
            actions={<Button as={Link} to="/transactions" variant="secondary"><Icon name="receipt" /> View transactions</Button>}
          />

          <div className="savings-account-grid">
            <AccountCard label="FOSA available" value={balanceLoading ? undefined : format(collateral?.fosa_withdrawable)} helper="Available after recorded holds" icon="coins" loading={balanceLoading} />
            <AccountCard label="Recorded FOSA balance" value={balanceLoading ? undefined : format(collateral?.fosa_balance)} helper="Flexible savings account balance" icon="wallet" loading={balanceLoading} />
            <AccountCard label="Pending withdrawal holds" value={balanceLoading ? undefined : format(pendingHold)} helper="Pending or uncertain payout requests" icon="clock" loading={balanceLoading} />
            <AccountCard label="Recorded BOSA savings" value={balanceLoading ? undefined : format(collateral?.bosa_balance)} helper="BOSA recorded savings; share capital is tracked separately when available" icon="bank" loading={balanceLoading} />
          </div>

          {balanceError && <FeedbackMessage tone="warning" title="Balance availability could not be refreshed" action={<Button variant="secondary" size="sm" onClick={loadBalances}><Icon name="refresh" /> Retry</Button>}>Available and held amounts remain unavailable until the balance service responds.</FeedbackMessage>}

          <div className="savings-tabs" role="tablist" aria-label="Savings sections">
            <button type="button" role="tab" aria-selected={tab === "overview"} onClick={() => setTab("overview")}>Balances and activity</button>
            <button type="button" role="tab" aria-selected={tab === "statement"} onClick={() => setTab("statement")}>Savings statement</button>
            <button type="button" role="tab" aria-selected={tab === "exit"} onClick={() => setTab("exit")}>Membership exit</button>
          </div>

          {tab === "overview" && <div className="savings-content-grid">
            <section className="ui-panel savings-panel" aria-labelledby="deposit-title">
              <div className="ui-panel-header"><h2 className="ui-panel-title" id="deposit-title">Make a deposit</h2><Icon name="coins" /></div>
              <div className="ui-panel-body savings-form">
                <p className="ui-muted">Deposits are added to your account only after the payment provider confirms them.</p>
                <fieldset className="savings-account-choice">
                  <legend>Deposit account</legend>
                  {[{ value: "bosa", label: "BOSA", detail: "Core savings" }, { value: "fosa", label: "FOSA", detail: "Flexible savings" }].map((account) => (
                    <label className={depositAccount === account.value ? "selected" : ""} key={account.value}>
                      <input type="radio" name="deposit-account" value={account.value} checked={depositAccount === account.value} onChange={() => setDepositAccount(account.value)} />
                      <span><strong>{account.label}</strong><small>{account.detail}</small></span>
                    </label>
                  ))}
                </fieldset>
                {depositAccount === "bosa" && <FeedbackMessage>Routine BOSA deposits are not a share-capital register and are not routine withdrawals.</FeedbackMessage>}
                <FormField label="Amount (KES)" htmlFor="savings-deposit-amount" error={depositError}>
                  <input id="savings-deposit-amount" className="ui-input" type="number" min="1" step="1" inputMode="decimal" value={depositAmount} onChange={(event) => { setDepositAmount(event.target.value); setDepositError(""); }} placeholder="Enter amount" />
                </FormField>
                <Button variant="accent" onClick={openDeposit} disabled={depositBusy}><Icon name="wallet" /> Continue to M-Pesa</Button>
              </div>
            </section>

            <section className="ui-panel savings-panel" aria-labelledby="withdrawal-title">
              <div className="ui-panel-header"><div><p className="ui-eyebrow">Funds access</p><h2 className="ui-panel-title" id="withdrawal-title">FOSA withdrawal status</h2></div></div>
              <div className="ui-panel-body savings-form">
                <dl className="savings-facts">
                  <div><dt>Available</dt><dd>{balanceLoading ? "Loading…" : format(collateral?.fosa_withdrawable)}</dd></div>
                  <div><dt>FOSA balance</dt><dd>{balanceLoading ? "Loading…" : format(collateral?.fosa_balance)}</dd></div>
                  <div><dt>Held for pending withdrawals</dt><dd>{balanceLoading ? "Loading…" : format(pendingHold)}</dd></div>
                </dl>
                <FeedbackMessage tone="warning" title="Withdrawals are unavailable">Live M-Pesa disbursement is not configured. No withdrawal can be submitted from this account.</FeedbackMessage>
                <p className="ui-muted">A request acceptance is not proof that funds were paid. Uncertain or pending payouts remain held for review.</p>
                {withdrawalsError && <FeedbackMessage tone="danger" title="Withdrawal history could not be loaded" action={<Button variant="secondary" size="sm" onClick={loadWithdrawals}><Icon name="refresh" /> Retry</Button>}>Try again to see the latest payout status.</FeedbackMessage>}
              </div>
            </section>

            <section className="ui-panel savings-panel savings-withdrawals" aria-labelledby="withdrawal-history-title">
              <div className="ui-panel-header"><div><p className="ui-eyebrow">Payout records</p><h2 className="ui-panel-title" id="withdrawal-history-title">FOSA withdrawal requests</h2></div><Button variant="secondary" size="sm" onClick={loadWithdrawals} loading={withdrawalsLoading}><Icon name="refresh" /> Refresh</Button></div>
              {withdrawalsLoading ? <LoadingState label="Loading withdrawal history…" /> : withdrawalsError ? null : withdrawals.length === 0 ? <div className="ui-empty"><strong>No withdrawal requests</strong>Your withdrawal requests will appear here.</div> : (
                <DataTable label="FOSA withdrawal request history"><table className="ui-table"><thead><tr><th>Requested</th><th>Reference</th><th>Destination</th><th>Amount</th><th>Status</th></tr></thead><tbody>{withdrawals.map((row) => <tr key={row.reference}><td>{date(row.created_at)}</td><td>{row.reference}</td><td>{row.destination_type} {row.destination_masked || ""}</td><td className="ui-money">{money(row.amount)}</td><td><StatusBadge status={row.status} /></td></tr>)}</tbody></table></DataTable>
              )}
            </section>
          </div>}

          {tab === "statement" && <section className="ui-panel savings-panel" aria-labelledby="savings-statement-title">
            <div className="ui-panel-header"><h2 className="ui-panel-title" id="savings-statement-title">Savings activity</h2><Button variant="secondary" size="sm" onClick={loadStatement} loading={statementState === "loading"}><Icon name="refresh" /> Refresh</Button></div>
            {statementState === "loading" && <LoadingState label="Loading savings statement…" />}
            {statementState === "error" && <div className="ui-panel-body"><FeedbackMessage tone="danger" title="Savings statement could not be loaded" action={<Button variant="secondary" onClick={loadStatement}><Icon name="refresh" /> Retry</Button>}>Please retry. The response could not be read as a valid statement.</FeedbackMessage></div>}
            {statementState === "success" && (statement.entries.length === 0 ? <div className="ui-empty"><strong>No savings activity recorded</strong>Account activity will appear when there are posted savings entries.</div> : <DataTable label="Savings statement entries"><table className="ui-table"><thead><tr><th>Date</th><th>Account</th><th>Entry</th><th>Amount</th><th>Recorded balance</th></tr></thead><tbody>{statement.entries.map((entry, index) => <tr key={entry.id || `${entry.created_at}-${index}`}><td>{date(entry.created_at || entry.date)}</td><td>{String(entry.account_type || "fosa").toUpperCase()}</td><td>{entry.type || "Activity"}</td><td className="ui-money">{money(entry.amount)}</td><td className="ui-money">{format(entry.balance)}</td></tr>)}</tbody></table></DataTable>)}
          </section>}

          {tab === "exit" && <section className="ui-panel savings-panel" aria-labelledby="exit-title">
            <div className="ui-panel-header"><div><p className="ui-eyebrow">Membership</p><h2 className="ui-panel-title" id="exit-title">Membership exit request</h2></div></div>
            <div className="ui-panel-body savings-form">
              <p className="ui-muted">A membership exit is reviewed by staff. BOSA funds are not released merely because a request is submitted.</p>
              {exitLoading && <LoadingState label="Loading your membership request…" />}
              {exitError && <FeedbackMessage tone="danger" title="Membership request could not be loaded" action={<Button variant="secondary" onClick={loadExit}><Icon name="refresh" /> Retry</Button>}>Try again to check your current request.</FeedbackMessage>}
              {!exitLoading && !exitError && exitRequest && <div className="savings-exit-status"><p><StatusBadge status={exitRequest.status} label={exitRequest.status_label || exitRequest.status} /></p><dl className="savings-facts"><div><dt>Submitted</dt><dd>{date(exitRequest.created_at)}</dd></div><div><dt>Recorded BOSA balance at request</dt><dd>{format(exitRequest.bosa_balance)}</dd></div><div><dt>Release date</dt><dd>{exitRequest.release_date ? date(exitRequest.release_date) : "Pending review"}</dd></div></dl>{exitRequest.rejection_reason && <FeedbackMessage tone="warning" title="Review outcome">{exitRequest.rejection_reason}</FeedbackMessage>}{["pending", "approved"].includes(exitRequest.status) && <Button variant="secondary" onClick={cancelExit} loading={depositBusy}>Cancel request</Button>}</div>}
              {!exitLoading && !exitError && !exitRequest && <><FormField label="Reason for leaving (optional)" htmlFor="exit-reason"><textarea id="exit-reason" className="ui-textarea" rows="4" value={exitReason} onChange={(event) => setExitReason(event.target.value)} /></FormField>{depositError && <FeedbackMessage tone="danger">{depositError}</FeedbackMessage>}<Button variant="danger" onClick={submitExit} loading={depositBusy}>Submit exit request</Button></>}
            </div>
          </section>}

          {paymentAmount !== null && <MpesaPayModal paymentType="deposit" amount={paymentAmount} accountType={depositAccount} defaultPhone={user?.phone_number || ""} onClose={() => setPaymentAmount(null)} onConfirmed={() => { setPaymentAmount(null); setDepositAmount(""); loadBalances(); }} />}
        </div>
      )}
    </Layout>
  );
}
