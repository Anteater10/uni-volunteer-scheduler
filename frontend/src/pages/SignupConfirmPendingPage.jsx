import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { PageHeader, Card, Button } from "../components/ui";

export default function SignupConfirmPendingPage() {
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") || "";
  const eventId = searchParams.get("event") || "";
  const [lastSentAt, setLastSentAt] = useState(null);

  const mutation = useMutation({
    mutationFn: api.resendMagicLink,
    onSuccess: () => setLastSentAt(new Date()),
  });

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <PageHeader title="Check your inbox" />
      <Card>
        <p className="mb-6 text-base text-[var(--color-fg)]">
          {/* TODO(copy) */}
          We sent a confirmation link to <strong>{email}</strong>. Click it
          within 15 minutes to lock in your spot.
        </p>

        {mutation.isSuccess && lastSentAt && (
          <div
            role="status"
            className="mb-4 rounded-lg bg-green-50 border border-green-200 p-3 text-green-900 text-sm"
          >
            Email resent at {lastSentAt.toLocaleTimeString()}.
          </div>
        )}
        {mutation.isError && mutation.error?.status === 429 && (
          <div
            role="alert"
            className="mb-4 rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-900 text-sm"
          >
            {/* TODO(copy) */}
            Please wait a few minutes before requesting another link.
          </div>
        )}

        <Button
          onClick={() => mutation.mutate({ email, eventId })}
          disabled={mutation.isPending || !email}
        >
          {mutation.isPending ? "Sending..." : "Resend email"}
        </Button>
      </Card>
    </div>
  );
}
