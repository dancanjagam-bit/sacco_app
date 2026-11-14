import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import "../styles/welfare.css";

const categoryRow = (id) => ({ id, category: "", maximum_benefit: "", minimum_contributions: "" });
const initialForm = { version: "", approval_reference: "", activate: false };

function dateStr(v) {
  return v ? new Date(v).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Nairobi" }) : "—";
}

export default function WelfarePolicy() {
  const { user } = useAuth();
  const canManage = user?.permissions?.includes("staff.manage");
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");

  // Create form
  const [form, setForm] = useState(initialForm);
  const [categories, setCategories] = useState([categoryRow(1)]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const res = await api.get("welfare/policy/");
      setData(res.data);
      setState("ready");
    } catch (err) {
      setState("error");
      setError(err.response?.data?.detail || "Welfare policy could not be loaded.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    setFormError("");
    setFormSuccess("");
    const names = categories.map((row) => row.category.trim());
    if (names.some((name) => !name) || new Set(names.map((name) => name.toLowerCase())).size !== names.length) {
      setFormError("Enter a distinct name for each benefit category.");
      return;
    }
    const benefits = Object.fromEntries(categories.map(({ category, maximum_benefit, minimum_contributions }) => [
      category.trim(), { maximum_benefit, minimum_contributions },
    ]));
    setSaving(true);
    try {
      await api.post("welfare/policy/", {
        version: form.version,
        approval_reference: form.approval_reference,
        benefits,
        activate: form.activate,
      });
      setFormSuccess("Policy created successfully.");
      setForm(initialForm);
      setCategories([categoryRow(1)]);
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || "Could not create policy.");
    } finally {
      setSaving(false);
    }
  }

  function updateCategory(id, field, value) {
    setCategories((rows) => rows.map((row) => row.id === id ? { ...row, [field]: value } : row));
  }

  const active = data?.active_policy;
  const policies = data?.policies || [];

  return (
    <Layout>
      <main className="welfare-page">
        <PageHeading
          eyebrow="Welfare officer workspace"
          title="Welfare policy"
          description="Configure benefit categories, maximum payouts, and minimum contribution requirements."
          actions={<Button variant="secondary" onClick={load} loading={state === "loading"}><Icon name="refresh" size={15} /> Refresh</Button>}
        />

        {state === "loading" && <LoadingState label="Loading welfare policy…" />}
        {state === "error" && (
          <FeedbackMessage tone="danger" title="Policy unavailable" action={<Button variant="secondary" onClick={load}>Retry</Button>}>{error}</FeedbackMessage>
        )}

        {state === "ready" && (
          <>
            {/* Active policy */}
            <section className="ui-panel" aria-labelledby="active-policy-title">
              <div className="ui-panel-header">
                <div>
                  <p className="ui-eyebrow">Current</p>
                  <h2 className="ui-panel-title" id="active-policy-title">Active policy</h2>
                </div>
                {active && <StatusBadge status="active" label={`v${active.version}`} />}
              </div>
              <div className="ui-panel-body">
                {!active ? (
                  <div className="ui-empty"><strong>No active welfare policy.</strong>{canManage && <span>Create and activate an approved policy below.</span>}</div>
                ) : (
                  <>
                    <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--space-2) var(--space-4)", margin: 0, fontSize: "var(--text-sm)" }}>
                      <dt style={{ color: "var(--text-muted)" }}>Version</dt><dd style={{ margin: 0 }}>{active.version}</dd>
                      <dt style={{ color: "var(--text-muted)" }}>Approval reference</dt><dd style={{ margin: 0 }}>{active.approval_reference}</dd>
                      <dt style={{ color: "var(--text-muted)" }}>Approved at</dt><dd style={{ margin: 0 }}>{dateStr(active.approved_at)}</dd>
                    </dl>
                    <h3 style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-2)", fontSize: "var(--text-base)" }}>Benefit categories</h3>
                    {active.benefits && Object.keys(active.benefits).length > 0 ? (
                      <div style={{ overflowX: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-sm)" }}>
                          <thead>
                            <tr style={{ borderBottom: "2px solid var(--border)" }}>
                              <th style={{ textAlign: "left", padding: "var(--space-2) var(--space-3)", color: "var(--text-muted)", fontWeight: 600 }}>Category</th>
                              <th style={{ textAlign: "right", padding: "var(--space-2) var(--space-3)", color: "var(--text-muted)", fontWeight: 600 }}>Max benefit (KES)</th>
                              <th style={{ textAlign: "right", padding: "var(--space-2) var(--space-3)", color: "var(--text-muted)", fontWeight: 600 }}>Min contributions (KES)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(active.benefits).map(([cat, rule]) => (
                              <tr key={cat} style={{ borderBottom: "1px solid var(--border)" }}>
                                <td style={{ padding: "var(--space-2) var(--space-3)", fontWeight: 500 }}>{cat}</td>
                                <td style={{ padding: "var(--space-2) var(--space-3)", textAlign: "right" }}>
                                  {Number(rule.maximum_benefit).toLocaleString("en-KE", { minimumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: "var(--space-2) var(--space-3)", textAlign: "right" }}>
                                  {Number(rule.minimum_contributions).toLocaleString("en-KE", { minimumFractionDigits: 2 })}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>No benefit categories defined.</p>
                    )}
                  </>
                )}
              </div>
            </section>

            {/* Create new policy (staff.manage only) */}
            {canManage && (
              <section className="ui-panel" aria-labelledby="create-policy-title">
                <div className="ui-panel-header">
                  <div>
                    <p className="ui-eyebrow">Administration</p>
                    <h2 className="ui-panel-title" id="create-policy-title">Create new policy version</h2>
                  </div>
                  <Icon name="settings" />
                </div>
                <form className="ui-panel-body" style={{ display: "grid", gap: "var(--space-4)", maxWidth: "640px" }} onSubmit={create}>
                  {formError && <FeedbackMessage tone="danger">{formError}</FeedbackMessage>}
                  {formSuccess && <FeedbackMessage tone="success">{formSuccess}</FeedbackMessage>}
                  <FormField label="Version" htmlFor="policy-version">
                    <input id="policy-version" className="ui-input" required maxLength="60" value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} placeholder="e.g. 2024-v1" />
                  </FormField>
                  <FormField label="Approval reference (board resolution number)" htmlFor="policy-approval-ref">
                    <input id="policy-approval-ref" className="ui-input" required maxLength="120" value={form.approval_reference} onChange={(e) => setForm({ ...form, approval_reference: e.target.value })} placeholder="e.g. BD-RES-2024-003" />
                  </FormField>
                  <h3>Benefit categories</h3>
                  {categories.map((row, index) => (
                    <fieldset className="welfare-policy-category" key={row.id} disabled={saving}>
                      <legend>Benefit {index + 1}</legend>
                      <FormField label="Category name" htmlFor={`benefit-category-${row.id}`}>
                        <input id={`benefit-category-${row.id}`} className="ui-input" required maxLength="60" value={row.category} onChange={(e) => updateCategory(row.id, "category", e.target.value)} />
                      </FormField>
                      <FormField label="Maximum benefit (KES)" htmlFor={`benefit-max-${row.id}`}>
                        <input id={`benefit-max-${row.id}`} className="ui-input" type="number" inputMode="decimal" required min="0.01" max="9999999999.99" step="0.01" value={row.maximum_benefit} onChange={(e) => updateCategory(row.id, "maximum_benefit", e.target.value)} />
                      </FormField>
                      <FormField label="Minimum posted contributions (KES)" htmlFor={`benefit-min-${row.id}`}>
                        <input id={`benefit-min-${row.id}`} className="ui-input" type="number" inputMode="decimal" required min="0" max="9999999999.99" step="0.01" value={row.minimum_contributions} onChange={(e) => updateCategory(row.id, "minimum_contributions", e.target.value)} />
                      </FormField>
                      {categories.length > 1 && <Button variant="secondary" onClick={() => setCategories((rows) => rows.filter((item) => item.id !== row.id))}>Remove benefit {index + 1}</Button>}
                    </fieldset>
                  ))}
                  <Button variant="secondary" disabled={saving} onClick={() => setCategories((rows) => [...rows, categoryRow(rows[rows.length - 1].id + 1)])}>Add benefit category</Button>
                  <label className="welfare-activate-policy"><input type="checkbox" checked={form.activate} onChange={(e) => setForm({ ...form, activate: e.target.checked })} /> Activate this policy and retire the current version</label>
                  <Button type="submit" loading={saving}><Icon name="plus" size={15} /> Create policy</Button>
                </form>
              </section>
            )}

            {/* Policy history */}
            {policies.length > 0 && (
              <section className="ui-panel" aria-labelledby="policy-history-title">
                <div className="ui-panel-header">
                  <div>
                    <p className="ui-eyebrow">History</p>
                    <h2 className="ui-panel-title" id="policy-history-title">All policy versions</h2>
                  </div>
                </div>
                <div className="ui-panel-body" style={{ display: "grid", gap: "var(--space-2)" }}>
                  {policies.map((p) => (
                    <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-2) 0", borderBottom: "1px solid var(--border)", flexWrap: "wrap", gap: "var(--space-2)" }}>
                      <div>
                        <strong>{p.version}</strong>
                        <span style={{ marginLeft: 8, fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>{p.approval_reference}</span>
                        <div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", marginTop: 2 }}>Approved: {dateStr(p.approved_at)}</div>
                      </div>
                      <StatusBadge status={p.active ? "active" : "inactive"} label={p.active ? "Active" : "Inactive"} />
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </Layout>
  );
}
