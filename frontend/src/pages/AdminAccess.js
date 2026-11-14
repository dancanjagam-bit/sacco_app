import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import "../styles/staffAccess.css";

const STAFF_ROLES = [
  ["clerk", "Transport clerk"], ["credit_officer", "Credit officer"],
  ["treasurer", "Treasurer"], ["secretary", "Secretary"], ["chairman", "Chairman"],
  ["welfare_officer", "Welfare Officer"],
];
const TRANSPORT_ROLES = [["owner", "Vehicle owner"], ["driver", "Driver"], ["conductor", "Conductor"]];
const DUTIES = {
  clerk: [["transport_assignment", "Manage assigned vehicle/crew work"], ["cash_handover", "Confirm assigned cash handovers"], ["transport_issue", "Review assigned transport issues"]],
  credit_officer: [["loan_appraisal", "Appraise assigned loan"]],
  chairman: [["loan_approval", "Decide assigned loan"]],
};
const DUTY_SCOPE = {
  transport_assignment: ["vehicle", "crew_assignment"], cash_handover: ["crew_assignment"],
  transport_issue: ["transport_issue"], loan_appraisal: ["loan"], loan_approval: ["loan"],
};
const roleLabel = (role, choices) => choices.find(([key]) => key === role)?.[1] || role;

