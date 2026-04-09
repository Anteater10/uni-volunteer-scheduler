import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../state/useAuth";
import {
  PageHeader,
  Label,
  Input,
  Button,
  FieldError,
} from "../components/ui";

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
    <div className="mx-auto max-w-sm w-full pt-8">
      {/* TODO(copy) */}
      <PageHeader title="Create account" />

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="reg-name">Full name</Label>
          <Input
            id="reg-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            required
          />
        </div>
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="reg-email">Email</Label>
          <Input
            id="reg-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </div>
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="reg-uniid">University ID (optional)</Label>
          <Input
            id="reg-uniid"
            value={universityId}
            onChange={(e) => setUniversityId(e.target.value)}
          />
        </div>
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="reg-password">Password</Label>
          <Input
            id="reg-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={notifyEmail}
            onChange={(e) => setNotifyEmail(e.target.checked)}
            className="h-4 w-4"
          />
          {/* TODO(copy) */}
          Email me confirmations and reminders
        </label>
        <FieldError>{err}</FieldError>
        <Button
          type="submit"
          className="w-full"
          size="lg"
          disabled={loading}
        >
          {/* TODO(copy) */}
          {loading ? "Creating..." : "Create account"}
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Button variant="ghost" as={Link} to="/login">
          {/* TODO(copy) */}
          Already have an account? Sign in
        </Button>
      </div>
    </div>
  );
}
