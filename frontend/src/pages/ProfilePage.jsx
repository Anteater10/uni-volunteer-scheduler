import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../state/authContext";
import { PageHeader, Card, Button, Label } from "../components/ui";

export default function ProfilePage() {
  const { user, logout } = useAuth();

  return (
    <div>
      {/* TODO(copy) */}
      <PageHeader title="Profile" />

      <Card>
        <div className="space-y-3">
          <div>
            {/* TODO(copy) */}
            <Label>Display name</Label>
            <p className="text-base">{user?.name || "—"}</p>
          </div>
          <div>
            {/* TODO(copy) */}
            <Label>Email</Label>
            <p className="text-base">{user?.email || "—"}</p>
          </div>
          {user?.role && (
            <div>
              {/* TODO(copy) */}
              <Label>Role</Label>
              <p className="text-base">{user.role}</p>
            </div>
          )}
        </div>
      </Card>

      <div className="mt-4 flex flex-col gap-2">
        {/* TODO(copy): change-password route lands in a future phase */}
        <Button variant="secondary" as={Link} to="/profile/change-password">
          {/* TODO(copy) */}
          Change password
        </Button>
        <Button variant="danger" onClick={logout}>
          {/* TODO(copy) */}
          Log out
        </Button>
      </div>
    </div>
  );
}
