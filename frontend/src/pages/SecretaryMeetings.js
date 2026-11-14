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
const TYPES = [
  ["committee", "Committee Meeting"],
  ["agm", "Annual General Meeting (AGM)"],
  ["sgm", "Special General Meeting (SGM)"],
  ["board", "Board Meeting"],
  ["other", "Other"],
];
const STATUSES = [
  ["scheduled", "Scheduled"],
  ["completed", "Completed"],
  ["postponed", "Postponed"],
  ["cancelled", "Cancelled"],
];

function dateTime(v) {
  return v ? new Date(v).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export default function SecretaryMeetings() {
  const [meetings, setMeetings] = useState([]);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [form, setForm] = useState({ title: "", meeting_type: "committee", scheduled_at: "", location: "", agenda: "" });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [editing, setEditing] = useState(null); // { id, minutes, status, quorum_met }

  // Attendance state per meeting
  const [attendanceMeetingId, setAttendanceMeetingId] = useState(null);
  const [attendees, setAttendees] = useState([]);
  const [attendeeState, setAttendeeState] = useState("idle");
  const [attendeeError, setAttendeeError] = useState("");
  const [attendeeForm, setAttendeeForm] = useState({ name: "", role: "", present: true });
  const [attendeeSaving, setAttendeeSaving] = useState(false);
  const [attendeeFormError, setAttendeeFormError] = useState("");

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const res = await api.get("secretary/meetings/" + (filter !== "all" ? `?status=${filter}` : ""));
      if (!Array.isArray(res.data)) throw new Error("Unexpected response.");
      setMeetings(res.data); setState("ready");
    } catch (err) {
      setState("error"); setError(err.response?.data?.detail || "Meetings could not be loaded.");
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault(); setSaving(true); setFormError(""); setFormSuccess("");
    try {
      await api.post("secretary/meetings/", form);
      setFormSuccess("Meeting scheduled.");
      setForm({ title: "", meeting_type: "committee", scheduled_at: "", location: "", agenda: "" });
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Could not schedule the meeting.");
    } finally { setSaving(false); }
  }

  async function update(id, patch) {
    setSaving(true);
    try {
      await api.patch(`secretary/meetings/${id}/`, patch);
      setEditing(null);
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Update failed.");
    } finally { setSaving(false); }
  }

  async function loadAttendees(meetingId) {
    setAttendanceMeetingId(meetingId);
    setAttendeeState("loading");
    setAttendeeError("");
    setAttendees([]);
    try {
      const res = await api.get(`secretary/meetings/${meetingId}/attendees/`);
      setAttendees(Array.isArray(res.data) ? res.data : []);
      setAttendeeState("ready");
    } catch (err) {
      setAttendeeState("error");
      setAttendeeError(err.response?.data?.detail || "Attendance could not be loaded.");
    }
  }

  async function addAttendee(meetingId) {
    if (!attendeeForm.name.trim()) return;
    setAttendeeSaving(true);
    setAttendeeFormError("");
    try {
      const res = await api.post(`secretary/meetings/${meetingId}/attendees/`, attendeeForm);
      setAttendees((prev) => [...prev, res.data]);
      setAttendeeForm({ name: "", role: "", present: true });
    } catch (err) {
      setAttendeeFormError(err.response?.data?.detail || "Could not add attendee.");
    } finally {
      setAttendeeSaving(false);
    }
  }

  async function removeAttendee(meetingId, attendeeId) {
    try {
      await api.delete(`secretary/meetings/${meetingId}/attendees/${attendeeId}/`);
      setAttendees((prev) => prev.filter((a) => a.id !== attendeeId));
    } catch (err) {
      setAttendeeError(err.response?.data?.detail || "Could not remove attendee.");
    }
  }

  return (
    <Layout>
      <main style={{ display: "grid", gap: "var(--grid-gap)", maxWidth: "72rem", margin: "0 auto", width: "100%", minWidth: 0 }}>
        <PageHeading
          eyebrow="Secretary workspace"
          title="Meetings"
          description="Schedule and record cooperative meetings. Minutes and quorum are recorded after the meeting."
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" size={15} /> Refresh</Button>}
        />

        {/* ── Schedule new meeting ── */}
        <section className="ui-panel" aria-labelledby="new-meeting-title">
          <div className="ui-panel-header"><div><p className="ui-eyebrow">Secretary</p><h2 className="ui-panel-title" id="new-meeting-title">Schedule a meeting</h2></div><Icon name="file" /></div>
          <form className="ui-panel-body" style={{ display: "grid", gap: "var(--space-4)", maxWidth: "640px" }} onSubmit={create}>
            {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
            {formSuccess && <FeedbackMessage tone="success">{formSuccess}</FeedbackMessage>}
            <FormField label="Meeting title" htmlFor="mtg-title"><input id="mtg-title" className="ui-input" required maxLength="200" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></FormField>
            <FormField label="Meeting type" htmlFor="mtg-type"><select id="mtg-type" className="ui-select" value={form.meeting_type} onChange={(e) => setForm({ ...form, meeting_type: e.target.value })}>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></FormField>
            <FormField label="Date and time" htmlFor="mtg-date"><input id="mtg-date" className="ui-input" type="datetime-local" required value={form.scheduled_at} onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })} /></FormField>
            <FormField label="Location (optional)" htmlFor="mtg-loc"><input id="mtg-loc" className="ui-input" maxLength="300" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></FormField>
            <FormField label="Agenda (optional)" htmlFor="mtg-agenda"><textarea id="mtg-agenda" className="ui-textarea" rows="4" maxLength="2000" value={form.agenda} onChange={(e) => setForm({ ...form, agenda: e.target.value })} /></FormField>
            <Button type="submit" loading={saving}><Icon name="plus" size={15} /> Schedule meeting</Button>
          </form>
        </section>

        {/* ── Filter ── */}
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          {[["all", "All"], ...STATUSES].map(([v, l]) => (
            <button key={v} className={`ui-filter-pill${filter === v ? " is-active" : ""}`} onClick={() => setFilter(v)}>{l}</button>
          ))}
        </div>

        {state === "loading" && <LoadingState label="Loading meetings…" />}
        {state === "error" && <FeedbackMessage tone="danger" title="Meetings unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
        {state === "ready" && meetings.length === 0 && <div className="ui-empty"><strong>No meetings found.</strong><span>Schedule one above.</span></div>}

        {state === "ready" && meetings.map((m) => (
          <article className="ui-panel" key={m.id}>
            <div className="ui-panel-header">
              <div>
                <p className="ui-eyebrow">{m.meeting_type_display}</p>
                <h2 className="ui-panel-title">{m.title}</h2>
                <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
                  {dateTime(m.scheduled_at)}{m.location ? ` · ${m.location}` : ""}
                </p>
              </div>
              <StatusBadge status={m.status} label={m.status_display} />
            </div>
            <div className="ui-panel-body" style={{ display: "grid", gap: "var(--space-3)" }}>
              {m.agenda && <div><p style={{ margin: "0 0 4px", fontWeight: 600, fontSize: "var(--text-sm)" }}>Agenda</p><p style={{ margin: 0, color: "var(--text-muted)", whiteSpace: "pre-wrap" }}>{m.agenda}</p></div>}
              {m.minutes && <div><p style={{ margin: "0 0 4px", fontWeight: 600, fontSize: "var(--text-sm)" }}>Minutes</p><p style={{ margin: 0, color: "var(--text-muted)", whiteSpace: "pre-wrap" }}>{m.minutes}</p></div>}
              {m.quorum_met != null && <p style={{ margin: 0, fontSize: "var(--text-sm)" }}>Quorum: <strong>{m.quorum_met ? "Met" : "Not met"}</strong></p>}

              {editing?.id === m.id ? (
                <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "520px" }}>
                  <FormField label="Status" htmlFor={`status-${m.id}`}>
                    <select id={`status-${m.id}`} className="ui-select" value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })}>
                      {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </FormField>
                  <FormField label="Quorum met?" htmlFor={`quorum-${m.id}`}>
                    <select id={`quorum-${m.id}`} className="ui-select" value={editing.quorum_met ?? ""} onChange={(e) => setEditing({ ...editing, quorum_met: e.target.value === "" ? null : e.target.value === "true" })}>
                      <option value="">Not recorded</option>
                      <option value="true">Yes — quorum met</option>
                      <option value="false">No — quorum not met</option>
                    </select>
                  </FormField>
                  <FormField label="Minutes" htmlFor={`minutes-${m.id}`}>
                    <textarea id={`minutes-${m.id}`} className="ui-textarea" rows="5" maxLength="10000" value={editing.minutes} onChange={(e) => setEditing({ ...editing, minutes: e.target.value })} />
                  </FormField>
                  {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
                  <div style={{ display: "flex", gap: "var(--space-2)" }}>
                    <Button loading={saving} onClick={() => update(m.id, { status: editing.status, minutes: editing.minutes, quorum_met: editing.quorum_met })}>Save changes</Button>
                    <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <div>
                  <Button variant="secondary" size="sm" onClick={() => { setFormError(""); setEditing({ id: m.id, status: m.status, minutes: m.minutes || "", quorum_met: m.quorum_met }); }}>
                    <Icon name="settings" size={14} /> Update record
                  </Button>
                </div>
              )}

              {/* ── Attendance ── */}
              {attendanceMeetingId === m.id ? (
                <div style={{ marginTop: "var(--space-4)", borderTop: "1px solid var(--border)", paddingTop: "var(--space-3)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
                    <strong style={{ fontSize: "var(--text-sm)" }}>Attendance ({m.attendee_count ?? attendees.length})</strong>
                    <Button variant="secondary" size="sm" onClick={() => setAttendanceMeetingId(null)}>Close</Button>
                  </div>
                  {attendeeState === "loading" && <LoadingState label="Loading attendees…" />}
                  {attendeeState === "error" && <FeedbackMessage tone="danger">{attendeeError}</FeedbackMessage>}
                  {attendeeState === "ready" && (
                    <>
                      {attendees.length === 0 ? (
                        <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>No attendees recorded yet.</p>
                      ) : (
                        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 var(--space-3)", display: "grid", gap: "var(--space-2)" }}>
                          {attendees.map((a) => (
                            <li key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "var(--text-sm)", gap: "var(--space-2)" }}>
                              <span>
                                <strong>{a.name}</strong>
                                {a.role && <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>{a.role}</span>}
                                {!a.present && <span style={{ color: "var(--color-danger, #dc2626)", marginLeft: 6 }}>Absent</span>}
                              </span>
                              <Button variant="secondary" size="sm" onClick={() => removeAttendee(m.id, a.id)}>Remove</Button>
                            </li>
                          ))}
                        </ul>
                      )}
                      <div style={{ display: "grid", gap: "var(--space-2)", maxWidth: 420 }}>
                        <FormField label="Name" htmlFor={`att-name-${m.id}`}>
                          <input id={`att-name-${m.id}`} className="ui-input" maxLength="150" value={attendeeForm.name} onChange={(e) => setAttendeeForm({ ...attendeeForm, name: e.target.value })} placeholder="Full name" />
                        </FormField>
                        <FormField label="Role (optional)" htmlFor={`att-role-${m.id}`}>
                          <input id={`att-role-${m.id}`} className="ui-input" maxLength="100" value={attendeeForm.role} onChange={(e) => setAttendeeForm({ ...attendeeForm, role: e.target.value })} placeholder="e.g. Director, Member" />
                        </FormField>
                        <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--text-sm)", cursor: "pointer" }}>
                          <input type="checkbox" checked={attendeeForm.present} onChange={(e) => setAttendeeForm({ ...attendeeForm, present: e.target.checked })} />
                          Present
                        </label>
                        {attendeeFormError && <FeedbackMessage tone="danger">{attendeeFormError}</FeedbackMessage>}
                        <Button size="sm" loading={attendeeSaving} onClick={() => addAttendee(m.id)} disabled={!attendeeForm.name.trim()}>
                          <Icon name="plus" size={14} /> Add attendee
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div style={{ marginTop: "var(--space-2)" }}>
                  <Button variant="secondary" size="sm" onClick={() => loadAttendees(m.id)}>
                    <Icon name="users" size={14} /> Attendance {m.attendee_count != null ? `(${m.attendee_count})` : ""}
                  </Button>
                </div>
              )}
            </div>
          </article>
        ))}
      </main>
    </Layout>
  );
}
