import React, { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import TransportAssignmentHistory from "../components/TransportAssignmentHistory";
import { useAuth } from "../context/AuthContext";
import "../styles/transport.css";

const emptyAssignment = { vehicle: "", route: "", driver: "", conductor: "", starts_at: "", ends_at: "" };
const emptyRole = { user: "", role: "driver", reason: "" };
const toArray = (value) => Array.isArray(value) ? value : value?.results || [];

export default function TransportOperations() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);
  const [role, setRole] = useState(emptyRole);
  const [route, setRoute] = useState({ name: "", origin: "", destination: "" });
  const [vehicle, setVehicle] = useState({ registration: "", owner: "", make_model: "" });
  const [assignment, setAssignment] = useState(emptyAssignment);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [usersResponse, routesResponse, vehiclesResponse, assignmentsResponse] = await Promise.all([
        api.get("transport/staff/users/"),
        api.get("transport/routes/"),
        api.get("transport/vehicles/"),
        api.get("transport/assignments/"),
      ]);
      setUsers(toArray(usersResponse.data));
      setRoutes(toArray(routesResponse.data));
      setVehicles(toArray(vehiclesResponse.data));
      setAssignments(toArray(assignmentsResponse.data));
    } catch (error) {
      setLoadError(error.response?.data?.detail || "Transport setup could not be loaded. Retry to continue.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const owners = useMemo(() => users.filter((user) => user.transport_roles?.includes("owner")), [users]);
  const drivers = useMemo(() => users.filter((user) => user.transport_roles?.includes("driver")), [users]);
  const conductors = useMemo(() => users.filter((user) => user.transport_roles?.includes("conductor")), [users]);
  const options = (list) => list.map((user) => <option key={user.id} value={user.id}>{user.name || user.username} (@{user.username})</option>);

  const send = async (path, payload, successText, reset) => {
    setNotice(null);
    setSaving(true);
    try {
      await api.post(path, payload);
      setNotice({ tone: "success", text: successText });
      if (reset) reset();
      await load();
    } catch (error) {
      setNotice({ tone: "danger", text: error.response?.data?.detail || error.response?.data?.error || "The change could not be saved. Check the details and retry." });
    } finally { setSaving(false); }
  };

  const handleRole = (event) => { event.preventDefault(); send("transport/roles/", { ...role, reason: role.reason.trim() }, "Transport role assigned.", () => setRole(emptyRole)); };
  const handleRoute = (event) => { event.preventDefault(); send("transport/routes/", route, "Route created.", () => setRoute({ name: "", origin: "", destination: "" })); };
  const handleVehicle = (event) => { event.preventDefault(); send("transport/vehicles/", vehicle, "Vehicle registered.", () => setVehicle({ registration: "", owner: "", make_model: "" })); };
  const handleAssignment = (event) => { event.preventDefault(); send("transport/assignments/", assignment, "Crew assignment created.", () => setAssignment(emptyAssignment)); };
  const assignmentEnded = (ended) => {
    setAssignments((current) => current.map((item) => item.id === ended.id ? ended : item));
    setNotice({ tone: "success", text: `Assignment ended for ${ended.vehicle_registration}.` });
  };

  return (
    <Layout>
      <main className="transport-operations-page">
        <PageHeading eyebrow="Staff workspace" title="Transport operations" description="Manage transport roles, routes, vehicles, and effective-dated crew assignments." actions={<Button variant="secondary" onClick={load} loading={loading}><Icon name="refresh" /> Refresh</Button>} />
        {notice && <FeedbackMessage tone={notice.tone} title={notice.tone === "success" ? "Saved" : "Could not save"}>{notice.text}</FeedbackMessage>}
        {loadError && <FeedbackMessage tone="danger" title="Transport setup unavailable" action={<Button variant="secondary" onClick={load}><Icon name="refresh" /> Retry</Button>}>{loadError}</FeedbackMessage>}
        {loading && <LoadingState label="Loading transport setup…" />}

        {!loading && !loadError && <div className="transport-management-grid">
          <section className="ui-panel transport-management-panel">
            <div className="ui-panel-header"><div><p className="ui-eyebrow">Access</p><h2 className="ui-panel-title">Assign transport role</h2></div><Icon name="users" /></div>
            <form className="ui-panel-body transport-form" onSubmit={handleRole}>
              <FormField label="Existing user" htmlFor="transport-role-user"><select className="ui-select" id="transport-role-user" required value={role.user} onChange={(event) => setRole({ ...role, user: event.target.value })}><option value="">Choose member</option>{options(users.filter((candidate) => candidate.id !== user?.id))}</select></FormField>
              <FormField label="Role" htmlFor="transport-role"><select className="ui-select" id="transport-role" required value={role.role} onChange={(event) => setRole({ ...role, role: event.target.value })}><option value="owner">Owner</option><option value="driver">Driver</option><option value="conductor">Conductor</option></select></FormField>
              <FormField label="Reason for granting this role" htmlFor="transport-role-reason"><input className="ui-input" id="transport-role-reason" required maxLength="500" value={role.reason} onChange={(event) => setRole({ ...role, reason: event.target.value })} /></FormField>
              <Button type="submit" loading={saving} disabled={!role.reason.trim()}><Icon name="plus" /> Assign role</Button>
            </form>
          </section>

          <section className="ui-panel transport-management-panel">
            <div className="ui-panel-header"><div><p className="ui-eyebrow">Network</p><h2 className="ui-panel-title">Create route</h2></div><Icon name="map" /></div>
            <form className="ui-panel-body transport-form" onSubmit={handleRoute}>
              <FormField label="Route name" htmlFor="transport-route-name"><input className="ui-input" id="transport-route-name" required value={route.name} onChange={(event) => setRoute({ ...route, name: event.target.value })} /></FormField>
              <FormField label="Origin" htmlFor="transport-route-origin"><input className="ui-input" id="transport-route-origin" value={route.origin} onChange={(event) => setRoute({ ...route, origin: event.target.value })} /></FormField>
              <FormField label="Destination" htmlFor="transport-route-destination"><input className="ui-input" id="transport-route-destination" value={route.destination} onChange={(event) => setRoute({ ...route, destination: event.target.value })} /></FormField>
              <Button type="submit" loading={saving}><Icon name="plus" /> Create route</Button>
            </form>
          </section>

          <section className="ui-panel transport-management-panel">
            <div className="ui-panel-header"><div><p className="ui-eyebrow">Fleet</p><h2 className="ui-panel-title">Register vehicle</h2></div><Icon name="truck" /></div>
            <form className="ui-panel-body transport-form" onSubmit={handleVehicle}>
              <FormField label="Registration" htmlFor="transport-vehicle-registration"><input className="ui-input" id="transport-vehicle-registration" required value={vehicle.registration} onChange={(event) => setVehicle({ ...vehicle, registration: event.target.value })} /></FormField>
              <FormField label="Vehicle owner" htmlFor="transport-vehicle-owner"><select className="ui-select" id="transport-vehicle-owner" required value={vehicle.owner} onChange={(event) => setVehicle({ ...vehicle, owner: event.target.value })}><option value="">Choose owner</option>{options(owners)}</select></FormField>
              <FormField label="Make / model" htmlFor="transport-vehicle-model"><input className="ui-input" id="transport-vehicle-model" value={vehicle.make_model} onChange={(event) => setVehicle({ ...vehicle, make_model: event.target.value })} /></FormField>
              <Button type="submit" loading={saving}><Icon name="plus" /> Register vehicle</Button>
            </form>
          </section>

          <section className="ui-panel transport-management-panel">
            <div className="ui-panel-header"><div><p className="ui-eyebrow">Crew</p><h2 className="ui-panel-title">Create crew assignment</h2></div><Icon name="users" /></div>
            <form className="ui-panel-body transport-form" onSubmit={handleAssignment}>
              <FormField label="Vehicle" htmlFor="transport-assignment-vehicle"><select className="ui-select" id="transport-assignment-vehicle" required value={assignment.vehicle} onChange={(event) => setAssignment({ ...assignment, vehicle: event.target.value })}><option value="">Choose vehicle</option>{vehicles.map((item) => <option key={item.id} value={item.id}>{item.registration}</option>)}</select></FormField>
              <FormField label="Route" htmlFor="transport-assignment-route"><select className="ui-select" id="transport-assignment-route" required value={assignment.route} onChange={(event) => setAssignment({ ...assignment, route: event.target.value })}><option value="">Choose route</option>{routes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>
              <FormField label="Driver" htmlFor="transport-assignment-driver"><select className="ui-select" id="transport-assignment-driver" required value={assignment.driver} onChange={(event) => setAssignment({ ...assignment, driver: event.target.value })}><option value="">Choose driver</option>{options(drivers)}</select></FormField>
              <FormField label="Conductor (optional)" htmlFor="transport-assignment-conductor"><select className="ui-select" id="transport-assignment-conductor" value={assignment.conductor} onChange={(event) => setAssignment({ ...assignment, conductor: event.target.value })}><option value="">No conductor</option>{options(conductors)}</select></FormField>
              <FormField label="Starts at (Nairobi time)" htmlFor="transport-assignment-start"><input className="ui-input" id="transport-assignment-start" type="datetime-local" required value={assignment.starts_at} onChange={(event) => setAssignment({ ...assignment, starts_at: event.target.value })} /></FormField>
              <FormField label="Ends at (Nairobi time)" htmlFor="transport-assignment-end"><input className="ui-input" id="transport-assignment-end" type="datetime-local" required min={assignment.starts_at || undefined} value={assignment.ends_at} onChange={(event) => setAssignment({ ...assignment, ends_at: event.target.value })} /></FormField>
              <Button type="submit" loading={saving}><Icon name="plus" /> Create assignment</Button>
            </form>
          </section>

          <TransportAssignmentHistory title="Crew assignment history" assignments={assignments} onEnded={assignmentEnded} />
        </div>}
      </main>
    </Layout>
  );
}
