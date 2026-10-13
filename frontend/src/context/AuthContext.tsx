"use client";

import React, { createContext, useContext, useMemo, useState, useEffect } from "react";
import { normalizeRole, type AppRole, rolePermissions, dashboardRouteMap } from "@/lib/iam";
import { TOKEN_COOKIE, ROLE_COOKIE, USER_ID_COOKIE } from "@/lib/session";

type AuthState = {
  isAuthenticated: boolean;
  role: AppRole | null;
  permissions: string[];
  userId: string | null;
  accessToken: string | null;
  setSession: (input: { role: AppRole | null; permissions?: string[]; userId?: string | null; accessToken?: string | null }) => void;
  clearSession: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

function readCookie(name: string) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()\[\]\\/+^])/g, "\\$1")}=(.*?)(?:;|$)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<AppRole | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    // Read from cookies or localStorage only after mount (client-side)
    const cookieRole = normalizeRole(readCookie(ROLE_COOKIE) || localStorage.getItem(ROLE_COOKIE));

    // Defer to avoid synchronous cascading render warnings
    queueMicrotask(() => {
      setRole(cookieRole);
      setPermissions(cookieRole ? rolePermissions[cookieRole] : []);
      setUserId(readCookie(USER_ID_COOKIE) || localStorage.getItem(USER_ID_COOKIE));
      setAccessToken(readCookie(TOKEN_COOKIE) || localStorage.getItem(TOKEN_COOKIE));
      setIsMounted(true);
    });
  }, []);

  const value = useMemo<AuthState>(() => ({
    isAuthenticated: Boolean(role && accessToken),
    role,
    permissions,
    userId,
    accessToken,
    setSession: ({ role: nextRole, permissions: nextPermissions, userId: nextUserId, accessToken: nextToken }) => {
      setRole(nextRole);
      setPermissions(nextPermissions ?? (nextRole ? rolePermissions[nextRole] : []));
      setUserId(nextUserId ?? null);
      setAccessToken(nextToken ?? null);
    },
    clearSession: () => {
      setRole(null);
      setPermissions([]);
      setUserId(null);
      setAccessToken(null);
    },
  }), [accessToken, permissions, role, userId]);

  // Avoid hydration mismatch by not rendering until client-side auth state is loaded
  if (!isMounted) return null;

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

export function isDashboardRouteAllowed(role: AppRole | null, route: string) {
  if (!role) return false;
  return dashboardRouteMap[role] === route;
}
