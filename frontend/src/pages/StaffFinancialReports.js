import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import LoadingState from "../components/ui/LoadingState";
import MetricCard from "../components/ui/MetricCard";
import PageHeading from "../components/ui/PageHeading";
import Button from "../components/ui/Button";

const kes = (value) => value == null ? "Unavailable" : `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function StaffFinancialReports() {
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("admin/reports/");
      if (!response.data?.members || !response.data?.savings || !response.data?.loans) throw new Error("Incomplete report response.");
      setData(response.data); setState("ready");
    } catch (requestError) {
      setData(null); setState("error");
      setError(requestError.response?.data?.detail || "Financial report is unavailable.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  return <Layout><main className="staff-workspace-page">
    <PageHeading eyebrow="Treasury workspace" title="Financial reports" description="Cooperative financial aggregates from recorded accounts and transactions. These reports are not a double-entry trial balance." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}>Refresh</Button>} />
    {state === "loading" && <LoadingState label="Loading financial reports…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Report unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {data && <>
      <section className="staff-workspace-metrics" aria-label="Cooperative member summary">
        <MetricCard label="Members" value={data.members.total} helper={`${data.members.active} active · ${data.members.suspended} suspended`} icon="users" />
        <MetricCard label="Recorded savings deposits" value={kes(data.savings.total_deposited)} helper="Positive savings entries" icon="wallet" />
        <MetricCard label="Recorded withdrawals" value={kes(data.savings.total_withdrawn)} helper="Negative savings entries" icon="receipt" />
        <MetricCard label="Net recorded savings" value={kes(data.savings.net_balance)} helper="Deposits less recorded withdrawals" icon="bank" />
        <MetricCard label="Outstanding approved loan balance" value={kes(data.loans.outstanding_balance)} helper="Current approved loan records" icon="file" />
        <MetricCard label="Recorded repayments" value={kes(data.loans.total_collected)} helper="Posted repayment transactions" icon="receipt" />
      </section>
      <FeedbackMessage tone="warning" title="Accounting scope">This report summarizes the existing ledger records. Balanced double-entry financial statements are not established in this application.</FeedbackMessage>
    </>}
  </main></Layout>;
}
