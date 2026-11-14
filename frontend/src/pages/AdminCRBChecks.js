import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";

const TABS = ["all", "flagged", "clear", "error", "pending", "needs_review", "disputed"];
const value = (item) => item === null || item === undefined || item === "" ? "Not supplied" : item;

export default function AdminCRBChecks() {
  const [records, setRecords] = useState([]);
  const [tab, setTab] = useState("all");
  const [selected, setSelected] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("admin/crb-checks/", { params: tab === "all" ? {} : { status: tab } });
      if (!Array.isArray(response.data)) throw new Error("Unexpected credit report response.");
      setRecords(response.data); setState("ready");
    } catch (requestError) {
      setRecords([]); setState("error");
      setError(requestError.response?.data?.detail || "Assigned credit reports could not be loaded.");
    }
  }, [tab]);
  useEffect(() => { load(); }, [load]);

  async function showDetail(id) {
    setDetailLoading(true); setError("");
    try {
      const response = await api.get(`admin/crb-checks/${id}/`);
      setSelected(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "This report is not available to your assignment.");
    } finally { setDetailLoading(false); }
  }

  return <Layout><main className="staff-workspace-page">
    <PageHeading eyebrow="Assigned credit reviews" title="Credit bureau reports" description="Provider data is shown only for loans assigned to your appraisal role. A report status or score does not decide a loan." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>} />
    {error && state !== "error" && <FeedbackMessage tone="danger" title="Credit report action needs attention">{error}</FeedbackMessage>}
    <div className="staff-access-tabs" role="group" aria-label="Filter credit reports">{TABS.map((item) => <Button key={item} variant={item === tab ? "primary" : "secondary"} size="sm" aria-pressed={item === tab} onClick={() => setTab(item)}>{item.replaceAll("_", " ")}</Button>)}</div>
    {state === "loading" && <LoadingState label="Loading assigned credit reports…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Credit reports unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {state === "ready" && records.length === 0 && <div className="ui-empty"><strong>No credit reports in this review scope.</strong>Reports for other officers’ assignments are not shown.</div>}
    {state === "ready" && records.length > 0 && <section className="ui-panel"><div className="ui-table-wrap"><table className="ui-table"><thead><tr><th>Member</th><th>Loan</th><th>Provider</th><th>Score</th><th>Report date</th><th>Status</th><th>Details</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td>{record.member_name || record.member_username}</td><td>KES {Number(record.loan_amount).toLocaleString("en-KE", { minimumFractionDigits: 2 })}</td><td>{record.provider || "Not supplied"}</td><td>{value(record.score)}</td><td>{record.checked_at ? new Date(record.checked_at).toLocaleDateString("en-KE") : "Not recorded"}</td><td><StatusBadge status={record.status} label={record.status.replaceAll("_", " ")} /></td><td><Button size="sm" variant="secondary" onClick={() => showDetail(record.id)}>Review details</Button></td></tr>)}</tbody></table></div></section>}
    {detailLoading && <LoadingState label="Loading report details…" />}
    {selected && <section className="ui-panel staff-workspace-actions" aria-labelledby="credit-report-detail-title">
      <div className="ui-panel-header"><div><p className="ui-eyebrow">Assigned loan #{selected.loan_id}</p><h2 className="ui-panel-title" id="credit-report-detail-title">Report review details</h2></div><Button variant="ghost" onClick={() => setSelected(null)} aria-label="Close report details"><Icon name="close" /></Button></div>
      <dl className="staff-credit-report-facts"><div><dt>Member</dt><dd>{selected.member_name || selected.member_username}</dd></div><div><dt>Loan status</dt><dd>{selected.loan_status}</dd></div><div><dt>Credit score</dt><dd>{value(selected.score)}</dd></div><div><dt>External loans reported</dt><dd>{value(selected.active_loans_count)}</dd></div><div><dt>Provider reference</dt><dd>{value(selected.request_reference)}</dd></div><div><dt>Report date / expiry</dt><dd>{value(selected.report_date)} / {value(selected.expires_at && new Date(selected.expires_at).toLocaleDateString("en-KE"))}</dd></div></dl>
      <h3>External obligations supplied</h3><pre className="staff-credit-report-json">{selected.external_obligations == null ? "Not supplied" : JSON.stringify(selected.external_obligations, null, 2)}</pre>
      <h3>Repayment/default information supplied</h3><pre className="staff-credit-report-json">{selected.repayment_default_information == null ? "Not supplied" : JSON.stringify(selected.repayment_default_information, null, 2)}</pre>
      {Array.isArray(selected.missing_data) && selected.missing_data.length > 0 && <p>Missing data: {selected.missing_data.join(", ")}</p>}
      {selected.coverage_limitations && <p>Provider coverage: {selected.coverage_limitations}</p>}
      <FeedbackMessage tone="info" title="Report review does not approve a loan">Loan decisions must use a separately assigned decision workflow. An absent score or debt figure is unknown, not zero.</FeedbackMessage>
    </section>}
  </main></Layout>;
}
