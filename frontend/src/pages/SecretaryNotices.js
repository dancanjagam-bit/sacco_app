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

function dateTime(v) {
  return v ? new Date(v).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export default function SecretaryNotices() {
  const [notices, setNotices] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [form, setForm] = useState({ title: "", body: "", priority: "normal", status: "draft" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const res = await api.get("secretary/notices/" + (filter !== "all" ? `?status=${filter}` : ""));
      if (!Array.isArray(res.data)) throw new Error("Unexpected response.");
      setNotices(res.data); setState("ready");
    } catch (err) {
      setState("error"); setError(err.response?.data?.detail || "Notices could not be loaded.");
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault(); setSaving(true); setFormError(""); setFormSuccess("");
    try {
      await api.post("secretary/notices/", form);
      setFormSuccess(form.status === "published" ? "Notice published." : "Notice saved as draft.");
      setForm({ title: "", body: "", priority: "normal", status: "draft" });
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Could not save the notice.");
    } finally { setSaving(false); }
  }

  async function patch(id, data) {
    setSaving(true); setFormError("");
    try {
      await api.patch(`secretary/notices/${id}/`, data);
      setEditing(null); await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Update failed.");
    } finally { setSaving(false); }
  }

  const statusColor = { draft: "neutral", published: "active", archived: "inactive" };

  return (
    <Layout>
      <main style={{ display: "grid", gap: "var(--grid-gap)", maxWidth: "72rem", margin: "0 auto", width: "100%", minWidth: 0 }}>
        <PageHeading
          eyebrow="Secretary workspace"
          title="Member notices"
          description="Draft and publish cooperative announcements to all active members."
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" size={15} /> Refresh</Button>}
        />

        {/* ── Create notice ── */}
        <section className="ui-panel" aria-labelledby="new-notice-title">
          <div className="ui-panel-header"><div><p className="ui-eyebrow">Secretary</p><h2 className="ui-panel-title" id="new-notice-title">New notice</h2></div><Icon name="bell" /></div>
          <form className="ui-panel-body" style={{ display: "grid", gap: "var(--space-4)", maxWidth: "640px" }} onSubmit={create}>
            {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
            {formSuccess && <FeedbackMessage tone="success">{formSuccess}</FeedbackMessage>}
            <FormField label="Title" htmlFor="notice-title"><input id="notice-title" className="ui-input" required maxLength="200" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></FormField>
            <FormField label="Body" htmlFor="notice-body"><textarea id="notice-body" className="ui-textarea" required rows="5" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></FormField>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
              <FormField label="Priority" htmlFor="notice-priority">
                <select id="notice-priority" className="ui-select" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                  <option value="normal">Normal</option>
                  <option value="urgent">Urgent</option>
                </select>
              </FormField>
              <FormField label="Save as" htmlFor="notice-status">
                <select id="notice-status" className="ui-select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="draft">Draft</option>
                  <option value="published">Published (visible to members)</option>
                </select>
              </FormField>
            </div>
            <Button type="submit" loading={saving}><Icon name="plus" size={15} /> Save notice</Button>
          </form>
        </section>

        {/* ── Filter ── */}
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          {[["all", "All"], ["draft", "Draft"], ["published", "Published"], ["archived", "Archived"]].map(([v, l]) => (
            <button key={v} className={`ui-filter-pill${filter === v ? " is-active" : ""}`} onClick={() => setFilter(v)}>{l}</button>
          ))}
        </div>

        {state === "loading" && <LoadingState label="Loading notices…" />}
        {state === "error" && <FeedbackMessage tone="danger" title="Notices unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
        {state === "ready" && notices.length === 0 && <div className="ui-empty"><strong>No notices found.</strong><span>Create one above.</span></div>}

        {state === "ready" && notices.map((n) => (
          <article className="ui-panel" key={n.id}>
            <div className="ui-panel-header">
              <div>
                <p className="ui-eyebrow">
                  {n.priority === "urgent" ? "🔴 Urgent notice" : "Notice"}
                  {n.published_at ? ` · Published ${dateTime(n.published_at)}` : ""}
                </p>
                <h2 className="ui-panel-title">{n.title}</h2>
              </div>
              <StatusBadge status={statusColor[n.status] || "neutral"} label={n.status} />
            </div>
            <div className="ui-panel-body" style={{ display: "grid", gap: "var(--space-3)" }}>
              {editing?.id === n.id ? (
                <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "520px" }}>
                  <FormField label="Body" htmlFor={`edit-body-${n.id}`}>
                    <textarea id={`edit-body-${n.id}`} className="ui-textarea" rows="5" value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
                  </FormField>
                  <FormField label="Status" htmlFor={`edit-status-${n.id}`}>
                    <select id={`edit-status-${n.id}`} className="ui-select" value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}>
                      <option value="draft">Draft</option>
                      <option value="published">Published</option>
                      <option value="archived">Archived</option>
                    </select>
                  </FormField>
                  {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
                  <div style={{ display: "flex", gap: "var(--space-2)" }}>
                    <Button loading={saving} onClick={() => patch(n.id, { body: editing.body, status: editing.status })}>Save</Button>
                    <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <>
                  <p style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--text)" }}>{n.body}</p>
                  <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
                    <Button variant="secondary" size="sm" onClick={() => { setFormError(""); setEditing({ id: n.id, body: n.body, status: n.status }); }}>Edit</Button>
                    {n.status === "draft" && <Button size="sm" onClick={() => patch(n.id, { status: "published" })}>Publish</Button>}
                    {n.status === "published" && <Button variant="secondary" size="sm" onClick={() => patch(n.id, { status: "archived" })}>Archive</Button>}
                  </div>
                </>
              )}
              <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                Created by {n.created_by} · {dateTime(n.created_at)}
              </p>
            </div>
          </article>
        ))}
      </main>
    </Layout>
  );
}