export default function AdminAccess() {
  const [overview, setOverview] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [roleQuery, setRoleQuery] = useState("");
  const [roleUsers, setRoleUsers] = useState([]);
  const [selectedRoleUser, setSelectedRoleUser] = useState(null);
  const [dutyQuery, setDutyQuery] = useState("");
  const [dutyUsers, setDutyUsers] = useState([]);
  const [selectedDutyUser, setSelectedDutyUser] = useState(null);
  const [roleType, setRoleType] = useState("staff");
  const [role, setRole] = useState("clerk");
  const [dutyRole, setDutyRole] = useState("clerk");
  const [duty, setDuty] = useState("transport_assignment");
  const [scopeType, setScopeType] = useState("vehicle");
  const [scopes, setScopes] = useState([]);
  const [scopeId, setScopeId] = useState("");
  const [roleReason, setRoleReason] = useState("");
  const [dutyReason, setDutyReason] = useState("");
  const [dutyStartsAt, setDutyStartsAt] = useState("");
  const [dutyEndsAt, setDutyEndsAt] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setState("loading"); setError("");
    try {
      const response = await api.get("admin/access/");
      if (!Array.isArray(response.data?.roles) || !Array.isArray(response.data?.duties) || !Array.isArray(response.data?.transport_roles)) {
        throw new Error("Unexpected access assignment response.");
      }
      setOverview(response.data); setState("ready");
    } catch (requestError) {
      setOverview(null); setState("error");
      setError(requestError.response?.data?.detail || "Role assignments could not be loaded.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const normalized = roleQuery.trim();
    if (normalized.length < 2) { setRoleUsers([]); return undefined; }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await api.get("admin/access/users/", { params: { q: normalized } });
        if (!cancelled) setRoleUsers(Array.isArray(response.data?.results) ? response.data.results : []);
      } catch { if (!cancelled) setRoleUsers([]); }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [roleQuery]);
  useEffect(() => {
    const normalized = dutyQuery.trim();
    if (normalized.length < 2) { setDutyUsers([]); return undefined; }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const response = await api.get("admin/access/users/", { params: { q: normalized } });
        if (!cancelled) setDutyUsers(Array.isArray(response.data?.results) ? response.data.results : []);
      } catch { if (!cancelled) setDutyUsers([]); }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [dutyQuery]);
  useEffect(() => {
    const permittedDuties = DUTIES[dutyRole] || [];
    if (!permittedDuties.some(([key]) => key === duty)) setDuty(permittedDuties[0]?.[0] || "");
  }, [dutyRole, duty]);
  useEffect(() => {
    const allowedScopes = DUTY_SCOPE[duty] || [];
    if (!allowedScopes.includes(scopeType)) setScopeType(allowedScopes[0] || "");
  }, [duty, scopeType]);
  useEffect(() => {
    if (!duty || !scopeType) { setScopes([]); setScopeId(""); return; }
    let cancelled = false;
    api.get("admin/access/scopes/", { params: { duty, scope_type: scopeType } }).then((response) => {
      const results = Array.isArray(response.data?.results) ? response.data.results.filter((row) => row.scope_type === scopeType) : [];
      if (!cancelled) { setScopes(results); setScopeId(""); }
    }).catch(() => { if (!cancelled) { setScopes([]); setScopeId(""); } });
    return () => { cancelled = true; };
  }, [duty, scopeType]);

  async function submitRole(event) {
    event.preventDefault(); setError(""); setNotice("");
    if (!selectedRoleUser || !roleReason.trim()) { setError("Choose an account and provide the reason for this assignment."); return; }
    setSaving(true);
    try {
      const endpoint = roleType === "transport" ? "admin/access/transport-roles/" : "admin/access/roles/";
      await api.post(endpoint, { user_id: selectedRoleUser.id, role, reason: roleReason.trim() });
      setNotice(`${roleLabel(role, roleType === "transport" ? TRANSPORT_ROLES : STAFF_ROLES)} assigned to ${selectedRoleUser.display_name}.`);
      setRoleReason(""); await load();
    } catch (requestError) { setError(requestError.response?.data?.detail || "Role assignment could not be saved."); }
    finally { setSaving(false); }
  }

  async function submitDuty(event) {
    event.preventDefault(); setError(""); setNotice("");
    if (!selectedDutyUser || !duty || !scopeId || !dutyReason.trim()) { setError("Choose an account, duty scope, and reason."); return; }
    setSaving(true);
    try {
      await api.post("admin/access/duties/", {
        staff_id: selectedDutyUser.id, duty, scope_type: scopeType, scope_id: scopeId, reason: dutyReason.trim(),
        starts_at: dutyStartsAt ? new Date(dutyStartsAt).toISOString() : null,
        ends_at: dutyEndsAt ? new Date(dutyEndsAt).toISOString() : null,
      });
      setNotice(`${roleLabel(duty, DUTIES[dutyRole] || [])} assigned to ${selectedDutyUser.display_name}.`);
      setDutyReason(""); await load();
    } catch (requestError) { setError(requestError.response?.data?.detail || "Scoped duty could not be assigned."); }
    finally { setSaving(false); }
  }

  async function revoke(endpoint, id, label) {
    const why = window.prompt(`Reason for ending ${label}:`);
    if (!why?.trim()) return;
    setError(""); setNotice("");
    try { await api.post(endpoint, { reason: why.trim() }); setNotice(`${label} ended.`); await load(); }
    catch (requestError) { setError(requestError.response?.data?.detail || `${label} could not be ended.`); }
  }

  const roleOptions = roleType === "transport" ? TRANSPORT_ROLES : STAFF_ROLES;

  return <Layout><main className="staff-access-page">
    <PageHeading eyebrow="System administration" title="Role and duty assignments" description="Grant only the workspace and record scope needed for a person’s duties. Assignment changes are audited." actions={<Button variant="secondary" onClick={load} loading={state === "loading"}>Refresh</Button>} />
    {error && <FeedbackMessage tone="danger" title="Action needs attention">{error}</FeedbackMessage>}
    {notice && <FeedbackMessage tone="success" title="Saved">{notice}</FeedbackMessage>}
    {state === "loading" && !overview && <LoadingState label="Loading current role assignments…" />}
    {state === "error" && <FeedbackMessage tone="danger" title="Access management unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>}
    {overview && <>
      <section className="ui-panel staff-access-forms" aria-label="Grant role or scoped duty">
        <div className="ui-panel-header"><div><h2 className="ui-panel-title">Assign access</h2><p className="staff-access-muted">Users cannot grant roles to themselves. Workspaces do not add permissions beyond the listed role and scope.</p></div></div>
        <div className="staff-access-form-grid">
          <form className="staff-access-form" onSubmit={submitRole}>
            <h3>Workspace role</h3>
            <FormField label="Find an existing account" htmlFor="access-user-search" hint="Search by username or name; use at least two characters.">
              <input id="access-user-search" className="ui-input" value={roleQuery} onChange={(event) => { setRoleQuery(event.target.value); setSelectedRoleUser(null); }} autoComplete="off" />
            </FormField>
            {roleUsers.length > 0 && <div className="staff-access-user-results" role="listbox" aria-label="Matching accounts">{roleUsers.map((candidate) => <button type="button" key={candidate.id} onClick={() => { setSelectedRoleUser(candidate); setRoleQuery(candidate.display_name); setRoleUsers([]); }}>{candidate.display_name} <span>{candidate.username}</span></button>)}</div>}
            {selectedRoleUser && <p className="staff-access-selected">Selected: <strong>{selectedRoleUser.display_name}</strong> · {selectedRoleUser.username}</p>}
            <FormField label="Role category" htmlFor="access-role-type"><select id="access-role-type" className="ui-select" value={roleType} onChange={(event) => { setRoleType(event.target.value); setRole(event.target.value === "transport" ? "owner" : "clerk"); }}><option value="staff">Cooperative staff role</option><option value="transport">Transport role</option></select></FormField>
            <FormField label="Role" htmlFor="access-role"><select id="access-role" className="ui-select" value={role} onChange={(event) => setRole(event.target.value)}>{roleOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FormField>
            <FormField label="Reason" htmlFor="access-role-reason"><textarea id="access-role-reason" className="ui-textarea" rows="3" maxLength="500" value={roleReason} onChange={(event) => setRoleReason(event.target.value)} required /></FormField>
            <Button type="submit" loading={saving} disabled={!selectedRoleUser || !roleReason.trim()}>Assign role</Button>
          </form>
          <form className="staff-access-form" onSubmit={submitDuty}>
            <h3>Scoped staff duty</h3>
            <p className="staff-access-muted">Select a staff member with the matching workspace role first. Appraisal and approval duties are separate.</p>
            <FormField label="Staff role" htmlFor="duty-role"><select id="duty-role" className="ui-select" value={dutyRole} onChange={(event) => setDutyRole(event.target.value)}>{STAFF_ROLES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FormField>
            <FormField label="Staff account" htmlFor="duty-user-search"><input id="duty-user-search" className="ui-input" value={dutyQuery} onChange={(event) => { setDutyQuery(event.target.value); setSelectedDutyUser(null); }} autoComplete="off" /></FormField>
            {dutyUsers.length > 0 && <div className="staff-access-user-results" role="listbox" aria-label="Matching staff accounts">{dutyUsers.map((candidate) => <button type="button" key={candidate.id} onClick={() => { setSelectedDutyUser(candidate); setDutyQuery(candidate.display_name); setDutyUsers([]); }}>{candidate.display_name} <span>{candidate.username}</span></button>)}</div>}
            {selectedDutyUser && <p className="staff-access-selected">Selected: <strong>{selectedDutyUser.display_name}</strong> · {selectedDutyUser.username}</p>}
            <FormField label="Duty" htmlFor="access-duty"><select id="access-duty" className="ui-select" value={duty} onChange={(event) => setDuty(event.target.value)}>{(DUTIES[dutyRole] || []).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FormField>
            {duty === "transport_assignment" && <FormField label="Scope type" htmlFor="access-scope-type"><select id="access-scope-type" className="ui-select" value={scopeType} onChange={(event) => setScopeType(event.target.value)}>{(DUTY_SCOPE[duty] || []).map((key) => <option key={key} value={key}>{key.replaceAll("_", " ")}</option>)}</select></FormField>}
            <FormField label="Scoped record" htmlFor="access-scope"><select id="access-scope" className="ui-select" value={scopeId} onChange={(event) => setScopeId(event.target.value)} required><option value="">Choose a record</option>{scopes.map((scope) => <option key={scope.id} value={scope.id}>{scope.label}</option>)}</select></FormField>
            <FormField label="Duty starts at (optional; defaults to now)" htmlFor="duty-starts-at"><input id="duty-starts-at" className="ui-input" type="datetime-local" value={dutyStartsAt} onChange={(event) => setDutyStartsAt(event.target.value)} /></FormField>
            <FormField label="Duty ends at (optional)" htmlFor="duty-ends-at"><input id="duty-ends-at" className="ui-input" type="datetime-local" value={dutyEndsAt} onChange={(event) => setDutyEndsAt(event.target.value)} /></FormField>
            <FormField label="Reason" htmlFor="access-duty-reason"><textarea id="access-duty-reason" className="ui-textarea" rows="3" maxLength="500" value={dutyReason} onChange={(event) => setDutyReason(event.target.value)} required /></FormField>
            <Button type="submit" loading={saving} disabled={!selectedDutyUser || !scopeId || !dutyReason.trim() || !(DUTIES[dutyRole] || []).length}>Assign scoped duty</Button>
          </form>
        </div>
      </section>
      <section className="ui-panel staff-access-table-panel"><div className="ui-panel-header"><h2 className="ui-panel-title">Current staff role grants</h2></div><div className="ui-table-wrap"><table className="ui-table"><thead><tr><th>Account</th><th>Role</th><th>State</th><th>Reason</th><th>Action</th></tr></thead><tbody>{overview.roles.length ? overview.roles.map((row) => <tr key={`role-${row.id}`}><td>{row.display_name}<span className="staff-access-subline">{row.username}</span></td><td>{roleLabel(row.role, STAFF_ROLES)}</td><td><StatusBadge status={row.active ? "active" : "closed"} label={row.active ? "Active" : "Revoked"} /></td><td>{row.reason}</td><td>{row.active && <Button variant="secondary" size="sm" onClick={() => revoke(`admin/access/roles/${row.id}/revoke/`, row.id, `${row.role} role`)}>Revoke</Button>}</td></tr>) : <tr><td colSpan="5" className="staff-access-empty">No staff role grants recorded.</td></tr>}</tbody></table></div></section>
      <section className="ui-panel staff-access-table-panel"><div className="ui-panel-header"><h2 className="ui-panel-title">Current transport role grants</h2></div><div className="ui-table-wrap"><table className="ui-table"><thead><tr><th>Account</th><th>Role</th><th>State</th><th>Action</th></tr></thead><tbody>{overview.transport_roles.length ? overview.transport_roles.map((row) => <tr key={`transport-${row.id}`}><td>{row.display_name}<span className="staff-access-subline">{row.username}</span></td><td>{roleLabel(row.role, TRANSPORT_ROLES)}</td><td><StatusBadge status={row.active ? "active" : "closed"} label={row.active ? "Active" : "Inactive"} /></td><td>{row.active && <Button variant="secondary" size="sm" onClick={() => revoke(`admin/access/transport-roles/${row.id}/revoke/`, row.id, `${row.role} role`)}>Revoke</Button>}</td></tr>) : <tr><td colSpan="4" className="staff-access-empty">No transport role grants recorded.</td></tr>}</tbody></table></div></section>
      <section className="ui-panel staff-access-table-panel"><div className="ui-panel-header"><div><h2 className="ui-panel-title">Legacy staff profiles</h2><p className="staff-access-muted">Existing legacy role records remain visible here. Manage their active status in Staff accounts; these are not new workspace grants.</p></div></div><div className="ui-table-wrap"><table className="ui-table"><thead><tr><th>Account</th><th>Legacy role</th><th>Status</th></tr></thead><tbody>{(overview.legacy_profiles || []).length ? overview.legacy_profiles.map((row) => <tr key={`legacy-${row.id}`}><td>{row.display_name}<span className="staff-access-subline">{row.username}</span></td><td>{row.role.replaceAll("_", " ")}</td><td><StatusBadge status={row.status === "active" ? "active" : "inactive"} label={row.status} /></td></tr>) : <tr><td colSpan="3" className="staff-access-empty">No legacy staff profiles.</td></tr>}</tbody></table></div></section>
      <section className="ui-panel staff-access-table-panel"><div className="ui-panel-header"><h2 className="ui-panel-title">Scoped duty assignments</h2></div><div className="ui-table-wrap"><table className="ui-table"><thead><tr><th>Account</th><th>Duty</th><th>Scope</th><th>Effective period</th><th>State</th><th>Action</th></tr></thead><tbody>{overview.duties.length ? overview.duties.map((row) => <tr key={`duty-${row.id}`}><td>{row.display_name}<span className="staff-access-subline">{row.username}</span></td><td>{row.duty.replaceAll("_", " ")}</td><td>{row.scope}</td><td>{new Date(row.starts_at).toLocaleString()}{row.ends_at ? ` — ${new Date(row.ends_at).toLocaleString()}` : " — No end date"}</td><td><StatusBadge status={row.active ? "active" : "closed"} label={row.active ? "Active" : "Ended"} /></td><td>{row.active && <Button variant="secondary" size="sm" onClick={() => revoke(`admin/access/duties/${row.id}/revoke/`, row.id, `${row.duty.replaceAll("_", " ")} duty`)}>End</Button>}</td></tr>) : <tr><td colSpan="6" className="staff-access-empty">No scoped duties recorded.</td></tr>}</tbody></table></div></section>
    </>}
  </main></Layout>;
}
