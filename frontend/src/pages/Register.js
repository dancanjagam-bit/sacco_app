import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/axios";
import "../styles/auth.css";

const COUNTIES = [
  "Mombasa","Kwale","Kilifi","Tana River","Lamu","Taita-Taveta",
  "Garissa","Wajir","Mandera","Marsabit","Isiolo","Meru",
  "Tharaka-Nithi","Embu","Kitui","Machakos","Makueni","Nyandarua",
  "Nyeri","Kirinyaga","Murang'a","Kiambu","Turkana","West Pokot",
  "Samburu","Trans-Nzoia","Uasin Gishu","Elgeyo-Marakwet","Nandi",
  "Baringo","Laikipia","Nakuru","Narok","Kajiado","Kericho",
  "Bomet","Kakamega","Vihiga","Bungoma","Busia","Siaya",
  "Kisumu","Homa Bay","Migori","Kisii","Nyamira","Nairobi",
];

const MAX_DOB = new Date(Date.now() - 18 * 365.25 * 24 * 3600 * 1000)
  .toISOString()
  .split("T")[0];

// Reusable label + error helper — a plain function, NOT a component
function labelStyle() {
  return {
    display: "block",
    fontSize: "12px",
    fontWeight: "700",
    color: "#475569",
    textTransform: "uppercase",
    letterSpacing: ".4px",
    marginBottom: "5px",
  };
}
function errStyle() {
  return { margin: "4px 0 0", fontSize: "12px", color: "#dc2626" };
}
function inputStyle(hasError) {
  return {
    width: "100%",
    padding: "11px 14px",
    border: `1.5px solid ${hasError ? "#fca5a5" : "#e2e8f0"}`,
    borderRadius: "10px",
    fontSize: "15px",
    fontFamily: "inherit",
    background: hasError ? "#fef2f2" : "#f8fafc",
    boxSizing: "border-box",
    outline: "none",
    transition: "border-color .15s",
  };
}

