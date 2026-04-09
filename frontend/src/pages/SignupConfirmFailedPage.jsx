import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { PageHeader, Card, Button, Input, Label } from "../components/ui";

const REASON_MESSAGES = {
  expired: "Your confirmation link has expired. Request a new one below.",
  used: "This link has already been used. If you need another, request below.",
  not_found: "We couldn't find that link. Request a new one below.",
};

export default function SignupConfirmFailedPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason") || "not_found";
  const eventId = searchParams.get("event") || "";
  const [email, setEmail] = useState("");

  const mutation = useMutation({
    mutationFn: api.resendMagicLink,
  });

  const onSubmit = (e) => {
    e.preventDefault();
    mutation.mutate({ email, eventId });
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <PageHeader title="Confirmation failed" />
      <Card>
        {/* TODO(copy) */}
        <p className="mb-6 text-base text-[var(--color-fg)]">
          {REASON_MESSAGES[reason] || REASON_MESSAGES.not_found}
        </p>

        {mutation.isSuccess && (
          <div
            role="status"
            className="mb-4 rounded-lg bg-green-50 border border-green-200 p-3 text-green-900 text-sm"
          >
            {/* TODO(copy) */}
            Email sent — check your inbox.
          </div>
        )}
        {mutation.isError && mutation.error?.status === 429 && (
          <div
            role="alert"
            className="mb-4 rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-900 text-sm"
          >
            {/* TODO(copy) */}
            You&apos;ve requested too many links for this email. Please wait a
            few minutes and try again.
          </div>
        )}
        {mutation.isError && mutation.error?.status !== 429 && (
          <div
            role="alert"
            className="mb-4 rounded-lg bg-red-50 border border-red-200 p-3 text-red-900 text-sm"
          >
            Something went wrong. Please try again.
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <div>
            <Label htmlFor="resend-email">Email</Label>
            <Input
              id="resend-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <Button type="submit" disabled={mutation.isPending || !email}>
            {mutation.isPending ? "Sending..." : "Resend confirmation link"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
