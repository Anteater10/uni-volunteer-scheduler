// src/state/authContext.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import authStorage from "../lib/authStorage";
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
      // only try /me if a token exists
      const tok = authStorage.getToken();
      if (tok) await reloadMe();
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

  function logout() {
    api.logout();
    setUser(null);
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
