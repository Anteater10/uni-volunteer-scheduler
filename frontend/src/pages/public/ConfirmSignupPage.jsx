// src/pages/public/ConfirmSignupPage.jsx
//
// Entry point from the confirmation email link (/signup/confirm?token=...).
// Calls the confirm endpoint then renders the manage view INLINE (no redirect).
// Per locked decision 1: inline render after confirm succeeds.

import React, { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../../lib/api";
import { Card } from "../../components/ui";
import ManageSignupsPage from "./ManageSignupsPage";

// State machine: confirming | confirmed | error
export default function ConfirmSignupPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState("confirming");

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }
    api.public
      .confirmSignup(token)
      .then(() => setState("confirmed"))
      .catch(() => setState("error"));
  }, [token]);

  if (state === "confirming") {
    return (
      <div className="flex flex-col items-center justify-center mt-20 gap-4">
        <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full" />
        <p className="text-gray-600">Confirming your signup...</p>
      </div>
    );
  }

  if (state === "error") {
    return (
      <Card className="max-w-md mx-auto mt-12 p-6 text-center">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Link expired or invalid
        </h2>
        <p className="text-gray-600">
          This link has expired or is invalid. Please check your email for a
          new link.
        </p>
      </Card>
    );
  }

  // confirmed — render manage view inline with same token
  return (
    <div>
      <div className="max-w-xl mx-auto mt-6 px-4">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
          <p className="text-green-800 font-medium text-sm">
            Your signup is confirmed! You can manage or cancel your signups
            below.
          </p>
        </div>
      </div>
      <ManageSignupsPage tokenOverride={token} />
    </div>
  );
}
