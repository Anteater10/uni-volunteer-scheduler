import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../state/authContext";

export default function RegisterPage() {
  const nav = useNavigate();
  const { register } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [universityId, setUniversityId] = useState("");
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim(),
        password,
        university_id: universityId.trim() || null,
        notify_email: notifyEmail,
      });
      nav("/events");
    } catch (e2) {
      setErr(e2?.message || "Register failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 520 }}>
      <h2>Register (Participant)</h2>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}

      <form onSubmit={onSubmit} style={{ display: "grid", gap: 10 }}>
        <label>
          Full Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>

        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </label>

        <label>
          University ID (optional)
          <input value={universityId} onChange={(e) => setUniversityId(e.target.value)} />
        </label>

        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={notifyEmail} onChange={(e) => setNotifyEmail(e.target.checked)} />
          Email me confirmations/reminders
        </label>

        <label>
          Password
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
        </label>

        <button disabled={loading}>{loading ? "Creating..." : "Create account"}</button>
      </form>
    </div>
  );
}
