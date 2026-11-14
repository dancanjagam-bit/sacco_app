import React, { useState } from "react";
import api from "../api/axios";
import Button from "./ui/Button";
import FeedbackMessage from "./ui/FeedbackMessage";
import FormField from "./ui/FormField";
import StatusBadge from "./ui/StatusBadge";

const nairobiTime = { timeZone: "Africa/Nairobi" };

export default function TransportAssignmentHistory({ title, assignments, onEnded }) {
  const [selectedId, setSelectedId] = useState(null);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function select(id) {
    setSelectedId(id);
    setReason("");
    setError("");
  }

  async function endAssignment(event) {
    event.preventDefault();
    if (saving || !reason.trim()) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(`transport/assignments/${selectedId}/end/`, { reason: reason.trim() });
      onEnded(data);
      select(null);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "The assignment could not be ended.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="ui-panel transport-management-history">
      <div className="ui-panel-header"><h2 className="ui-panel-title">{title}</h2></div>
      {assignments.length === 0 ? <div className="ui-empty">No assignments recorded.</div> : (
        <div className="transport-history-list">
          {assignments.map((item) => (
            <article className="transport-history-row" key={item.id}>
              <div>
                <strong>{item.vehicle_registration}</strong>
                <span>{item.route_name} · {item.driver_name} · {item.conductor_name || "No conductor"}</span>
                <small>
                  {new Date(item.starts_at).toLocaleString("en-KE", nairobiTime)}
                  {item.ends_at ? ` – ${new Date(item.ends_at).toLocaleString("en-KE", nairobiTime)}` : " · No end date"}
                </small>
              </div>
              <div className="transport-assignment-actions">
                <StatusBadge status={item.status} />
                {item.status === "active" && selectedId !== item.id && (
                  <Button variant="secondary" disabled={saving} onClick={() => select(item.id)}>End assignment</Button>
                )}
              </div>
              {selectedId === item.id && (
                <form className="transport-form transport-end-assignment" onSubmit={endAssignment}>
                  <FormField label="Reason for ending this assignment" htmlFor={`end-assignment-${item.id}`}>
                    <textarea
                      className="ui-textarea" id={`end-assignment-${item.id}`} rows="2" required maxLength="500"
                      disabled={saving} value={reason} onChange={(event) => setReason(event.target.value)}
                    />
                  </FormField>
                  {error && <FeedbackMessage tone="danger">{error}</FeedbackMessage>}
                  <div className="transport-crew-actions">
                    <Button type="submit" loading={saving} disabled={!reason.trim()}>Confirm end</Button>
                    <Button variant="secondary" disabled={saving} onClick={() => select(null)}>Cancel</Button>
                  </div>
                </form>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
