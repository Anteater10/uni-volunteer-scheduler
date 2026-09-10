// src/state/authContext.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import { refreshAccessToken } from "../lib/authToken";
import { AuthContext } from "./AuthContext";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  async function reloadMe() {
    try {
      const me = await api.me();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    }
  }

  useEffect(() => {
    (async () => {
      // The access token lives in memory only (Phase L3), so it never
      // survives a page reload — recover it via a silent refresh against
      // the HttpOnly refresh cookie before deciding whether to call /me.
      // No cookie (or an expired one) means genuinely logged out.
      try {
        await refreshAccessToken();
        await reloadMe();
      } catch {
        setUser(null);
      }
      setInitializing(false);
    })();
  }, []);

  async function login(email, password) {
    await api.login(email, password); // stores token internally
    return reloadMe();
  }

  async function register(payload) {
    // your UI expects “register then be able to use the app”
    await api.register(payload);
    // then login to get token
    await api.login(payload.email, payload.password);
    return reloadMe();
  }

  async function logout() {
    // Clear the user first so the UI leaves the authenticated view immediately
    // rather than waiting on the revoke round trip (BASE-SEC-43).
    setUser(null);
    await api.logout();
  }

  const value = useMemo(
    () => ({
      user,
      initializing,
      isAuthed: !!user,
      role: user?.role || null,
      reloadMe,
      login,
      register,
      logout,
    }),
    [user, initializing]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
