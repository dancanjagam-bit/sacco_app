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

export default function TransportClerkIssues() {
  const [items, setItems] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [reasons, setReasons] = useState({});
  const [saving, setSaving] = useState(null);
  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("transport/issues/");
      if (!Array.isArray(response.data)) throw new Error("Unexpected issue response.");
      setItems(response.data); setState("ready");
    } catch (requestError) {
      setState("error"); setError(requestError.response?.data?.detail || "Assigned transport issues could not be loaded.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  async function resolve(item) {
    const reason = String(reasons[item.id] || "").trim();
    if (reason.length < 10) { setError("Enter a resolution reason of at least 10 characters."); return; }
    setSaving(item.id); setError("");
    try { await api.post(`transport/issues/${item.id}/resolve/`, { reason }); await load(); }
    catch (requestError) { setError(requestError.response?.data?.detail || "The issue could not be resolved."); }
    finally { setSaving(null); }
  }
  return <Layout><main className="staff-workspace-page">
    <PageHeading eyebrow="Assigned clerk duties" title="Assignment issues" description="Review only operational issues assigned to your clerk account. Each resolution requires a reason." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>} />
    {error && <FeedbackMessage tone="danger" title="Issue action needs attention">{error}</FeedbackMessage>}
    {state === "loading" && <LoadingState label="Loading assigned transport issues…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Issue queue unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {state === "ready" && items.length === 0 && <div className="ui-empty"><strong>No issues are assigned to you.</strong>Other operational reports remain outside this account’s scope.</div>}
    {state === "ready" && items.map((item) => <article className="ui-panel transport-clerk-cash-card" key={item.id}>
      <div className="transport-clerk-cash-head"><div><p className="ui-eyebrow">Issue #{item.id}</p><h2>{item.vehicle || "Assignment not linked"}{item.route ? ` · ${item.route}` : ""}</h2></div><StatusBadge status={item.status} /></div>
      <p>{item.message}</p><p className="staff-access-muted">Reported by {item.reported_by} · {new Date(item.created_at).toLocaleString("en-KE")}</p>
      {item.status === "pending" ? <><FormField label="Resolution reason" htmlFor={`issue-reason-${item.id}`}><textarea id={`issue-reason-${item.id}`} className="ui-textarea" rows="3" maxLength="500" value={reasons[item.id] || ""} onChange={(event) => setReasons({ ...reasons, [item.id]: event.target.value })} /></FormField><Button loading={saving === item.id} disabled={(reasons[item.id] || "").trim().length < 10} onClick={() => resolve(item)}>Resolve issue</Button></> : <p>Resolution: {item.resolution_reason || "Reason not recorded"}</p>}
    </article>)}
  </main></Layout>;
}
