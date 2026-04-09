import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader, Card, Button } from "../components/ui";

export default function SignupConfirmedPage() {
  const [searchParams] = useSearchParams();
  const eventId = searchParams.get("event");

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <PageHeader title="Signup confirmed" />
      <Card>
        <p className="mb-6 text-base text-[var(--color-fg)]">
          {/* TODO(copy) */}
          Your spot is locked in. We&apos;ll see you there!
        </p>
        <div className="flex flex-wrap gap-3">
          <Button as={Link} to="/my-signups">
            View my signups
          </Button>
          {eventId && (
            <Button as={Link} to={`/events/${eventId}`} variant="secondary">
              Back to event
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
