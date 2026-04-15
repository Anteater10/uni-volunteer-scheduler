import React from "react";
import { Link } from "react-router-dom";
import { EmptyState, Button } from "../components/ui";

export default function NotFoundPage() {
  return (
    <EmptyState
      /* TODO(copy) */
      title="Page not found"
      /* TODO(copy) */
      body="That page doesn't exist."
      action={
        <Button as={Link} to="/">
          {/* TODO(copy) */}
          Go home
        </Button>
      }
    />
  );
}