export default function Register() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    username: "", password: "", confirm_password: "",
    first_name: "", last_name: "", email: "",
    national_id: "", phone_number: "",
    gender: "male", date_of_birth: "",
    county: "", address: "",
    recovery_email: "", recovery_phone: "",
  });

  const [errors,  setErrors]  = useState({});
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [step,    setStep]    = useState(1);

  const [showPw,   setShowPw]   = useState(false);
  const [showConf, setShowConf] = useState(false);

  const set = (name) => (e) => {
    setForm(prev => ({ ...prev, [name]: e.target.value }));
    if (errors[name]) setErrors(prev => ({ ...prev, [name]: null }));
  };

  // ── Validation ─────────────────────────────────────────────────────────
  const validateStep1 = () => {
    const e = {};
    if (!form.first_name.trim()) e.first_name = "First name is required.";
    if (!form.last_name.trim())  e.last_name  = "Last name is required.";
    if (!form.email.trim())      e.email      = "Email is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      e.email = "Enter a valid email address.";
    if (!form.date_of_birth)     e.date_of_birth = "Date of birth is required.";
    else {
      const age = new Date().getFullYear() - new Date(form.date_of_birth).getFullYear();
      if (age < 18) e.date_of_birth = "You must be at least 18 years old.";
    }
    if (!form.gender) e.gender = "Select a gender.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const validateStep2 = () => {
    const e  = {};
    const ph = /^(?:\+254|254|0)([17]\d{8})$/;
    if (!form.national_id.trim()) e.national_id = "National ID is required.";
    else if (!/^\d{5,8}$/.test(form.national_id.trim()))
      e.national_id = "Enter a valid Kenyan National ID (5–8 digits).";
    if (!form.phone_number.trim()) e.phone_number = "Phone number is required.";
    else if (!ph.test(form.phone_number.replace(/[\s-]/g, "")))
      e.phone_number = "Enter a valid Kenyan number (e.g. 0722 000 000).";
    if (!form.county)  e.county  = "Select your county.";
    if (!form.address.trim()) e.address = "Address is required.";
    if (form.recovery_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.recovery_email))
      e.recovery_email = "Enter a valid email.";
    if (form.recovery_phone && !ph.test(form.recovery_phone.replace(/[\s-]/g, "")))
      e.recovery_phone = "Enter a valid Kenyan number.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const validateStep3 = () => {
    const e = {};
    if (!form.username.trim()) e.username = "Username is required.";
    else if (!/^[a-zA-Z0-9_]{3,30}$/.test(form.username))
      e.username = "3–30 chars, letters/numbers/underscores only.";
    if (!form.password) e.password = "Password is required.";
    else if (form.password.length < 8) e.password = "At least 8 characters.";
    else if (!/[A-Za-z]/.test(form.password)) e.password = "Must contain a letter.";
    else if (!/\d/.test(form.password)) e.password = "Must contain a number.";
    if (!form.confirm_password) e.confirm_password = "Please confirm your password.";
    else if (form.password !== form.confirm_password)
      e.confirm_password = "Passwords do not match.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const nextStep = () => {
    if (step === 1 && !validateStep1()) return;
    if (step === 2 && !validateStep2()) return;
    setStep(step + 1);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    if (!validateStep3()) return;
    setLoading(true);
    try {
      const res = await api.post("register/", form);
      setMessage({
        type: "success",
        text: `✅ Registration successful! Your Member Number is ${res.data.member_number}. Redirecting...`,
      });
      setTimeout(() => navigate("/"), 3000);
    } catch (err) {
      const data = err.response?.data;
      if (!data) {
        setMessage({ type: "error", text: "Registration failed. Check your connection." });
        return;
      }
      if (data.error) {
        setMessage({ type: "error", text: data.error });
      } else {
        const serverErrors = {};
        Object.entries(data).forEach(([f, errs]) => {
          serverErrors[f] = Array.isArray(errs) ? errs[0] : errs;
        });
        setErrors(serverErrors);
        const s1 = ["first_name","last_name","email","date_of_birth","gender"];
        const s2 = ["national_id","phone_number","county","address","recovery_email","recovery_phone"];
        if (Object.keys(serverErrors).some(f => s1.includes(f))) setStep(1);
        else if (Object.keys(serverErrors).some(f => s2.includes(f))) setStep(2);
        else setStep(3);
        setMessage({ type: "error", text: "Please fix the highlighted fields." });
      }
    } finally {
      setLoading(false);
    }
  };

  const pw = form.password;
  const pwOk = { length: pw.length >= 8, letter: /[A-Za-z]/.test(pw), number: /\d/.test(pw) };

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: "540px" }}>
        <div className="auth-logo">🏦</div>
        <h1 className="auth-title">SACCO Registration</h1>
        <p className="auth-subtitle">Create your SACCO member account</p>

        {/* Step indicator */}
        <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginBottom: "16px" }}>
          {[1, 2, 3].map(n => (
            <div key={n} style={{
              width: "32px", height: "32px", borderRadius: "50%",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: n <= step ? "#2563eb" : "#e2e8f0",
              color: n <= step ? "#fff" : "#94a3b8",
              fontWeight: "700", fontSize: "14px", transition: "background .2s",
            }}>
              {n < step ? "✓" : n}
            </div>
          ))}
        </div>
        <p style={{ textAlign: "center", fontSize: "13px", color: "#64748b", marginBottom: "16px" }}>
          {step === 1 ? "Personal Information" : step === 2 ? "Contact & Location" : "Account Security"}
        </p>

        {message && (
          <div className={`auth-message ${message.type}`}>{message.text}</div>
        )}

        <div className="auth-form">

          {/* ── STEP 1 ── */}
          {step === 1 && (
            <>
              <div className="auth-row">
                <div>
                  <label style={labelStyle()}>First Name <span style={{ color: "#dc2626" }}>*</span></label>
                  <input style={inputStyle(errors.first_name)} name="first_name" value={form.first_name} onChange={set("first_name")} placeholder="e.g. Ben" />
                  {errors.first_name && <p style={errStyle()}>{errors.first_name}</p>}
                </div>
                <div>
                  <label style={labelStyle()}>Last Name <span style={{ color: "#dc2626" }}>*</span></label>
                  <input style={inputStyle(errors.last_name)} name="last_name" value={form.last_name} onChange={set("last_name")} placeholder="e.g. Oduor" />
                  {errors.last_name && <p style={errStyle()}>{errors.last_name}</p>}
                </div>
              </div>

              <div>
                <label style={labelStyle()}>Email Address <span style={{ color: "#dc2626" }}>*</span></label>
                <input style={inputStyle(errors.email)} type="email" name="email" value={form.email} onChange={set("email")} placeholder="yourname@example.com" />
                {errors.email && <p style={errStyle()}>{errors.email}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Gender <span style={{ color: "#dc2626" }}>*</span></label>
                <select style={inputStyle(errors.gender)} name="gender" value={form.gender} onChange={set("gender")}>
                  <option value="">— Select gender —</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
                {errors.gender && <p style={errStyle()}>{errors.gender}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Date of Birth (must be 18+) <span style={{ color: "#dc2626" }}>*</span></label>
                <input style={inputStyle(errors.date_of_birth)} type="date" name="date_of_birth" value={form.date_of_birth} onChange={set("date_of_birth")} min="1924-01-01" max={MAX_DOB} />
                {errors.date_of_birth && <p style={errStyle()}>{errors.date_of_birth}</p>}
              </div>

              <button type="button" className="auth-button" onClick={nextStep}>
                Next: Contact Info →
              </button>
            </>
          )}

          {/* ── STEP 2 ── */}
          {step === 2 && (
            <>
              <div>
                <label style={labelStyle()}>National ID Number <span style={{ color: "#dc2626" }}>*</span></label>
                <input style={inputStyle(errors.national_id)} name="national_id" value={form.national_id} onChange={set("national_id")} placeholder="e.g. 28750187" maxLength={8} />
                {errors.national_id && <p style={errStyle()}>{errors.national_id}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Phone Number <span style={{ color: "#dc2626" }}>*</span></label>
                <input style={inputStyle(errors.phone_number)} name="phone_number" value={form.phone_number} onChange={set("phone_number")} placeholder="e.g. 0722 000 000" />
                {errors.phone_number && <p style={errStyle()}>{errors.phone_number}</p>}
              </div>

              <div>
                <label style={labelStyle()}>County (Kenya) <span style={{ color: "#dc2626" }}>*</span></label>
                <select style={inputStyle(errors.county)} name="county" value={form.county} onChange={set("county")}>
                  <option value="">— Select county —</option>
                  {COUNTIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                {errors.county && <p style={errStyle()}>{errors.county}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Physical Address <span style={{ color: "#dc2626" }}>*</span></label>
                <textarea style={{ ...inputStyle(errors.address), resize: "vertical", minHeight: "70px" }} name="address" value={form.address} onChange={set("address")} placeholder="e.g. P.O. Box 123, Kisumu" />
                {errors.address && <p style={errStyle()}>{errors.address}</p>}
              </div>

              <p style={{ fontSize: "11px", fontWeight: "700", color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".5px", margin: "4px 0 0" }}>
                Recovery Contacts (Optional)
              </p>
              <p style={{ fontSize: "12px", color: "#94a3b8", margin: "2px 0 4px" }}>
                Used to recover your account if you forget your password.
              </p>

              <div>
                <label style={labelStyle()}>Recovery Email</label>
                <input style={inputStyle(errors.recovery_email)} type="email" name="recovery_email" value={form.recovery_email} onChange={set("recovery_email")} placeholder="backup@example.com" />
                {errors.recovery_email && <p style={errStyle()}>{errors.recovery_email}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Recovery Phone</label>
                <input style={inputStyle(errors.recovery_phone)} name="recovery_phone" value={form.recovery_phone} onChange={set("recovery_phone")} placeholder="e.g. 0733 000 000" />
                {errors.recovery_phone && <p style={errStyle()}>{errors.recovery_phone}</p>}
              </div>

              <div style={{ display: "flex", gap: "10px" }}>
                <button type="button" onClick={() => setStep(1)} style={{ flex: 1, padding: "12px", border: "1.5px solid #e2e8f0", borderRadius: "10px", background: "#f8fafc", fontWeight: "600", cursor: "pointer" }}>
                  ← Back
                </button>
                <button type="button" className="auth-button" style={{ flex: 2 }} onClick={nextStep}>
                  Next: Set Password →
                </button>
              </div>
            </>
          )}

          {/* ── STEP 3 ── */}
          {step === 3 && (
            <>
              <div>
                <label style={labelStyle()}>Username <span style={{ color: "#dc2626" }}>*</span></label>
                <input style={inputStyle(errors.username)} name="username" value={form.username} onChange={set("username")} placeholder="e.g. benoduor" autoComplete="username" />
                {errors.username && <p style={errStyle()}>{errors.username}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Password <span style={{ color: "#dc2626" }}>*</span></label>
                <div className="auth-input-wrap">
                  <span className="auth-input-icon">🔒</span>
                  <input style={inputStyle(errors.password)} type={showPw ? "text" : "password"} name="password" value={form.password} onChange={set("password")} placeholder="At least 8 characters" autoComplete="new-password" className="auth-input-with-icon" />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="auth-toggle-pw" tabIndex={-1}>{showPw ? "🙈" : "👁️"}</button>
                </div>
                {pw.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "3px", marginTop: "6px", fontSize: "12px" }}>
                    {[["length", "8+ characters"], ["letter", "Contains a letter"], ["number", "Contains a number"]].map(([k, l]) => (
                      <span key={k} style={{ color: pwOk[k] ? "#16a34a" : "#94a3b8" }}>
                        {pwOk[k] ? "✅" : "○"} {l}
                      </span>
                    ))}
                  </div>
                )}
                {errors.password && <p style={errStyle()}>{errors.password}</p>}
              </div>

              <div>
                <label style={labelStyle()}>Confirm Password <span style={{ color: "#dc2626" }}>*</span></label>
                <div className="auth-input-wrap">
                  <span className="auth-input-icon">🔒</span>
                  <input style={inputStyle(errors.confirm_password)} type={showConf ? "text" : "password"} name="confirm_password" value={form.confirm_password} onChange={set("confirm_password")} placeholder="Repeat password" autoComplete="new-password" className="auth-input-with-icon" />
                  <button type="button" onClick={() => setShowConf(!showConf)} className="auth-toggle-pw" tabIndex={-1}>{showConf ? "🙈" : "👁️"}</button>
                </div>
                {form.confirm_password.length > 0 && (
                  <span style={{ fontSize: "12px", marginTop: "4px", display: "block", color: form.password === form.confirm_password ? "#16a34a" : "#dc2626" }}>
                    {form.password === form.confirm_password ? "✅ Passwords match" : "⚠️ Passwords do not match"}
                  </span>
                )}
                {errors.confirm_password && <p style={errStyle()}>{errors.confirm_password}</p>}
              </div>

              <div style={{ display: "flex", gap: "10px" }}>
                <button type="button" onClick={() => setStep(2)} style={{ flex: 1, padding: "12px", border: "1.5px solid #e2e8f0", borderRadius: "10px", background: "#f8fafc", fontWeight: "600", cursor: "pointer" }}>
                  ← Back
                </button>
                <button type="button" className="auth-button" style={{ flex: 2 }} disabled={loading} onClick={handleSubmit}>
                  {loading ? "Registering..." : "✅ Complete Registration"}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="auth-footer">
          Already have an account? <Link to="/">Sign in here</Link>
        </div>
      </div>
    </div>
  );
}
