export type AppRole =
  | "Patient"
  | "Doctor"
  | "Nurse"
  | "Lab Technician"
  | "Administrator";

export const dashboardRouteMap: Record<AppRole, string> = {
  Patient: "/dashboard/patient",
  Doctor: "/dashboard/doctor",
  Nurse: "/dashboard/nurse",
  "Lab Technician": "/dashboard/lab-technician",
  Administrator: "/dashboard/admin",
};

export const roleModules: Record<AppRole, string[]> = {
  Patient: ["My Records", "Consent", "Emergency Access", "Notifications"],
  Doctor: ["Assigned Patients", "Record Review", "Diagnosis Upload", "Emergency Request"],
  Nurse: ["Assigned Patients", "Vitals Upload", "Care Plans"],
  "Lab Technician": ["Assigned Samples", "Lab Report Upload", "Queue Management"],
  Administrator: ["User Management", "Role Assignment", "Registration Approvals", "Audit Logs"],
};

// These MUST mirror backend/app/rbac.py — the backend is the authoritative
// enforcer, and divergent strings here would gate the UI on permissions the
// server has never heard of. Used only as a fallback when a session is
// restored from a cookie; a fresh login uses the permissions the API returns.
export const rolePermissions: Record<AppRole, string[]> = {
  Patient: ["records:read:own", "records:upload:own", "consent:grant", "consent:revoke", "session:logout"],
  Doctor: ["records:read:approved", "records:upload:diagnosis", "consent:request", "emergency:request", "session:logout"],
  Nurse: ["patients:view:assigned", "records:upload:vitals", "session:logout"],
  "Lab Technician": ["records:upload:lab", "records:read:assigned", "session:logout"],
  Administrator: [
    "users:manage", "roles:assign", "permissions:manage", "audit:read",
    "system:configure", "keys:rotate", "registrations:manage", "security:view",
    "users:disable", "users:enable", "session:logout",
  ],
};

export function normalizeRole(role: string | null | undefined): AppRole | null {
  if (!role) return null;
  const cleaned = role.trim().toLowerCase();
  return (Object.keys(dashboardRouteMap) as AppRole[]).find((candidate) => candidate.toLowerCase() === cleaned) ?? null;
}

export function getAllowedModules(role: AppRole | null): string[] {
  return role ? roleModules[role] : [];
}

export function hasPermission(role: AppRole | null, permission: string): boolean {
  if (!role) return false;
  return rolePermissions[role].includes(permission);
}

export function canAccessRoute(role: AppRole | null, route: string): boolean {
  if (!role) return false;
  return dashboardRouteMap[role] === route;
}

export function getRoleFromCookie(cookieValue: string | null): AppRole | null {
  if (!cookieValue) return null;
  const decoded = decodeURIComponent(cookieValue);
  return (Object.keys(dashboardRouteMap) as AppRole[]).find((role) => role === decoded) ?? null;
}
