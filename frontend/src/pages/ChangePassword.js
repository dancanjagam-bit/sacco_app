import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import PageHeading from "../components/ui/PageHeading";
import "../styles/member-profile.css";

const initialForm = { old_password: "", new_password: "", confirm_password: "" };

export default function ChangePassword() {
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [visible, setVisible] = useState({ old_password: false, new_password: false, confirm_password: false });
  const [message, setMessage] = useState(null);
  const [saving, setSaving] = useState(false);

  const update = (event) => { setForm((current) => ({ ...current, [event.target.name]: event.target.value })); setMessage(null); };
  const passwordValid = form.new_password.length >= 8 && /[A-Za-z]/.test(form.new_password) && /\d/.test(form.new_password);
  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!passwordValid) { setMessage({ tone: "danger", title: "Choose a stronger password", text: "Use at least 8 characters, with a letter and a number." }); return; }
    if (form.new_password !== form.confirm_password) { setMessage({ tone: "danger", title: "Passwords do not match", text: "Enter the same new password in both fields." }); return; }
    setSaving(true);
    setMessage(null);
    try {
      await api.post("change-password/", form);
      setForm(initialForm);
      setMessage({ tone: "success", title: "Password changed", text: "Your password was updated. Please sign in again if asked." });
      window.setTimeout(() => navigate("/dashboard"), 1500);
    } catch (error) {
      const data = error.response?.data;
      const text = data?.error || Object.entries(data || {}).map(([field, errors]) => `${field.replace(/_/g, " ")}: ${Array.isArray(errors) ? errors[0] : errors}`).join(" · ") || "The password could not be changed. Try again.";
      setMessage({ tone: "danger", title: "Password change failed", text });
    } finally { setSaving(false); }
  };

  const fields = [
    ["Current password", "old_password", "Enter current password"],
    ["New password", "new_password", "At least 8 characters"],
    ["Confirm new password", "confirm_password", "Repeat new password"],
  ];

  return <Layout>
    <div className="member-profile-page">
      <PageHeading eyebrow="Account security" title="Change password" description="Update the password you use to sign in." />
      {message && <FeedbackMessage tone={message.tone} title={message.title}>{message.text}</FeedbackMessage>}
      <section className="ui-panel member-profile-card">
        <form className="member-password-form" onSubmit={handleSubmit}>
          {fields.map(([label, name, placeholder]) => <div className="ui-field" key={name}>
            <label className="ui-label" htmlFor={name}>{label}</label>
            <div className="ui-password-control">
              <span className="ui-password-icon"><Icon name="lock" size={17} /></span>
              <input className="ui-input" id={name} name={name} type={visible[name] ? "text" : "password"} autoComplete={name === "old_password" ? "current-password" : "new-password"} required value={form[name]} onChange={update} placeholder={placeholder} />
              <button className="ui-password-toggle" type="button" aria-label={`${visible[name] ? "Hide" : "Show"} ${label.toLowerCase()}`} aria-pressed={visible[name]} onClick={() => setVisible((current) => ({ ...current, [name]: !current[name] }))}><Icon name={visible[name] ? "eyeOff" : "eye"} /></button>
            </div>
          </div>)}
          {form.new_password && <ul className="member-password-checks" aria-label="Password requirements">
            <li className={form.new_password.length >= 8 ? "is-valid" : ""}>At least 8 characters</li>
            <li className={/[A-Za-z]/.test(form.new_password) ? "is-valid" : ""}>Contains a letter</li>
            <li className={/\d/.test(form.new_password) ? "is-valid" : ""}>Contains a number</li>
          </ul>}
          <Button type="submit" loading={saving} disabled={saving || !form.old_password || !passwordValid || !form.confirm_password}><Icon name="lock" /> Change password</Button>
        </form>
      </section>
    </div>
  </Layout>;
}
