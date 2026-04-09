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

export default function LoginPage() {
  const nav = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      await login(email.trim(), password);
      nav("/events");
    } catch (e2) {
      setErr(e2?.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm w-full pt-8">
      {/* TODO(copy) */}
      <PageHeader title="Sign in" />

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="login-email">Email</Label>
          <Input
            id="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </div>
        <div>
          {/* TODO(copy) */}
          <Label htmlFor="login-password">Password</Label>
          <Input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <FieldError>{err}</FieldError>
        <Button
          type="submit"
          className="w-full"
          size="lg"
          disabled={loading}
        >
          {/* TODO(copy) */}
          {loading ? "Signing in..." : "Sign in"}
        </Button>
      </form>

      <div className="mt-4 text-center">
        <Button variant="ghost" as={Link} to="/register">
          {/* TODO(copy) */}
          Create an account
        </Button>
      </div>
    </div>
  );
}
