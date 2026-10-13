"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { normalizeRole, dashboardRouteMap } from "@/lib/iam";
import { ROLE_COOKIE } from "@/lib/session";

function readCookie(name: string) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()\[\]\\/+^])/g, "\\$1")}=(.*?)(?:;|$)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export default function DashboardPage() {
  const router = useRouter();

  useEffect(() => {
    const stored = readCookie(ROLE_COOKIE) || localStorage.getItem(ROLE_COOKIE);
    const role = normalizeRole(stored);
    // Without a recognised role there is no dashboard to land on — send them to log in.
    router.replace(role ? dashboardRouteMap[role] : "/login");
  }, [router]);

  return null;
}
