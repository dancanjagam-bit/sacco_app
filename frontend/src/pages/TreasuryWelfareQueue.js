import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import ConfirmModal from "../components/ConfirmModal";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import MetricCard from "../components/ui/MetricCard";
import "../styles/welfare.css";

const PAYOUT_STATUS_LABELS = {
  awaiting_provider: "Awaiting provider",
  pending: "Pending confirmation",
  confirmed: "Confirmed",
  failed: "Failed",
  uncertain: "Needs review",
  needs_review: "Needs review",
  sending: "Sending",
  reversed: "Reversed",
};

function kes(value) {
  if (value == null) return "—";
  return `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dateStr(v) {
  return v ? new Date(v).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Nairobi" }) : "—";
}

export default function TreasuryWelfareQueue() {
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const res = await api.get("welfare/treasurer-queue/");
      setData(res.data);
      setState("ready");
    } catch (err) {
      setState("error");
      setError(err.response?.data?.detail || "Welfare payout queue could not be loaded.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const payouts = data?.payouts || [];

  async function updatePayout(row, action) {
    setActionError("");
    setNotice("");
    setBusy(`${row.id}:${action}`);
    try {
      const { data: result } = await api.post(`welfare/requests/${row.id}/payout/${action}/`, {});
      if (result.status === "failed") {
        setActionError("The payout failed. Review the provider response before retrying.");
      } else {
        const status = PAYOUT_STATUS_LABELS[result.status] || "Status unavailable";
        setNotice(`Payout status: ${status}.`);
      }
      setSelected(null);
      await load();
    } catch (requestError) {
      setSelected(null);
      setActionError(requestError.response?.data?.detail || "The payout action could not be completed. Refresh the status before trying again.");
      await load();
    } finally {
      setBusy("");
    }
  }

  return (
    <Layout>
      <main className="welfare-page">
        <PageHeading
          eyebrow="Treasury workspace"
          title="Welfare payout queue"
          description="Send approved welfare payouts to members’ registered M-Pesa numbers and check the provider response."
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" size={15} /> Refresh</Button>}
        />

        {state === "loading" && <LoadingState label="Loading welfare payout queue…" />}
        {state === "error" && (
          <FeedbackMessage tone="danger" title="Queue unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>
        )}
        {actionError && <FeedbackMessage tone="danger" title="Payout action needs attention">{actionError}</FeedbackMessage>}
        {notice && <FeedbackMessage tone="success">{notice}</FeedbackMessage>}

        {state === "ready" && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--space-3)" }}>
              <MetricCard
                label="Payouts in queue"
                value={payouts.length}
                icon="heart"
              />
              <MetricCard
                label="Total pending amount"
                value={kes(data?.total_pending_amount)}
                icon="wallet"
                helper="Sum of approved amounts"
              />
            </div>

            <section className="ui-panel" aria-labelledby="welfare-queue-title">
              <div className="ui-panel-header">
                <div>
                  <p className="ui-eyebrow">Treasury</p>
                  <h2 className="ui-panel-title" id="welfare-queue-title">Approved welfare payouts</h2>
                </div>
                <Icon name="heart" />
              </div>
              <div className="ui-panel-body">
                {data.provider_available === false && <FeedbackMessage tone="warning" title="Payout provider is unavailable">M-Pesa payout actions require a configured provider.</FeedbackMessage>}
                {payouts.length === 0 ? (
                  <div className="ui-empty">
                    <strong>No approved welfare payouts.</strong>
                  </div>
                ) : (
                  <div style={{ display: "grid", gap: "var(--space-3)" }}>
                    {payouts.map((row) => (
                      <article
                        key={row.id}
                        style={{
                          display: "grid",
                          gap: "var(--space-2)",
                          padding: "var(--space-3)",
                          background: "var(--surface)",
                          borderRadius: "var(--radius-card)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        <div>
                          <strong>{row.member_name}</strong>
                          <span style={{ marginLeft: 8, fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                            {row.member_number}
                          </span>
                          <div style={{ marginTop: "var(--space-1)", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                            Category: {row.category} · Approved: {kes(row.approved_amount)}
                          </div>
                          <div style={{ marginTop: "var(--space-1)", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                            Submitted: {dateStr(row.created_at)}
                            {row.decided_at && ` · Approved: ${dateStr(row.decided_at)}`}
                          </div>
                          {row.payout_reference && (
                            <div style={{ marginTop: "var(--space-1)", fontSize: "var(--text-sm)" }}>
                              Payout reference: <code>{row.payout_reference}</code>
                            </div>
                          )}
                        </div>
                        <div className="welfare-treasury-actions">
                          <StatusBadge status={row.payout_status} label={PAYOUT_STATUS_LABELS[row.payout_status] || row.payout_status} />
                          {row.can_start_payout && <Button disabled={Boolean(busy)} onClick={() => setSelected(row)}>Send M-Pesa payout</Button>}
                          {row.can_refresh_payout && <Button variant="secondary" loading={busy === `${row.id}:status`} disabled={Boolean(busy)} onClick={() => updatePayout(row, "status")}>Check payout status</Button>}
                        </div>
                        {row.payout_error && <p>{row.payout_error}</p>}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </section>
            {data.can_attribute && <ContributionAttribution />}
          </>
        )}
        {selected && <ConfirmModal title="Send approved welfare payout?"
          message={`Send ${kes(selected.approved_amount)} to ${selected.member_name} at their registered M-Pesa number.`}
          confirmLabel="Send payout" loading={Boolean(busy)}
          onCancel={() => setSelected(null)} onConfirm={() => updatePayout(selected, "start")} />}
      </main>
    </Layout>
  );
}

function ContributionAttribution() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [member, setMember] = useState("");
  const [credit, setCredit] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  async function search(event) {
    event.preventDefault();
    setBusy("search");
    setResults(null);
    setNotice("");
    setError("");
    setMember("");
    setCredit("");
    try {
      const { data } = await api.get(`welfare/contributions/attribution/?q=${encodeURIComponent(query.trim())}`);
      setResults(data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Attribution records could not be loaded.");
    } finally {
      setBusy("");
    }
  }

  async function attribute(event) {
    event.preventDefault();
    setBusy("attribute");
    setNotice("");
    setError("");
    try {
      await api.post("welfare/contributions/attribute/", {
        member: Number(member), journal_line: Number(credit), reason: reason.trim(),
      });
      setNotice("Posted contribution linked to the member.");
      setResults((current) => ({ ...current, credits: current.credits.filter((entry) => String(entry.id) !== credit) }));
      setCredit("");
      setReason("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The posted contribution could not be linked.");
    } finally {
      setBusy("");
    }
  }

  return <section className="ui-panel" aria-labelledby="welfare-attribution-title">
    <div className="ui-panel-header"><h2 className="ui-panel-title" id="welfare-attribution-title">Link posted contributions to members</h2></div>
    <div className="ui-panel-body welfare-attribution-form">
      {error && <FeedbackMessage tone="danger">{error}</FeedbackMessage>}
      {notice && <FeedbackMessage tone="success">{notice}</FeedbackMessage>}
      <form className="welfare-attribution-form" onSubmit={search}>
        <FormField label="Member name or number" htmlFor="welfare-attribution-search">
          <input className="ui-input" id="welfare-attribution-search" type="search" maxLength="120" value={query} onChange={(event) => setQuery(event.target.value)} />
        </FormField>
        <Button type="submit" variant="secondary" loading={busy === "search"} disabled={Boolean(busy)}>Find attribution records</Button>
      </form>
      {results && <form className="welfare-attribution-form" onSubmit={attribute}>
        <FormField label="Member" htmlFor="welfare-attribution-member">
          <select className="ui-select" id="welfare-attribution-member" value={member} required onChange={(event) => setMember(event.target.value)}>
            <option value="">{results.members.length ? "Choose member" : "No matching members"}</option>
            {results.members.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {entry.member_number}</option>)}
          </select>
        </FormField>
        <FormField label="Posted welfare credit" htmlFor="welfare-attribution-credit">
          <select className="ui-select" id="welfare-attribution-credit" value={credit} required onChange={(event) => setCredit(event.target.value)}>
            <option value="">{results.credits.length ? "Choose posted credit" : "No unlinked welfare credits"}</option>
            {results.credits.map((entry) => <option key={entry.id} value={entry.id}>{entry.source_reference} · {kes(entry.amount)} · {dateStr(entry.posted_at)} · #{entry.id}</option>)}
          </select>
        </FormField>
        <FormField label="Reason for linking the contribution" htmlFor="welfare-attribution-reason">
          <textarea className="ui-textarea" id="welfare-attribution-reason" rows="2" maxLength="500" required value={reason} onChange={(event) => setReason(event.target.value)} />
        </FormField>
        <Button type="submit" loading={busy === "attribute"} disabled={!member || !credit || !reason.trim() || Boolean(busy)}>Link posted contribution</Button>
      </form>}
    </div>
  </section>;
}
