import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import "../styles/member-profile.css";

const editableFields = [
  ["First name", "first_name", "text"], ["Last name", "last_name", "text"],
  ["Email address", "email", "email"], ["Phone number", "phone_number", "tel"],
  ["County", "county", "text"], ["Address", "address", "textarea"],
];

export default function Profile() {
  const { refreshUser } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [form, setForm] = useState({});

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const response = await api.get("profile/");
      if (!response.data || typeof response.data !== "object") throw new Error("Invalid profile response");
      setProfile(response.data);
      setForm(Object.fromEntries([...editableFields, ["Recovery email", "recovery_email"], ["Recovery phone", "recovery_phone"]].map(([, key]) => [key, response.data[key] || ""])));
    } catch {
      setLoadError(true);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadProfile(); }, [loadProfile]);
  const changeField = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }));

  const saveProfile = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await api.put("profile/", form);
      setEditing(false);
      setMessage({ tone: "success", title: "Profile updated", text: "Your profile changes were saved." });
      await loadProfile();
      await refreshUser?.();
    } catch (error) {
      const data = error.response?.data;
      const text = data?.error || Object.entries(data || {}).map(([field, errors]) => `${field.replace(/_/g, " ")}: ${Array.isArray(errors) ? errors[0] : errors}`).join(" · ") || "Your profile could not be updated.";
      setMessage({ tone: "danger", title: "Profile update failed", text });
    } finally { setSaving(false); }
  };

  const fieldValue = (key) => form[key] || "Not set";
  return <Layout>
    <div className="member-profile-page">
      <PageHeading eyebrow="Account settings" title="Profile and security" description="Review your details and recovery contacts." actions={profile && !editing ? <Button variant="secondary" onClick={() => { setEditing(true); setMessage(null); }}><Icon name="user" /> Edit profile</Button> : null} />
      {message && <FeedbackMessage tone={message.tone} title={message.title}>{message.text}</FeedbackMessage>}
      {loading && <LoadingState label="Loading profile…" />}
      {!loading && loadError && <FeedbackMessage tone="warning" title="Profile unavailable" action={<Button variant="secondary" onClick={loadProfile}><Icon name="refresh" /> Retry</Button>}>Your profile could not be loaded. Check your connection and try again.</FeedbackMessage>}
      {!loading && !loadError && profile && <div className="member-profile-grid">
        <section className="ui-panel member-profile-card" aria-labelledby="personal-information-title">
          <div className="ui-panel-header"><h2 className="ui-panel-title" id="personal-information-title">Personal information</h2></div>
          <div className="ui-panel-body">
            {editing ? <form className="member-profile-form" onSubmit={saveProfile}>
              {editableFields.map(([label, key, type]) => <FormField label={label} htmlFor={`profile-${key}`} key={key}>{type === "textarea" ? <textarea className="ui-textarea" id={`profile-${key}`} name={key} rows="3" value={form[key] || ""} onChange={changeField} /> : <input className="ui-input" id={`profile-${key}`} type={type} name={key} value={form[key] || ""} onChange={changeField} />}</FormField>)}
              <h3 className="member-profile-subheading">Recovery contacts</h3>
              <FormField label="Recovery email" htmlFor="profile-recovery-email"><input className="ui-input" id="profile-recovery-email" type="email" name="recovery_email" value={form.recovery_email || ""} onChange={changeField} /></FormField>
              <FormField label="Recovery phone" htmlFor="profile-recovery-phone"><input className="ui-input" id="profile-recovery-phone" type="tel" name="recovery_phone" value={form.recovery_phone || ""} onChange={changeField} /></FormField>
              <div className="member-profile-actions"><Button type="submit" loading={saving}>Save changes</Button><Button variant="secondary" onClick={() => { setEditing(false); setForm(Object.fromEntries([...editableFields, ["Recovery email", "recovery_email"], ["Recovery phone", "recovery_phone"]].map(([, key]) => [key, profile[key] || ""]))); }}>Cancel</Button></div>
            </form> : <>
              <dl className="member-profile-details">{editableFields.map(([label, key]) => <div key={key}><dt>{label}</dt><dd>{fieldValue(key)}</dd></div>)}</dl>
              <h3 className="member-profile-subheading">Recovery contacts</h3>
              <dl className="member-profile-details"><div><dt>Recovery email</dt><dd>{fieldValue("recovery_email")}</dd></div><div><dt>Recovery phone</dt><dd>{fieldValue("recovery_phone")}</dd></div></dl>
            </>}
          </div>
        </section>
        <aside className="member-profile-side">
          <section className="ui-panel member-profile-card" aria-labelledby="account-details-title">
            <div className="ui-panel-header"><h2 className="ui-panel-title" id="account-details-title">Account details</h2></div>
            <div className="ui-panel-body"><dl className="member-profile-details">{[["Member number", profile.member_number], ["Username", profile.username], ["Gender", profile.gender], ["Date of birth", profile.date_of_birth], ["Date joined", profile.date_joined], ["Membership status", profile.status]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "Not set"}</dd></div>)}</dl></div>
          </section>
          <section className="ui-panel member-profile-card" aria-labelledby="profile-security-title">
            <div className="ui-panel-header"><h2 className="ui-panel-title" id="profile-security-title">Sign-in security</h2><Icon name="shield" /></div>
            <div className="ui-panel-body"><p className="ui-muted">Change your password regularly and keep your recovery contacts up to date.</p><Button as={Link} to="/change-password" variant="secondary"><Icon name="lock" /> Change password</Button></div>
          </section>
        </aside>
      </div>}
    </div>
  </Layout>;
}
