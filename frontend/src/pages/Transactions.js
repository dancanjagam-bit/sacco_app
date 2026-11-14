import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import DataTable from "../components/ui/DataTable";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import { downloadFailureMessage, downloadStatement } from "../utils/downloadStatement";
import "../styles/member-financial.css";

const emptyFilters = { type: "", from: "", to: "", search: "" };

function money(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "Unavailable";
  return `KES ${numeric.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatStatus(entry) {
  if (entry.withdrawal_status) {
    return { status: entry.withdrawal_status, label: entry.withdrawal_status === "needs_review" ? "Needs review" : undefined };
  }
  if (entry.type === "loan" && /application/i.test(entry.note || "")) {
    return { status: "pending", label: "Application recorded" };
  }
  return { status: entry.status || "posted", label: undefined };
}

function formatDate(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Date unavailable" : parsed.toLocaleDateString("en-KE");
}

function buildParams(filters, page) {
  const params = { page };
  if (filters.type) params.type = filters.type;
  if (filters.from) params.from = filters.from;
  if (filters.to) params.to = filters.to;
  if (filters.search.trim()) params.search = filters.search.trim();
  return params;
}

export default function Transactions() {
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [downloading, setDownloading] = useState("");
  const [downloadError, setDownloadError] = useState("");

  const loadTransactions = useCallback(async (nextPage = 1, selected = emptyFilters) => {
    setState("loading");
    setError("");
    try {
      const response = await api.get("transactions/", { params: buildParams(selected, nextPage) });
      const payload = response.data;
      const results = Array.isArray(payload) ? payload : payload?.results;
      if (!Array.isArray(results)) throw new Error("The transaction service returned an unexpected response.");
      setData({
        results,
        count: Number.isInteger(payload?.count) ? payload.count : results.length,
        next: payload?.next || null,
        previous: payload?.previous || null,
        summary: payload?.summary || null,
      });
      setPage(nextPage);
      setState(results.length ? "ready" : "empty");
    } catch (requestError) {
      setData(null);
      setError(requestError.response?.data?.detail || requestError.response?.data?.error || requestError.message || "Transaction history could not be loaded.");
      setState("error");
    }
  }, []);

  useEffect(() => { loadTransactions(1, emptyFilters); }, [loadTransactions]);

  const applyFilters = (event) => {
    event.preventDefault();
    const selected = { ...filters };
    setAppliedFilters(selected);
    loadTransactions(1, selected);
  };

  const clearFilters = () => {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    loadTransactions(1, emptyFilters);
  };

  const exportReport = async (format) => {
    setDownloadError("");
    setDownloading(format);
    const endpoint = format === "pdf" ? "statement/pdf/" : "transactions/excel/";
    try {
      const response = await api.get(endpoint, {
        responseType: "blob",
        params: {
          ...(appliedFilters.from ? { from: appliedFilters.from } : {}),
          ...(appliedFilters.to ? { to: appliedFilters.to } : {}),
        },
      });
      await downloadStatement(response, {
        format: format === "pdf" ? "pdf" : "xlsx",
        fallbackFilename: format === "pdf" ? "member-statement.pdf" : "member-statement.xlsx",
      });
    } catch (downloadRequestError) {
      setDownloadError(await downloadFailureMessage(downloadRequestError, "The statement could not be downloaded. Please retry."));
    } finally {
      setDownloading("");
    }
  };

  return (
    <Layout>
      {() => (
        <div className="member-financial-page">
          <PageHeading
            eyebrow="Account activity"
            title="Transactions and statements"
            description="Review your account entries and download a date-filtered statement."
            actions={<Button variant="secondary" onClick={() => loadTransactions(page, appliedFilters)} loading={state === "loading"}>Refresh</Button>}
          />

          <section className="member-panel" aria-label="Transaction filters">
            <div className="member-panel-heading">
              <div><p className="ui-eyebrow">Find an entry</p><h2>Filter transaction history</h2></div>
            </div>
            <form className="member-filter-grid" onSubmit={applyFilters}>
              <FormField label="Type" htmlFor="transaction-type">
                <select id="transaction-type" value={filters.type} onChange={(event) => setFilters((current) => ({ ...current, type: event.target.value }))}>
                  <option value="">All activity</option><option value="deposit">Deposits</option><option value="withdrawal">Withdrawals</option><option value="loan">Loan applications</option><option value="repayment">Repayments</option><option value="dividend">Dividends</option>
                </select>
              </FormField>
              <FormField label="From date" htmlFor="transaction-from">
                <input id="transaction-from" type="date" value={filters.from} onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))} />
              </FormField>
              <FormField label="To date" htmlFor="transaction-to">
                <input id="transaction-to" type="date" value={filters.to} onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))} />
              </FormField>
              <FormField label="Search" htmlFor="transaction-search">
                <input id="transaction-search" value={filters.search} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} placeholder="Description, type or amount" />
              </FormField>
              <div className="member-filter-actions">
                <Button type="submit" variant="primary">Apply filters</Button>
                <Button type="button" variant="secondary" onClick={clearFilters}>Clear</Button>
              </div>
            </form>
          </section>

          <section className="member-panel" aria-label="Financial record">
            <div className="member-panel-heading">
              <div><p className="ui-eyebrow">Financial record</p><h2>Transaction history</h2></div>
              <span className="ui-muted">{state === "loading" ? "Loading entries" : `${data?.count ?? 0} entries`}</span>
            </div>

            {state === "loading" && <LoadingState label="Loading transaction history…" />}
            {state === "error" && <FeedbackMessage tone="danger" title="Transaction history could not be loaded">{error}<div className="member-inline-action"><Button variant="secondary" onClick={() => loadTransactions(page, appliedFilters)}>Retry</Button></div></FeedbackMessage>}
            {state === "empty" && <FeedbackMessage tone="info" title="No transactions found">Try a different date range or clear your filters.</FeedbackMessage>}
            {state === "ready" && (
              <DataTable label="Transaction history table">
                <table className="ui-data-table member-transactions-table">
                  <thead><tr><th scope="col">Date</th><th scope="col">Activity</th><th scope="col">Description</th><th scope="col">Status</th><th scope="col">Amount</th><th scope="col">Details</th></tr></thead>
                  <tbody>
                    {data.results.map((entry) => {
                      const rowStatus = formatStatus(entry);
                      const isExpanded = expandedId === entry.id;
                      const debit = ["withdrawal", "repayment"].includes(entry.type);
                      return <React.Fragment key={entry.id}>
                        <tr>
                          <td>{formatDate(entry.created_at)}</td>
                          <td>{entry.type === "loan" && /application/i.test(entry.note || "") ? "Loan application" : String(entry.type || "Activity").replaceAll("_", " ")}</td>
                          <td>{entry.note || "No description recorded"}</td>
                          <td><StatusBadge status={rowStatus.status} label={rowStatus.label} /></td>
                          <td><span className="ui-money">{debit ? "− " : entry.type === "deposit" ? "+ " : ""}{money(entry.amount)}</span></td>
                          <td><Button size="sm" variant="secondary" aria-expanded={isExpanded} onClick={() => setExpandedId(isExpanded ? null : entry.id)}>{isExpanded ? "Hide details" : "Details"}</Button></td>
                        </tr>
                        {isExpanded && <tr className="member-transaction-details"><td colSpan="6">
                          <h3>Transaction details</h3>
                          <p><strong>Reference:</strong> {entry.reference || `Ledger entry ${entry.id}`}</p>
                          {entry.type === "withdrawal" && <>
                            <p><strong>Destination:</strong> {entry.withdrawal_destination || "Not recorded on this entry"}</p>
                            <p><strong>Provider reference:</strong> {entry.provider_reference || entry.withdrawal_reference || "Not recorded on this entry"}</p>
                            {entry.withdrawal_status === "needs_review" && <p>Contact the SACCO and provide this ledger reference so staff can review the payout.</p>}
                          </>}
                          {entry.payment_history?.length > 0 && <div><strong>Payment history</strong><ul>{entry.payment_history.map((payment) => <li key={payment.id}>{payment.status}: {money(payment.amount)}{payment.receipt ? ` · receipt ${payment.receipt}` : ""}</li>)}</ul></div>}
                          {entry.type === "loan" && /application/i.test(entry.note || "") && <p>This records the loan application. It does not confirm a disbursement.</p>}
                        </td></tr>}
                      </React.Fragment>;
                    })}
                  </tbody>
                </table>
              </DataTable>
            )}

            {data?.summary && <div className="member-activity-summary" role="region" aria-label="Account activity totals">
              <strong>Activity totals</strong>
              <span>Deposits recorded: {money(data.summary.deposits)}</span>
              <span>Repayments recorded: {money(data.summary.repayments)}</span>
              <span>Loan applications: {money(data.summary.loans)} (not confirmed disbursements)</span>
            </div>}

            {state === "ready" && (data.previous || data.next) && <nav className="member-pagination" aria-label="Transaction pages">
              <Button variant="secondary" disabled={!data.previous || state === "loading"} onClick={() => loadTransactions(Math.max(1, page - 1), appliedFilters)}>Previous</Button>
              <span>Page {page}</span>
              <Button variant="secondary" disabled={!data.next || state === "loading"} onClick={() => loadTransactions(page + 1, appliedFilters)}>Next</Button>
            </nav>}

            <div className="member-download-row">
              <div><strong>Download statement</strong><p className="ui-muted">Uses your account only. Selected dates are applied when provided.</p></div>
              <div className="member-download-actions">
                <Button variant="secondary" loading={downloading === "pdf"} disabled={Boolean(downloading)} onClick={() => exportReport("pdf")}>PDF statement</Button>
                <Button variant="secondary" loading={downloading === "excel"} disabled={Boolean(downloading)} onClick={() => exportReport("excel")}>Excel statement</Button>
              </div>
            </div>
            {downloadError && <FeedbackMessage tone="danger" title="Statement download failed">{downloadError}</FeedbackMessage>}
          </section>
        </div>
      )}
    </Layout>
  );
}
