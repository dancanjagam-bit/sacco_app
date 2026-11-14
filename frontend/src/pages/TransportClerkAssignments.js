import React, { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import TransportAssignmentHistory from "../components/TransportAssignmentHistory";
import Icon from "../components/ui/Icon";
import "../styles/transport.css";

const toArray = (value) => Array.isArray(value) ? value : value?.results || [];
const empty = { vehicle: "", route: "", driver: "", conductor: "", starts_at: "", ends_at: "" };

export default function TransportClerkAssignments() {
  const [data, setData] = useState({ users: [], vehicles: [], routes: [], assignments: [] });
  const [form, setForm] = useState(empty);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const [users, vehicles, routes, assignments] = await Promise.all([
        api.get("transport/staff/users/"), api.get("transport/vehicles/"),
        api.get("transport/routes/"), api.get("transport/assignments/"),
      ]);
      setData({ users: toArray(users.data), vehicles: toArray(vehicles.data), routes: toArray(routes.data), assignments: toArray(assignments.data) });
      setState("ready");
    } catch (requestError) {
      setState("error");
      setError(requestError.response?.data?.detail || "Assigned transport work could not be loaded.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const drivers = useMemo(() => data.users.filter((user) => user.transport_roles?.includes("driver")), [data.users]);
  const conductors = useMemo(() => data.users.filter((user) => user.transport_roles?.includes("conductor")), [data.users]);
  const options = (users) => users.map((user) => <option key={user.id} value={user.id}>{user.name || user.username}</option>);

  async function submit(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      await api.post("transport/assignments/", form);
      setNotice("Assignment saved. Its vehicle, route, crew, and effective dates are preserved in history.");
      setForm(empty); await load();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.response?.data?.error || "The assignment could not be saved.");
    } finally { setSaving(false); }
  }

  const assignmentEnded = (ended) => {
    setData((current) => ({ ...current, assignments: current.assignments.map((item) => item.id === ended.id ? ended : item) }));
    setNotice(`Assignment ended for ${ended.vehicle_registration}.`);
  };

  return <Layout><main className="transport-operations-page">
    <PageHeading eyebrow="Assigned clerk duties" title="Transport assignments" description="Create and review assignments only for vehicles in your current clerk scope." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" /> Refresh</Button>} />
    {error && state !== "error" && <FeedbackMessage tone="danger" title="Assignment needs attention">{error}</FeedbackMessage>}
    {notice && <FeedbackMessage tone="success" title="Assignment saved">{notice}</FeedbackMessage>}
    {state === "loading" && <LoadingState label="Loading assigned transport scopes…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Assigned scope unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {state === "ready" && <>
      <section className="ui-panel transport-management-panel">
        <div className="ui-panel-header"><div><p className="ui-eyebrow">Crew scheduling</p><h2 className="ui-panel-title">Create an effective-dated assignment</h2></div><Icon name="users" /></div>
        <form className="ui-panel-body transport-form" onSubmit={submit}>
          <FormField label="Assigned vehicle" htmlFor="clerk-assignment-vehicle"><select className="ui-select" id="clerk-assignment-vehicle" value={form.vehicle} onChange={(event) => setForm({ ...form, vehicle: event.target.value })} required><option value="">Choose vehicle</option>{data.vehicles.map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.registration}</option>)}</select></FormField>
          <FormField label="Route" htmlFor="clerk-assignment-route"><select className="ui-select" id="clerk-assignment-route" value={form.route} onChange={(event) => setForm({ ...form, route: event.target.value })} required><option value="">Choose route</option>{data.routes.map((route) => <option key={route.id} value={route.id}>{route.name}</option>)}</select></FormField>
          <FormField label="Driver" htmlFor="clerk-assignment-driver"><select className="ui-select" id="clerk-assignment-driver" value={form.driver} onChange={(event) => setForm({ ...form, driver: event.target.value })} required><option value="">Choose driver</option>{options(drivers)}</select></FormField>
          <FormField label="Conductor (optional)" htmlFor="clerk-assignment-conductor"><select className="ui-select" id="clerk-assignment-conductor" value={form.conductor} onChange={(event) => setForm({ ...form, conductor: event.target.value })}><option value="">No conductor</option>{options(conductors)}</select></FormField>
          <FormField label="Starts at (Nairobi time)" htmlFor="clerk-assignment-start"><input className="ui-input" id="clerk-assignment-start" type="datetime-local" value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} required /></FormField>
          <FormField label="Ends at (Nairobi time)" htmlFor="clerk-assignment-end"><input className="ui-input" id="clerk-assignment-end" type="datetime-local" min={form.starts_at || undefined} value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} required /></FormField>
          {data.vehicles.length === 0 && <FeedbackMessage tone="warning" title="No vehicle assigned">Ask a system administrator to assign a vehicle scope before scheduling crew.</FeedbackMessage>}
          <Button type="submit" loading={saving} disabled={!form.vehicle || !form.route || !form.driver || !form.starts_at || !form.ends_at}>Save assignment</Button>
        </form>
      </section>
      <TransportAssignmentHistory title="Assignments in your scope" assignments={data.assignments} onEnded={assignmentEnded} />
    </>}
  </main></Layout>;
}
