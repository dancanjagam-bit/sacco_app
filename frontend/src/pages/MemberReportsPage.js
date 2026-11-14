import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Button from "../components/ui/Button";
import DataTable from "../components/ui/DataTable";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import StatusBadge from "../components/ui/StatusBadge";
import api from "../api/axios";
import "../styles/member-reports.css";

const money = (value) => {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const amount = Number(value);
  return Number.isFinite(amount) ? `KES ${amount.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "Unavailable";
};

export default function MemberReportsPage({ user }) {
  const loans = Array.isArray(user?.loans) ? user.loans : [];
  const [dividends, setDividends] = useState([]);
  const [dividendState, setDividendState] = useState("loading");

  const loadDividends = useCallback(async () => {
    setDividendState("loading");
    try {
      const response = await api.get("dividends/");
      const rows = Array.isArray(response.data) ? response.data : response.data?.results;
      if (!Array.isArray(rows)) throw new Error("Invalid dividend response");
      setDividends(rows);
      setDividendState("success");
    } catch {
      setDividends([]);
      setDividendState("error");
    }
  }, []);

  useEffect(() => { loadDividends(); }, [loadDividends]);

  return <div className="member-reports-page">
    <header className="member-reports-heading">
      <div><p className="ui-eyebrow">Member reporting</p><h1 className="section-title">Loan and dividend reports</h1><p className="section-subtitle">Review loan application records and dividend entries. Use your transaction statement for posted account activity.</p></div>
      <Button as={Link} to="/transactions" variant="accent"><Icon name="receipt" /> Transactions and statements</Button>
    </header>

    <section className="ui-panel member-reports-panel" aria-labelledby="loan-report-title">
      <div className="ui-panel-header"><div><p className="ui-eyebrow">Credit</p><h2 className="ui-panel-title" id="loan-report-title">Loan applications and recorded balances</h2></div></div>
      <div className="member-loan-report-note">An approved application is not evidence that funds were sent. This system does not yet record a separate confirmed disbursement state.</div>
      {loans.length === 0 ? <div className="ui-empty"><strong>No loan applications found</strong>Loan applications will appear here when submitted.</div> : <div className="member-loan-report-list">{loans.map((loan) => <article className="member-loan-report-card" key={loan.id}>
        <header><div><p className="ui-eyebrow">Application</p><h3>Loan application #{loan.id}</h3></div><StatusBadge status={loan.status} /></header>
        <dl className="member-loan-report-facts"><div><dt>Requested principal</dt><dd>{money(loan.amount)}</dd></div><div><dt>Interest rate</dt><dd>{loan.interest === null || loan.interest === undefined ? "Unavailable" : `${loan.interest}%`}</dd></div><div><dt>Repayment period</dt><dd>{loan.repayment_months ? `${loan.repayment_months} months` : "Unavailable"}</dd></div><div><dt>Recorded loan balance</dt><dd>{money(loan.balance)}</dd></div><div><dt>Lifecycle status</dt><dd>{loan.status || "Unavailable"}</dd></div></dl>
        {loan.remarks && <p className="ui-muted">Staff note: {loan.remarks}</p>}
      </article>)}</div>}
    </section>

    <section className="ui-panel member-reports-panel" aria-labelledby="dividend-report-title">
      <div className="ui-panel-header"><div><p className="ui-eyebrow">Returns</p><h2 className="ui-panel-title" id="dividend-report-title">Dividend history</h2></div><Button variant="secondary" size="sm" onClick={loadDividends} loading={dividendState === "loading"}><Icon name="refresh" /> Refresh</Button></div>
      {dividendState === "loading" && <LoadingState label="Loading dividend history…" />}
      {dividendState === "error" && <div className="ui-panel-body"><FeedbackMessage tone="warning" title="Dividend history unavailable" action={<Button variant="secondary" onClick={loadDividends}><Icon name="refresh" /> Retry</Button>}>We could not load dividend records. Try again.</FeedbackMessage></div>}
      {dividendState === "success" && dividends.length === 0 && <div className="ui-empty"><strong>No dividend records are available for this account.</strong>Only recorded dividend entries appear here.</div>}
      {dividendState === "success" && dividends.length > 0 && <DataTable label="Dividend history"><table className="ui-table"><thead><tr><th>Year</th><th>Rate</th><th>Balance used</th><th>Dividend recorded</th></tr></thead><tbody>{dividends.map((row, index) => <tr key={row.id || row.year || index}><td>{row.year || "—"}</td><td>{row.rate == null ? "Unavailable" : `${row.rate}%`}</td><td>{money(row.balance)}</td><td className="ui-money">{money(row.dividend)}</td></tr>)}</tbody></table></DataTable>}
    </section>
  </div>;
}
